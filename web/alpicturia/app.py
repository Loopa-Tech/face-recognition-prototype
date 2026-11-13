import csv
import hashlib
import html
import importlib.util
import io
import json
import logging
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, unquote
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware
from .db import Database
from .security import audit, digest, enqueue, issue_mail_token, limited, password_hash, password_ok, uid
from .worker import validated_image

STATIC=Path(__file__).parent/'static'
MAX_UPLOAD=25*1024*1024
CONSENT_VERSION='selfie-search-v1'

class Credentials(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=12,max_length=128)
    @field_validator('email')
    @classmethod
    def email_valid(cls,value):
        value=value.strip().lower()
        if value.count('@')!=1 or '.' not in value.split('@')[-1] or any(c.isspace() for c in value):
            raise ValueError('Adresse email invalide.')
        return value

class Signup(Credentials):
    name:str=Field(min_length=2,max_length=100)
    role:str='attendee'

class Login(BaseModel):
    email:str=Field(max_length=254)
    password:str=Field(max_length=128)

class EmailInput(BaseModel):
    email:str=Field(max_length=254)

class TokenInput(BaseModel):
    token:str=Field(min_length=20,max_length=200)
    password:str|None=Field(default=None,min_length=12,max_length=128)

class EventInput(BaseModel):
    title:str=Field(min_length=2,max_length=150)
    slug:str=Field(min_length=2,max_length=100,pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    location:str=Field(min_length=2,max_length=150)
    date:date
    description:str=Field(default='',max_length=3000)
    published:bool=False

class KeyInput(BaseModel):
    name:str=Field(min_length=2,max_length=80)
    scopes:list[str]=Field(default=['read'],min_length=1,max_length=3)

class Assignment(BaseModel):
    user_id:str=Field(max_length=40)

class RoleInput(BaseModel):
    role:str

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request,call_next):
        # Cookie requests are same-origin; agent requests use a scoped bearer key.
        origin=request.headers.get('origin')
        base=request.app.state.base_url
        if request.method not in ('GET','HEAD','OPTIONS'):
            if origin and origin.rstrip('/')!=base:
                return JSONResponse({'detail':'Origine non autorisée.'},403)
            if request.headers.get('sec-fetch-site')=='cross-site':
                return JSONResponse({'detail':'Origine non autorisée.'},403)
        try:
            length=int(request.headers.get('content-length','0'))
        except ValueError:
            return JSONResponse({'detail':'Taille invalide.'},400)
        if length>MAX_UPLOAD+1024:
            return JSONResponse({'detail':'Fichier limité à 25 Mo.'},413)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Permissions-Policy']='camera=(self), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if request.url.path.startswith(('/api/','/account/','/app','/photographer','/admin')):
            response.headers['Cache-Control']='no-store'
            response.headers['X-Robots-Tag']='noindex, nofollow'
        if base.startswith('https://'):
            response.headers['Strict-Transport-Security']='max-age=31536000'
        return response


def create_app(root=None):
    app=FastAPI(title='Alpicturia API',version='0.1.0',docs_url=None,redoc_url=None)
    app.state.db=Database(root)
    app.state.base_url=os.getenv('PUBLIC_BASE_URL','http://localhost:8000').rstrip('/')
    if urlparse(app.state.base_url).scheme not in ('http','https'):
        raise RuntimeError('PUBLIC_BASE_URL must be an HTTP(S) origin.')
    app.add_middleware(SecurityMiddleware)
    app.mount('/static',StaticFiles(directory=STATIC),name='static')
    db=app.state.db

    def identity(request:Request):
        auth=request.headers.get('authorization','')
        now=time.time()
        if auth.startswith('Bearer '):
            key=db.one('SELECT * FROM api_keys WHERE token=? AND expires>?',(digest(auth[7:]),now))
            user=db.one('SELECT * FROM users WHERE id=? AND disabled=0',(key['user_id'],)) if key else None
            if user:
                required={'read'} if request.method=='GET' else {'write'}
                if request.url.path.startswith('/api/admin'):
                    required.add('admin')
                if not required.issubset(set(json.loads(key['scopes']))):
                    raise HTTPException(403,'Cette clé ne permet pas cette opération.')
                request.state.api_key=True
        else:
            raw=request.cookies.get('alpi_session','')
            user=db.one('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>? AND u.disabled=0',(digest(raw),now)) if raw else None
        if not user:
            raise HTTPException(401,'Connectez-vous pour continuer.')
        db.run('UPDATE users SET last_seen=? WHERE id=? AND (last_seen IS NULL OR last_seen<?)',(now,user['id'],now-300))
        return user

    def verified(user=Depends(identity)):
        if not user['verified']:
            raise HTTPException(403,'Confirmez votre adresse email pour continuer.')
        return user

    def admin(user=Depends(verified)):
        if user['role']!='admin':
            raise HTTPException(403,'Accès réservé à l’administration.')
        return user

    def upload_access(event_id,user):
        event=db.one('SELECT * FROM events WHERE id=?',(event_id,))
        if not event:
            raise HTTPException(404,'Événement introuvable.')
        if user['role']!='admin' and (user['role']!='photographer' or not db.one('SELECT 1 FROM assignments WHERE event_id=? AND user_id=?',(event_id,user['id']))):
            raise HTTPException(403,'Vous devez être photographe assigné à cet événement.')
        return event

    def public_user(user):
        return {key:user[key] for key in ('id','email','name','role','verified','created')}

    def session(response,user_id):
        raw=secrets.token_urlsafe(32)
        db.run('INSERT INTO sessions VALUES(?,?,?)',(digest(raw),user_id,time.time()+7*86400))
        response.set_cookie('alpi_session',raw,max_age=7*86400,httponly=True,secure=app.state.base_url.startswith('https://'),samesite='lax',path='/')

    def throttle(request,key,limit=10,window=900):
        # No untrusted X-Forwarded-For: configure trusted proxy handling at Uvicorn.
        address=request.client.host if request.client else 'unknown'
        limited(db,f'{key}:{address}',limit,window)

    async def read_image(request):
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>MAX_UPLOAD:
                raise HTTPException(413,'Fichier limité à 25 Mo.')
        try:
            validated_image(bytes(data))
        except Exception as exc:
            if not isinstance(exc,ValueError):
                raise HTTPException(422,'Image illisible. Utilisez JPEG, PNG ou WebP.') from exc
            raise HTTPException(422,str(exc)) from exc
        return bytes(data)

    @app.get('/api/health')
    def health():
        db.one('SELECT 1')
        return {'status':'ok','face_engine_available':importlib.util.find_spec('face_recognition') is not None,'email_configured':bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM'))}

    @app.post('/api/auth/signup',status_code=201)
    def signup(data:Signup,request:Request,response:Response):
        throttle(request,'signup',5,3600)
        if data.role not in ('attendee','photographer'):
            raise HTTPException(422,'Rôle invalide.')
        user_id=uid(); now=time.time()
        try:
            db.run('INSERT INTO users(id,email,name,password,role,created) VALUES(?,?,?,?,?,?)',(user_id,data.email,data.name.strip(),password_hash(data.password),data.role,now))
        except sqlite3.IntegrityError:
            raise HTTPException(409,'Impossible de créer ce compte. Essayez de vous connecter ou de récupérer votre mot de passe.')
        user=db.one('SELECT * FROM users WHERE id=?',(user_id,))
        issue_mail_token(db,user,'verify',app.state.base_url)
        session(response,user_id)
        audit(db,user_id,'account.created')
        return public_user(user)

    @app.post('/api/auth/login')
    def login(data:Login,request:Request,response:Response):
        throttle(request,'login',20,900)
        user=db.one('SELECT * FROM users WHERE email=?',(data.email.strip().lower(),))
        # Always perform a password derivation to reduce account enumeration timing.
        stored=user['password'] if user else DUMMY_PASSWORD
        valid=password_ok(data.password,stored)
        if not user or not valid or user['disabled']:
            raise HTTPException(401,'Email ou mot de passe incorrect.')
        session(response,user['id']); audit(db,user['id'],'account.login')
        return public_user(user)

    @app.post('/api/auth/logout')
    def logout(request:Request,response:Response):
        db.run('DELETE FROM sessions WHERE token=?',(digest(request.cookies.get('alpi_session','')),))
        response.delete_cookie('alpi_session',path='/')
        return {'ok':True}

    @app.post('/api/auth/forgot')
    def forgot(data:EmailInput,request:Request):
        throttle(request,'forgot',5,3600)
        user=db.one('SELECT * FROM users WHERE email=? AND disabled=0',(data.email.strip().lower(),))
        if user:
            issue_mail_token(db,user,'reset',app.state.base_url)
        return {'message':'Si ce compte existe, un email de récupération sera envoyé.'}

    @app.post('/api/auth/resend')
    def resend(request:Request,user=Depends(identity)):
        limited(db,'verify:'+user['id'],3,3600)
        if not user['verified']:
            issue_mail_token(db,user,'verify',app.state.base_url)
        return {'ok':True}

    def consume_token(data,kind):
        now=time.time()
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT * FROM tokens WHERE token=? AND kind=? AND expires>?',(digest(data.token),kind,now)).fetchone()
            if not row:
                raise HTTPException(400,'Lien invalide ou expiré. Demandez un nouvel email.')
            if kind=='verify':
                conn.execute('UPDATE users SET verified=1 WHERE id=?',(row['user_id'],))
            else:
                if not data.password:
                    raise HTTPException(422,'Nouveau mot de passe requis.')
                conn.execute('UPDATE users SET password=? WHERE id=?',(password_hash(data.password),row['user_id']))
                conn.execute('DELETE FROM sessions WHERE user_id=?',(row['user_id'],))
                conn.execute('DELETE FROM api_keys WHERE user_id=?',(row['user_id'],))
            conn.execute('DELETE FROM tokens WHERE user_id=? AND kind=?',(row['user_id'],kind))
        return {'ok':True}

    @app.post('/api/auth/verify')
    def verify(data:TokenInput):
        return consume_token(data,'verify')

    @app.post('/api/auth/reset')
    def reset(data:TokenInput):
        return consume_token(data,'reset')

    @app.get('/api/me')
    def me(user=Depends(identity)):
        return public_user(user)

    @app.get('/api/me/export')
    def export_me(user=Depends(verified)):
        return {'user':public_user(user),'searches':db.all('SELECT id,event_id,consent_version,consented,status,expires,created FROM searches WHERE user_id=?',(user['id'],)),'photos':db.all('SELECT id,event_id,filename,status,created FROM photos WHERE owner_id=?',(user['id'],))}

    @app.delete('/api/me')
    def delete_me(request:Request,response:Response,user=Depends(verified)):
        if getattr(request.state,'api_key',False):
            raise HTTPException(403,'Supprimez votre compte depuis l’application.')
        if request.headers.get('x-confirm-delete')!='DELETE':
            raise HTTPException(400,'Confirmez la suppression définitive.')
        if user['role']=='admin':
            raise HTTPException(409,'Transférez le rôle administrateur avant de supprimer ce compte.')
        photos=db.all('SELECT path,preview FROM photos WHERE owner_id=?',(user['id'],))
        searches=db.all('SELECT path FROM searches WHERE user_id=?',(user['id'],))
        with db.connect() as conn:
            conn.execute("DELETE FROM jobs WHERE (kind='photo' AND ref_id IN (SELECT id FROM photos WHERE owner_id=?)) OR (kind='search' AND ref_id IN (SELECT id FROM searches WHERE user_id=?))",(user['id'],user['id']))
            conn.execute('DELETE FROM users WHERE id=?',(user['id'],))
            conn.execute('UPDATE audit SET actor_id=NULL WHERE actor_id=?',(user['id'],))
        for row in photos+searches:
            for key in ('path','preview'):
                if row.get(key): (db.root/row[key]).unlink(missing_ok=True)
        response.delete_cookie('alpi_session',path='/')
        return {'ok':True}

    @app.get('/api/events')
    def events():
        return db.all('SELECT id,slug,title,location,date,description FROM events WHERE published=1 ORDER BY date DESC')

    @app.get('/api/photographer/events')
    def photographer_events(user=Depends(verified)):
        if user['role']=='admin':
            return db.all('SELECT * FROM events ORDER BY date DESC')
        if user['role']!='photographer':
            raise HTTPException(403,'Espace réservé aux photographes.')
        return db.all('SELECT e.* FROM events e JOIN assignments a ON a.event_id=e.id WHERE a.user_id=? ORDER BY e.date DESC',(user['id'],))

    @app.post('/api/events/{event_id}/photos',status_code=201)
    async def upload_photo(event_id:str,request:Request,user=Depends(verified)):
        upload_access(event_id,user)
        limited(db,'upload:'+user['id'],5000,3600)
        data=await read_image(request)
        sha=hashlib.sha256(data).hexdigest()
        existing=db.one('SELECT id,status FROM photos WHERE event_id=? AND owner_id=? AND sha256=?',(event_id,user['id'],sha))
        if existing:
            return {**existing,'duplicate':True}
        photo_id=uid(); path=f'photos/{photo_id}.image'
        filename=Path(unquote(request.headers.get('x-filename','photo')).replace('\\','/')).name[:200]
        (db.root/path).write_bytes(data)
        try:
            now=time.time()
            with db.connect() as conn:
                conn.execute('INSERT INTO photos(id,event_id,owner_id,filename,sha256,size,path,created) VALUES(?,?,?,?,?,?,?,?)',(photo_id,event_id,user['id'],filename,sha,len(data),path,now))
                conn.execute('INSERT INTO jobs(id,kind,ref_id,available,created) VALUES(?,?,?,?,?)',(uid(),'photo',photo_id,now,now))
        except sqlite3.IntegrityError:
            (db.root/path).unlink(missing_ok=True)
            existing=db.one('SELECT id,status FROM photos WHERE event_id=? AND owner_id=? AND sha256=?',(event_id,user['id'],sha))
            if existing: return {**existing,'duplicate':True}
            raise
        audit(db,user['id'],'photo.uploaded',photo_id)
        return {'id':photo_id,'status':'queued','duplicate':False}

    @app.get('/api/events/{event_id}/photos')
    def own_photos(event_id:str,offset:int=0,limit:int=50,user=Depends(verified)):
        upload_access(event_id,user)
        if offset<0 or not 1<=limit<=100: raise HTTPException(422,'Pagination invalide.')
        clause='' if user['role']=='admin' else ' AND owner_id=?'
        args=(event_id,) if not clause else (event_id,user['id'])
        return {'items':db.all('SELECT id,filename,status,error,face_count,size,created FROM photos WHERE event_id=?'+clause+' ORDER BY created DESC LIMIT ? OFFSET ?',args+(limit,offset)),'total':db.one('SELECT count(*) AS n FROM photos WHERE event_id=?'+clause,args)['n']}

    @app.post('/api/photos/{photo_id}/retry')
    def retry_photo(photo_id:str,user=Depends(verified)):
        photo=db.one('SELECT * FROM photos WHERE id=?',(photo_id,))
        if not photo: raise HTTPException(404,'Photo introuvable.')
        upload_access(photo['event_id'],user)
        if user['role']!='admin' and photo['owner_id']!=user['id']: raise HTTPException(403,'Accès refusé.')
        if photo['status']!='failed': raise HTTPException(409,'Seul un traitement en échec peut être relancé.')
        db.run("UPDATE photos SET status='queued',error=NULL WHERE id=?",(photo_id,)); enqueue(db,'photo',photo_id)
        audit(db,user['id'],'photo.retried',photo_id)
        return {'ok':True}

    @app.delete('/api/photos/{photo_id}')
    def delete_photo(photo_id:str,user=Depends(verified)):
        photo=db.one('SELECT * FROM photos WHERE id=?',(photo_id,))
        if not photo: raise HTTPException(404,'Photo introuvable.')
        if user['role']!='admin' and photo['owner_id']!=user['id']: raise HTTPException(403,'Accès refusé.')
        with db.connect() as conn:
            conn.execute("DELETE FROM jobs WHERE kind='photo' AND ref_id=?",(photo_id,))
            conn.execute('DELETE FROM photos WHERE id=?',(photo_id,))
        for path in (photo['path'],photo['preview']):
            if path: (db.root/path).unlink(missing_ok=True)
        audit(db,user['id'],'photo.deleted',photo_id)
        return {'ok':True}

    @app.post('/api/events/{event_id}/searches',status_code=202)
    async def search(event_id:str,request:Request,user=Depends(verified)):
        limited(db,'search:'+user['id'],20,3600)
        event=db.one('SELECT * FROM events WHERE id=? AND published=1',(event_id,))
        if not event: raise HTTPException(404,'Événement introuvable.')
        if request.headers.get('x-consent-version')!=CONSENT_VERSION:
            raise HTTPException(422,'Votre consentement à cette recherche est requis.')
        data=await read_image(request)
        search_id=uid(); path=f'selfies/{search_id}.image'; now=time.time()
        (db.root/path).write_bytes(data)
        with db.connect() as conn:
            conn.execute('INSERT INTO searches(id,user_id,event_id,consent_version,consented,path,expires,created) VALUES(?,?,?,?,?,?,?,?)',(search_id,user['id'],event_id,CONSENT_VERSION,now,path,now+7*86400,now))
            conn.execute('INSERT INTO jobs(id,kind,ref_id,available,created) VALUES(?,?,?,?,?)',(uid(),'search',search_id,now,now))
        audit(db,user['id'],'search.created',search_id)
        return {'id':search_id,'status':'queued'}

    @app.get('/api/searches')
    def searches(user=Depends(verified)):
        return db.all('SELECT s.id,s.event_id,e.title,s.status,s.error,s.created,s.expires FROM searches s JOIN events e ON e.id=s.event_id WHERE s.user_id=? ORDER BY s.created DESC LIMIT 100',(user['id'],))

    @app.get('/api/searches/{search_id}')
    def search_result(search_id:str,user=Depends(verified)):
        item=db.one('SELECT id,event_id,status,error,created,expires FROM searches WHERE id=? AND user_id=?',(search_id,user['id']))
        if not item: raise HTTPException(404,'Recherche introuvable.')
        if item['expires']<=time.time():
            item['status']='expired'; item['photos']=[]
        else:
            item['photos']=db.all("SELECT p.id,p.filename FROM matches m JOIN photos p ON p.id=m.photo_id JOIN events e ON e.id=p.event_id WHERE m.search_id=? AND p.status='ready' AND e.published=1 ORDER BY m.distance",(search_id,))
        return item

    @app.delete('/api/searches/{search_id}')
    def delete_search(search_id:str,user=Depends(verified)):
        item=db.one('SELECT * FROM searches WHERE id=? AND user_id=?',(search_id,user['id']))
        if not item: raise HTTPException(404,'Recherche introuvable.')
        with db.connect() as conn:
            conn.execute("DELETE FROM jobs WHERE kind='search' AND ref_id=?",(search_id,))
            conn.execute('DELETE FROM searches WHERE id=?',(search_id,))
        if item['path']: (db.root/item['path']).unlink(missing_ok=True)
        audit(db,user['id'],'search.deleted',search_id)
        return {'ok':True}

    @app.get('/api/photos/{photo_id}/preview')
    def preview(photo_id:str,user=Depends(verified)):
        photo=db.one('SELECT * FROM photos WHERE id=?',(photo_id,))
        if not photo or not photo['preview']: raise HTTPException(404,'Aperçu indisponible.')
        permitted=user['role']=='admin' or photo['owner_id']==user['id']
        if not permitted:
            permitted=db.one("SELECT 1 FROM matches m JOIN searches s ON s.id=m.search_id JOIN events e ON e.id=s.event_id WHERE m.photo_id=? AND s.user_id=? AND s.expires>? AND e.published=1",(photo_id,user['id'],time.time()))
        if not permitted: raise HTTPException(404,'Aperçu introuvable.')
        return FileResponse(db.root/photo['preview'],media_type='image/jpeg')

    @app.get('/api/photos/{photo_id}/original')
    def original(photo_id:str,user=Depends(verified)):
        photo=db.one('SELECT * FROM photos WHERE id=?',(photo_id,))
        if not photo or (photo['owner_id']!=user['id'] and user['role']!='admin'): raise HTTPException(404,'Original introuvable.')
        return FileResponse(db.root/photo['path'],filename=photo['filename'])

    @app.get('/api/keys')
    def keys(user=Depends(verified)):
        return db.all('SELECT id,name,scopes,created,expires FROM api_keys WHERE user_id=?',(user['id'],))

    @app.post('/api/keys',status_code=201)
    def create_key(data:KeyInput,request:Request,user=Depends(verified)):
        if getattr(request.state,'api_key',False): raise HTTPException(403,'Créez les clés depuis votre compte.')
        valid={'read','write','admin'} if user['role']=='admin' else {'read','write'}
        if not set(data.scopes)<=valid: raise HTTPException(403,'Portée non autorisée.')
        if db.one('SELECT count(*) AS n FROM api_keys WHERE user_id=?',(user['id'],))['n']>=10: raise HTTPException(409,'Limite de dix clés atteinte.')
        raw='alpi_'+secrets.token_urlsafe(32); key_id=uid(); now=time.time()
        db.run('INSERT INTO api_keys VALUES(?,?,?,?,?,?,?)',(key_id,digest(raw),user['id'],data.name,json.dumps(sorted(set(data.scopes))),now,now+90*86400))
        audit(db,user['id'],'key.created',key_id)
        return {'id':key_id,'token':raw,'expires':now+90*86400}

    @app.delete('/api/keys/{key_id}')
    def delete_key(key_id:str,user=Depends(verified)):
        db.run('DELETE FROM api_keys WHERE id=? AND user_id=?',(key_id,user['id']))
        audit(db,user['id'],'key.revoked',key_id)
        return {'ok':True}

    @app.post('/api/metrics',status_code=202)
    def metrics(request:Request):
        throttle(request,'metrics',60,60)
        db.run("INSERT INTO metrics(event,path,created) VALUES('pageview',?,?)",(request.headers.get('x-page','/')[:160],time.time()))
        return {'ok':True}

    @app.get('/api/admin/overview')
    def overview(user=Depends(admin)):
        counts={name:db.one(f'SELECT count(*) AS n FROM {name}')['n'] for name in ('users','events','photos','searches')}
        counts['storage_bytes']=db.one('SELECT coalesce(sum(size),0) AS n FROM photos')['n']
        counts['pageviews_30d']=db.one('SELECT count(*) AS n FROM metrics WHERE created>?',(time.time()-30*86400,))['n']
        return {'counts':counts,'photo_status':db.all('SELECT status,count(*) AS count FROM photos GROUP BY status'),'job_status':db.all('SELECT status,count(*) AS count FROM jobs GROUP BY status'),'email_status':db.all('SELECT status,count(*) AS count FROM mail GROUP BY status'),'daily_views':db.all("SELECT date(created,'unixepoch') AS day,count(*) AS count FROM metrics WHERE created>? GROUP BY day ORDER BY day",(time.time()-30*86400,)),'configuration':{'smtp':bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM')),'face_engine':importlib.util.find_spec('face_recognition') is not None,'worker_last_seen':float((db.root/'worker-heartbeat').read_text()) if (db.root/'worker-heartbeat').exists() else None,'public_url':app.state.base_url,'search_console_verification':bool(os.getenv('GOOGLE_SITE_VERIFICATION'))}}

    @app.get('/api/admin/data/{table}')
    def admin_data(table:str,offset:int=0,limit:int=50,q:str='',user=Depends(admin)):
        columns={'users':'id,email,name,role,verified,disabled,created,last_seen','events':'*','photos':'id,event_id,owner_id,filename,size,status,error,face_count,created','searches':'id,user_id,event_id,status,error,consent_version,consented,expires,created','jobs':'id,kind,ref_id,status,attempts,error,created','mail':'id,user_id,recipient,subject,status,attempts,error,created','audit':'*','assignments':'*'}
        if table not in columns: raise HTTPException(404,'Table inconnue.')
        if offset<0 or not 1<=limit<=100: raise HTTPException(422,'Pagination invalide.')
        # Search only explicit text columns; no dynamic user-supplied SQL identifiers.
        searchcols={'users':['email','name'],'events':['title','location'],'photos':['filename'],'mail':['recipient','subject']}.get(table,[])
        where=' WHERE '+' OR '.join(f'{column} LIKE ?' for column in searchcols) if q and searchcols else ''
        args=tuple('%'+q[:100]+'%' for _ in searchcols) if where else ()
        return {'items':db.all(f'SELECT {columns[table]} FROM {table}'+where+' LIMIT ? OFFSET ?',args+(limit,offset)),'total':db.one(f'SELECT count(*) AS n FROM {table}'+where,args)['n']}

    @app.get('/api/admin/export/{table}')
    def admin_export(table:str,user=Depends(admin)):
        # Explicit allowlist validation before creating the streaming response.
        admin_data(table,0,1,'',user)
        def generate():
            offset=0; writer=None; output=io.StringIO()
            while True:
                rows=admin_data(table,offset,100,'',user)['items']
                if not rows: break
                if writer is None:
                    writer=csv.DictWriter(output,fieldnames=rows[0].keys()); writer.writeheader()
                for row in rows:
                    writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in row.items()})
                yield output.getvalue()
                output.seek(0); output.truncate(0); offset+=len(rows)
        audit(db,user['id'],'admin.export',table)
        return StreamingResponse(generate(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="alpicturia-{table}.csv"'})

    @app.post('/api/admin/events',status_code=201)
    def create_event(data:EventInput,user=Depends(admin)):
        event_id=uid()
        try:
            db.run('INSERT INTO events(id,slug,title,location,date,description,published,created) VALUES(?,?,?,?,?,?,?,?)',(event_id,data.slug,data.title,data.location,data.date.isoformat(),data.description,int(data.published),time.time()))
        except sqlite3.IntegrityError:
            raise HTTPException(409,'Ce slug existe déjà.')
        audit(db,user['id'],'event.created',event_id)
        return {'id':event_id}

    @app.get('/api/admin/photographers')
    def list_photographers(offset:int=0,limit:int=100,user=Depends(admin)):
        if offset<0 or not 1<=limit<=100: raise HTTPException(422,'Pagination invalide.')
        return db.all("SELECT id,name,email FROM users WHERE role='photographer' AND disabled=0 ORDER BY name LIMIT ? OFFSET ?",(limit,offset))

    @app.get('/api/admin/events/{event_id}')
    def get_admin_event(event_id:str,user=Depends(admin)):
        event=db.one('SELECT * FROM events WHERE id=?',(event_id,))
        if not event: raise HTTPException(404,'Événement introuvable.')
        return event

    @app.put('/api/admin/events/{event_id}')
    def update_event(event_id:str,data:EventInput,user=Depends(admin)):
        try:
            changed=db.run('UPDATE events SET slug=?,title=?,location=?,date=?,description=?,published=? WHERE id=?',(data.slug,data.title,data.location,data.date.isoformat(),data.description,int(data.published),event_id))
        except sqlite3.IntegrityError: raise HTTPException(409,'Ce slug existe déjà.')
        if not changed: raise HTTPException(404,'Événement introuvable.')
        audit(db,user['id'],'event.updated',event_id)
        return {'ok':True}

    @app.post('/api/admin/events/{event_id}/photographers')
    def assign(event_id:str,data:Assignment,user=Depends(admin)):
        target=db.one("SELECT id FROM users WHERE id=? AND role='photographer' AND disabled=0",(data.user_id,))
        if not target or not db.one('SELECT id FROM events WHERE id=?',(event_id,)): raise HTTPException(404,'Photographe ou événement introuvable.')
        db.run('INSERT OR IGNORE INTO assignments VALUES(?,?)',(event_id,data.user_id))
        audit(db,user['id'],'photographer.assigned',event_id+':'+data.user_id)
        return {'ok':True}

    @app.delete('/api/admin/events/{event_id}/photographers/{user_id}')
    def unassign(event_id:str,user_id:str,user=Depends(admin)):
        db.run('DELETE FROM assignments WHERE event_id=? AND user_id=?',(event_id,user_id))
        audit(db,user['id'],'photographer.unassigned',event_id+':'+user_id)
        return {'ok':True}

    @app.post('/api/admin/users/{user_id}/disable')
    def disable(user_id:str,user=Depends(admin)):
        target=db.one('SELECT role FROM users WHERE id=?',(user_id,))
        if not target: raise HTTPException(404,'Compte introuvable.')
        if target['role']=='admin': raise HTTPException(409,'La désactivation des administrateurs exige une intervention opérateur.')
        with db.connect() as conn:
            conn.execute('UPDATE users SET disabled=1 WHERE id=?',(user_id,))
            conn.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            conn.execute('DELETE FROM api_keys WHERE user_id=?',(user_id,))
        audit(db,user['id'],'user.disabled',user_id)
        return {'ok':True}

    @app.post('/api/admin/users/{user_id}/enable')
    def enable(user_id:str,user=Depends(admin)):
        if not db.run('UPDATE users SET disabled=0 WHERE id=?',(user_id,)): raise HTTPException(404,'Compte introuvable.')
        audit(db,user['id'],'user.enabled',user_id)
        return {'ok':True}

    @app.post('/api/admin/mail/{mail_id}/retry')
    def retry_mail(mail_id:str,user=Depends(admin)):
        row=db.one('SELECT * FROM mail WHERE id=?',(mail_id,))
        if not row or row['status']!='failed' or not row['body']: raise HTTPException(409,'Email non relançable. Demandez un nouveau lien si nécessaire.')
        db.run("UPDATE mail SET status='queued',attempts=0,error=NULL,available=? WHERE id=?",(time.time(),mail_id))
        audit(db,user['id'],'mail.retried',mail_id)
        return {'ok':True}

    def page(title,description,content,path='/',index=True):
        title=html.escape(title); description=html.escape(description,quote=True)
        canonical=html.escape(app.state.base_url+path,quote=True)
        verification=html.escape(os.getenv('GOOGLE_SITE_VERIFICATION',''),quote=True)
        return HTMLResponse(f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{title}</title><meta name="description" content="{description}"><meta name="robots" content="{'index,follow' if index else 'noindex,nofollow'}"><link rel="canonical" href="{canonical}"><meta property="og:title" content="{title}"><meta property="og:description" content="{description}"><meta property="og:url" content="{canonical}"><meta property="og:type" content="website"><meta name="theme-color" content="#171a18"><meta name="google-site-verification" content="{verification}"><link rel="manifest" href="/manifest.webmanifest"><link rel="icon" href="/static/icon.svg" type="image/svg+xml"><link rel="stylesheet" href="/static/app.css"><script defer src="/static/app.js"></script></head><body><a class="skip" href="#main">Aller au contenu</a><header><a class="brand" href="/">alpi<span>cturia</span><i>✳</i></a><nav aria-label="Navigation principale"><a href="/app">Mes photos</a><a href="/photographer">Photographes</a><a href="/account" id="account-link">Mon compte</a></nav></header><main id="main">{content}</main><footer><span>Alpicturia · Les instants restent.</span><div><a href="/privacy">Confidentialité</a><a href="/help">Aide</a><a href="/account">Compte & données</a></div></footer><div id="toast" role="status" aria-live="polite"></div><dialog id="lightbox"><button id="close-lightbox" aria-label="Fermer la photo">✕</button><img alt="Photo de votre événement" id="lightbox-image"><p>Aperçu protégé · pincez pour zoomer sur mobile.</p></dialog></body></html>''')

    @app.get('/',response_class=HTMLResponse)
    def home():
        return page('Alpicturia — Retrouvez vos photos de festival','Un selfie pour retrouver vos photos d’événements. Un espace professionnel pour les photographes de festivals en Suisse.', '''<section class="hero"><div><p class="eyebrow">VOTRE FESTIVAL. VOS INSTANTS.</p><h1>Vous l’avez vécu.<br><em>Retrouvez-le.</em></h1><p class="intro">Choisissez votre événement, prenez un selfie et retrouvez les photos sur lesquelles vous apparaissez.</p><a class="button" href="/app">Retrouver mes photos <span>↗</span></a><p class="subtle">Une recherche personnelle, limitée à votre événement.</p></div><div class="hero-art" aria-hidden="true"><div class="art-label">LES INSTANTS RESTENT.</div><div class="frame"><span>✳</span><p>La musique s’arrête.<br>Les souvenirs continuent.</p></div><span class="art-small">ALPICTURIA / FESTIVALS / SUISSE</span></div></section><section class="steps"><article><b>01</b><h2>Votre événement</h2><p>Retrouvez le festival auquel vous avez participé.</p></article><article><b>02</b><h2>Votre selfie</h2><p>Une photo de face pour lancer votre recherche personnelle.</p></article><article><b>03</b><h2>Vos souvenirs</h2><p>Consultez les photos candidates dans une galerie privée.</p></article></section><section class="section"><p class="eyebrow">LES ÉVÉNEMENTS</p><h2>Où étiez-vous ?</h2><div id="public-events" class="event-grid"></div></section><section class="photographer-callout"><p class="eyebrow">DERRIÈRE L’OBJECTIF</p><h2>Vos images méritent<br>de trouver leur public.</h2><p>Importez vos séries depuis votre ordinateur et suivez leur traitement dans votre espace photographe.</p><a class="button secondary" href="/photographer">Espace photographe ↗</a></section>''')

    @app.get('/events/{slug}',response_class=HTMLResponse)
    def event_page(slug:str):
        event=db.one('SELECT * FROM events WHERE slug=? AND published=1',(slug,))
        if not event: raise HTTPException(404,'Événement introuvable.')
        return page(f"{event['title']} — Photos | Alpicturia",f"Retrouvez vos photos de {event['title']} à {event['location']} avec votre selfie.",f'''<section class="section"><p class="eyebrow">{html.escape(event['date'])} · {html.escape(event['location'])}</p><h1>{html.escape(event['title'])}</h1><p class="intro">{html.escape(event['description'])}</p><a class="button" href="/app?event={event['id']}">Retrouver mes photos ↗</a></section>''',f'/events/{slug}')

    @app.get('/app',response_class=HTMLResponse)
    @app.get('/photographer',response_class=HTMLResponse)
    @app.get('/admin',response_class=HTMLResponse)
    @app.get('/account',response_class=HTMLResponse)
    @app.get('/account/{action}',response_class=HTMLResponse)
    def shell(request:Request):
        return page('Mon espace — Alpicturia','Votre espace personnel Alpicturia.','<div id="workspace" class="section"><p role="status">Chargement de votre espace…</p></div>',request.url.path,False)

    @app.get('/privacy',response_class=HTMLResponse)
    def privacy():
        return page('Confidentialité — Alpicturia','Comment Alpicturia traite vos selfies, vos recherches et vos données.', '''<article class="prose section"><p class="eyebrow">VOS DONNÉES</p><h1>Une recherche personnelle.</h1><h2>Selfie et consentement</h2><p>Chaque recherche nécessite votre accord explicite. Votre selfie sert à chercher votre visage uniquement dans l’événement sélectionné. Il est supprimé après le traitement, y compris en cas d’échec. Aucun selfie n’est utilisé pour entraîner un modèle.</p><h2>Résultats et précision</h2><p>Les correspondances sont des photos candidates et peuvent être inexactes. Les résultats sont privés et expirent après sept jours. Une photographie de groupe peut montrer d’autres participants.</p><h2>Photographies et index facial</h2><p>Les photographes professionnels autorisés déposent les photos des événements. Les caractéristiques faciales extraites sont associées aux photos pour permettre la recherche. Supprimer une photo supprime son index et ses correspondances.</p><h2>Votre contrôle</h2><p>Depuis votre compte, exportez vos données, révoquez vos clés d’accès, supprimez une recherche ou votre compte. La suppression du compte retire ses données actives et ses photos s’il s’agit d’un compte photographe.</p><h2>Mesures d’audience</h2><p>Nous comptons les pages consultées sans cookie publicitaire ni identification des visiteurs. Les compteurs détaillés sont conservés 90 jours.</p><h2>Avant l’ouverture publique</h2><p>Les coordonnées du responsable de traitement, l’hébergement retenu, la durée de conservation des photographies et les conditions de vente seront publiés ici avant le lancement commercial.</p></article>''','/privacy')

    @app.get('/help',response_class=HTMLResponse)
    def help_page():
        return page('Aide — Alpicturia','Aide pour retrouver vos photos et utiliser l’espace photographe.', '''<article class="prose section"><h1>Un coup de main ?</h1><h2>Aucune photo trouvée ?</h2><p>Vérifiez l’événement et utilisez un selfie net, de face et bien éclairé, avec un seul visage. Certaines photos peuvent être en cours de traitement. La reconnaissance ne garantit pas de retrouver chaque photo.</p><h2>Photographes</h2><p>Créez un compte photographe et faites-vous assigner à un événement par l’administrateur. JPEG, PNG et WebP sont acceptés jusqu’à 25 Mo et 40 mégapixels par fichier. Les imports s’effectuent par trois fichiers simultanés. Les doublons de votre événement sont reconnus.</p><h2>Emails</h2><p>Consultez les courriers indésirables. Vous pouvez redemander un email de confirmation depuis votre compte.</p><h2>Achat et originaux</h2><p>La vente et la livraison des originaux aux festivaliers ne sont pas encore activées. Les galeries présentent des aperçus protégés.</p></article>''','/help')

    @app.get('/robots.txt')
    def robots():
        return Response(f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /account\nDisallow: /admin\nDisallow: /photographer\nDisallow: /app\nSitemap: {app.state.base_url}/sitemap.xml\n",media_type='text/plain')

    @app.get('/sitemap.xml')
    def sitemap():
        paths=['/','/help','/privacy']+['/events/'+e['slug'] for e in db.all('SELECT slug FROM events WHERE published=1')]
        xml='<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+html.escape(app.state.base_url+p)+'</loc></url>' for p in paths)+'</urlset>'
        return Response(xml,media_type='application/xml')

    @app.get('/sw.js')
    def service_worker():
        return FileResponse(STATIC/'sw.js',media_type='application/javascript',headers={'Cache-Control':'no-cache','Service-Worker-Allowed':'/'})

    @app.get('/manifest.webmanifest')
    def manifest():
        return JSONResponse({'name':'Alpicturia','short_name':'Alpicturia','start_url':'/app','scope':'/','display':'standalone','background_color':'#f5f4ef','theme_color':'#171a18','lang':'fr','icons':[{'src':'/static/icon.svg','sizes':'any','type':'image/svg+xml','purpose':'any'},{'src':'/static/icon-192.png','sizes':'192x192','type':'image/png','purpose':'any'},{'src':'/static/icon-512.png','sizes':'512x512','type':'image/png','purpose':'any maskable'}]},media_type='application/manifest+json')

    return app

DUMMY_PASSWORD=password_hash('dummy-password-never-used-for-login')
app=create_app()

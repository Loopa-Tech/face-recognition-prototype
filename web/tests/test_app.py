import io
import json
import re
import secrets
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote
from fastapi.testclient import TestClient
from PIL import Image
from alpicturia.app import create_app
from alpicturia.security import digest, enqueue, password_hash, uid
from alpicturia.worker import cleanup, run_once, send_mail


class FakeEngine:
    def encode(self,path): return [[0.1]*128]

class FailedEngine:
    def encode(self,path): raise RuntimeError('Moteur indisponible')


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app(self.tmp.name); self.db=self.app.state.db
        self.owner=self.client('admin','owner@example.com')
        self.photographer=self.client('photographer','photo@example.com')
        self.attendee=self.client('attendee','guest@example.com')
        self.other=self.client('attendee','other@example.com')
        self.event=self.owner.post('/api/admin/events',json={'title':'Festival Test','slug':'festival-test','location':'Lausanne','date':'2027-06-01','published':True}).json()['id']
        self.photo_user=self.db.one("SELECT id FROM users WHERE email='photo@example.com'")['id']
        self.owner.post(f'/api/admin/events/{self.event}/photographers',json={'user_id':self.photo_user})
        buffer=io.BytesIO(); Image.new('RGB',(120,120),'red').save(buffer,'JPEG'); self.image=buffer.getvalue()

    def tearDown(self): self.tmp.cleanup()

    def client(self,role,email,verified=True):
        client=TestClient(self.app)
        user_id=uid(); raw=secrets.token_urlsafe(32)
        self.db.run('INSERT INTO users(id,email,name,password,role,verified,created) VALUES(?,?,?,?,?,?,?)',(user_id,email,'Test User',password_hash('ValidPassword123!'),role,int(verified),time.time()))
        self.db.run('INSERT INTO sessions VALUES(?,?,?)',(digest(raw),user_id,time.time()+3600))
        client.cookies.set('alpi_session',raw)
        return client

    def upload(self,event=None,client=None,data=None):
        return (client or self.photographer).post(f'/api/events/{event or self.event}/photos',content=data or self.image,headers={'Content-Type':'image/jpeg','X-Filename':'Photo%20%C3%A9t%C3%A9.jpg'})

    def search(self,client=None,event=None):
        return (client or self.attendee).post(f'/api/events/{event or self.event}/searches',content=self.image,headers={'X-Consent-Version':'selfie-search-v1'})

    def mail_token(self,user_id,kind):
        row=self.db.one('SELECT body FROM mail WHERE user_id=? ORDER BY created DESC',(user_id,))
        return re.search(r'#token=([\w-]+)',row['body'])[1]

    def test_public_and_seo_private_pages_excluded(self):
        c=TestClient(self.app)
        self.assertEqual(c.get('/').status_code,200)
        sitemap=c.get('/sitemap.xml').text
        self.assertIn('/events/festival-test',sitemap)
        self.assertNotIn('/admin',sitemap)
        self.assertIn('noindex',c.get('/app').headers['x-robots-tag'])
        self.assertEqual(c.get('/api/admin/overview').status_code,401)
        self.assertIn('Content-Security-Policy',c.get('/').headers)
        self.assertIn('Festival Test',c.get('/events/festival-test').text)

    def test_signup_verification_single_use_and_login_errors(self):
        c=TestClient(self.app)
        signup=c.post('/api/auth/signup',json={'name':'Alice','email':'ALICE@example.com','password':'StrongPassword123!'})
        self.assertEqual(signup.status_code,201)
        self.assertEqual(signup.json()['email'],'alice@example.com')
        self.assertEqual(c.get('/api/searches').status_code,403)
        token=self.mail_token(signup.json()['id'],'verify')
        self.assertEqual(c.post('/api/auth/verify',json={'token':token}).status_code,200)
        self.assertEqual(c.post('/api/auth/verify',json={'token':token}).status_code,400)
        self.assertEqual(c.get('/api/searches').status_code,200)
        c.post('/api/auth/logout')
        self.assertEqual(c.get('/api/me').status_code,401)
        self.assertEqual(c.post('/api/auth/login',json={'email':'alice@example.com','password':'incorrect'}).status_code,401)
        self.assertEqual(c.post('/api/auth/login',json={'email':'alice@example.com','password':'StrongPassword123!'}).status_code,200)
        self.assertTrue(c.cookies.get('alpi_session'))

    def test_no_admin_signup(self):
        c=TestClient(self.app)
        self.assertEqual(c.post('/api/auth/signup',json={'name':'Hacker','email':'hacker@example.com','password':'StrongPassword123!','role':'admin'}).status_code,422)

    def test_password_reset_revokes_sessions_and_api_keys(self):
        self.attendee.post('/api/keys',json={'name':'Agent','scopes':['read']})
        self.attendee.post('/api/auth/forgot',json={'email':'guest@example.com'})
        user=self.db.one("SELECT id FROM users WHERE email='guest@example.com'")
        token=self.mail_token(user['id'],'reset')
        c=TestClient(self.app)
        self.assertEqual(c.post('/api/auth/reset',json={'token':token,'password':'NewPassword123!'}).status_code,200)
        self.assertEqual(self.attendee.get('/api/me').status_code,401)
        self.assertEqual(self.db.one('SELECT count(*) AS n FROM api_keys WHERE user_id=?',(user['id'],))['n'],0)
        self.assertEqual(c.post('/api/auth/reset',json={'token':token,'password':'AgainPassword123!'}).status_code,400)
        self.assertEqual(c.post('/api/auth/login',json={'email':'guest@example.com','password':'NewPassword123!'}).status_code,200)

    def test_cross_origin_writes_rejected(self):
        self.assertEqual(self.attendee.post('/api/auth/logout',headers={'Origin':'https://attacker.example'}).status_code,403)
        self.assertEqual(self.attendee.post('/api/auth/logout',headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)

    def test_upload_permissions_validation_duplicates_and_filename(self):
        self.assertEqual(self.upload(client=self.attendee).status_code,403)
        outsider=self.client('photographer','outsider@example.com')
        self.assertEqual(self.upload(client=outsider).status_code,403)
        self.assertEqual(self.upload(data=b'not an image').status_code,422)
        first=self.upload(); self.assertEqual(first.status_code,201)
        again=self.upload(); self.assertTrue(again.json()['duplicate'])
        self.assertEqual(first.json()['id'],again.json()['id'])
        row=self.db.one('SELECT * FROM photos WHERE id=?',(first.json()['id'],))
        self.assertEqual(row['filename'],'Photo été.jpg')
        self.assertEqual(self.db.one('SELECT count(*) AS n FROM jobs')['n'],1)

    def test_separate_events_allow_same_image(self):
        e=self.owner.post('/api/admin/events',json={'title':'Other event','slug':'other-event','location':'Vevey','date':'2027-07-01','published':True}).json()['id']
        self.owner.post(f'/api/admin/events/{e}/photographers',json={'user_id':self.photo_user})
        self.assertNotEqual(self.upload().json()['id'],self.upload(event=e).json()['id'])

    def test_end_to_end_matching_private_results_and_selfie_deleted(self):
        p=self.upload().json()['id']; run_once(self.db,FakeEngine())
        s=self.search().json()['id']
        item=self.db.one('SELECT * FROM searches WHERE id=?',(s,)); selfie=self.db.root/item['path']
        self.assertTrue(selfie.exists()); run_once(self.db,FakeEngine())
        self.assertFalse(selfie.exists())
        result=self.attendee.get('/api/searches/'+s)
        self.assertEqual(result.json()['status'],'ready'); self.assertEqual(result.json()['photos'][0]['id'],p)
        self.assertEqual(self.other.get('/api/searches/'+s).status_code,404)
        self.assertEqual(self.other.get('/api/photos/'+p+'/preview').status_code,404)
        self.assertEqual(self.attendee.get('/api/photos/'+p+'/preview').status_code,200)
        self.assertEqual(self.attendee.get('/api/photos/'+p+'/original').status_code,404)
        self.assertEqual(self.photographer.get('/api/photos/'+p+'/original').status_code,200)
        self.assertEqual(self.db.one('SELECT path FROM searches WHERE id=?',(s,))['path'],None)

    def test_search_consent_and_event_isolation(self):
        self.upload(); run_once(self.db,FakeEngine())
        e=self.owner.post('/api/admin/events',json={'title':'No Photos','slug':'no-photos','location':'Sion','date':'2027-07-01','published':True}).json()['id']
        denied=self.attendee.post(f'/api/events/{e}/searches',content=self.image)
        self.assertEqual(denied.status_code,422)
        s=self.search(event=e).json()['id'];run_once(self.db,FakeEngine())
        self.assertEqual(self.attendee.get('/api/searches/'+s).json()['photos'],[])

    def test_exactly_one_face_required(self):
        class TwoFaces:
            def encode(self,path): return [[.1]*128,[.2]*128]
        s=self.search().json()['id'];run_once(self.db,TwoFaces())
        row=self.db.one('SELECT * FROM searches WHERE id=?',(s,))
        self.assertEqual(row['status'],'failed');self.assertIsNone(row['path'])
        self.assertIn('exactement un visage',row['error'])

    def test_engine_failure_visible_and_photo_retry(self):
        p=self.upload().json()['id'];run_once(self.db,FailedEngine())
        self.assertEqual(self.db.one('SELECT status FROM photos WHERE id=?',(p,))['status'],'failed')
        self.assertEqual(self.photographer.post('/api/photos/'+p+'/retry').status_code,200)
        run_once(self.db,FakeEngine())
        self.assertEqual(self.db.one('SELECT status FROM photos WHERE id=?',(p,))['status'],'ready')

    def test_crashed_job_lease_is_recovered(self):
        self.upload()
        self.db.run("UPDATE jobs SET status='running',lease_until=?",(time.time()-10,))
        self.assertTrue(run_once(self.db,FakeEngine()))
        self.assertEqual(self.db.one('SELECT status FROM jobs')['status'],'done')

    def test_expiry_immediately_blocks_previews_then_purges(self):
        p=self.upload().json()['id'];run_once(self.db,FakeEngine())
        s=self.search().json()['id'];run_once(self.db,FakeEngine())
        self.db.run('UPDATE searches SET expires=? WHERE id=?',(time.time()-1,s))
        self.assertEqual(self.attendee.get('/api/photos/'+p+'/preview').status_code,404)
        self.assertEqual(self.attendee.get('/api/searches/'+s).json()['photos'],[])
        cleanup(self.db)
        self.assertEqual(self.db.one('SELECT count(*) AS n FROM matches')['n'],0)

    def test_unpublishing_hides_page_results_and_preview(self):
        p=self.upload().json()['id'];run_once(self.db,FakeEngine())
        s=self.search().json()['id'];run_once(self.db,FakeEngine())
        self.db.run('UPDATE events SET published=0 WHERE id=?',(self.event,))
        self.assertEqual(self.attendee.get('/api/photos/'+p+'/preview').status_code,404)
        self.assertEqual(self.attendee.get('/api/searches/'+s).json()['photos'],[])
        self.assertEqual(TestClient(self.app).get('/events/festival-test').status_code,404)
        self.assertNotIn('/events/festival-test',self.attendee.get('/sitemap.xml').text)

    def test_api_key_scopes_revocation_and_no_privilege_escalation(self):
        key=self.attendee.post('/api/keys',json={'name':'Read Agent','scopes':['read']}).json()
        c=TestClient(self.app); c.headers['Authorization']='Bearer '+key['token']
        self.assertEqual(c.get('/api/me').status_code,200)
        self.assertEqual(c.get('/api/admin/overview').status_code,403)
        self.assertEqual(c.delete('/api/searches/nope').status_code,403)
        self.assertEqual(self.attendee.post('/api/keys',json={'name':'Admin Agent','scopes':['admin']}).status_code,403)
        self.assertEqual(c.post('/api/keys',json={'name':'Nested Key','scopes':['read']}).status_code,403)
        self.attendee.delete('/api/keys/'+key['id'])
        self.assertEqual(c.get('/api/me').status_code,401)

    def test_disabled_user_loses_session_and_tokens(self):
        self.owner.post('/api/admin/users/'+self.photo_user+'/disable')
        self.assertEqual(self.photographer.get('/api/me').status_code,401)
        self.assertEqual(self.owner.post('/api/admin/users/'+self.photo_user+'/enable').status_code,200)
        self.assertEqual(self.photographer.get('/api/me').status_code,401)

    def test_admin_real_counts_and_secrets_excluded(self):
        self.upload()
        overview=self.owner.get('/api/admin/overview').json()
        self.assertEqual(overview['counts']['photos'],1)
        self.assertGreater(overview['counts']['storage_bytes'],0)
        self.assertEqual(self.attendee.get('/api/admin/data/users').status_code,403)
        for table in ('users','mail','searches','photos','jobs','audit'):
            rows=self.owner.get('/api/admin/data/'+table).json()['items']
            for row in rows:
                for forbidden in ('password','token','body','encoding','path'):
                    self.assertNotIn(forbidden,row)
        self.assertEqual(self.owner.get('/api/admin/data/sqlite_master').status_code,404)

    def test_full_csv_export_and_formula_protection(self):
        for n in range(110):
            self.db.run('INSERT INTO audit(actor_id,action,target,created) VALUES(?,?,?,?)',(None,'=HYPERLINK("evil")',str(n),time.time()))
        response=self.owner.get('/api/admin/export/audit')
        import csv
        rows=list(csv.DictReader(io.StringIO(response.text)))
        self.assertGreater(len(rows),100)
        self.assertTrue(any(r['action'].startswith("'=HYPERLINK") for r in rows))

    def test_account_deletion_purges_owned_data_and_objects(self):
        p=self.upload().json()['id'];run_once(self.db,FakeEngine())
        files=self.db.one('SELECT path,preview FROM photos WHERE id=?',(p,))
        self.assertEqual(self.photographer.delete('/api/me').status_code,400)
        self.assertEqual(self.photographer.delete('/api/me',headers={'X-Confirm-Delete':'DELETE'}).status_code,200)
        self.assertIsNone(self.db.one('SELECT id FROM photos WHERE id=?',(p,)))
        for path in files.values(): self.assertFalse((self.db.root/path).exists())
        self.assertEqual(self.db.one('SELECT count(*) AS n FROM faces')['n'],0)
        self.assertEqual(self.photographer.get('/api/me').status_code,401)

    def test_photo_delete_cascades_matches_and_files(self):
        p=self.upload().json()['id'];run_once(self.db,FakeEngine())
        self.search();run_once(self.db,FakeEngine())
        self.assertEqual(self.attendee.delete('/api/photos/'+p).status_code,403)
        self.assertEqual(self.photographer.delete('/api/photos/'+p).status_code,200)
        self.assertEqual(self.db.one('SELECT count(*) AS n FROM matches')['n'],0)
        self.assertEqual(self.db.one('SELECT count(*) AS n FROM faces')['n'],0)

    def test_mail_not_falsely_marked_sent_without_smtp(self):
        self.attendee.post('/api/auth/forgot',json={'email':'guest@example.com'})
        with patch.dict('os.environ',{'SMTP_HOST':''}): send_mail(self.db)
        self.assertEqual(self.db.one('SELECT status FROM mail')['status'],'queued')

    def test_rate_limit(self):
        c=TestClient(self.app)
        for _ in range(20): c.post('/api/auth/login',json={'email':'absent@example.com','password':'bad'})
        self.assertEqual(c.post('/api/auth/login',json={'email':'absent@example.com','password':'bad'}).status_code,429)

    def test_image_size_limit(self):
        self.assertEqual(self.photographer.post(f'/api/events/{self.event}/photos',content=b'1',headers={'Content-Length':str(26*1024*1024)}).status_code,413)

if __name__=='__main__': unittest.main()

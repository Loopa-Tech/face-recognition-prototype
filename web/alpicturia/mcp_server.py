"""Official MCP SDK adapter; every operation goes through the permissioned API."""
import base64
import binascii
import os
from typing import Literal
from urllib.parse import quote
import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

API_URL=os.getenv('ALPICTURIA_API_URL','http://127.0.0.1:8000').rstrip('/')
TRANSPORT=os.getenv('MCP_TRANSPORT','stdio')
ALLOWED_HOSTS=os.getenv('MCP_ALLOWED_HOSTS','localhost:*,127.0.0.1:*').split(',')
mcp=FastMCP('Alpicturia',instructions='Manage your own Alpicturia data. API keys enforce user roles and read/write/admin scopes. Selfie search requires explicit user consent; use only the user’s own selfie. Photo uploads require event assignment. Results are candidates, not guaranteed identities.',host=os.getenv('MCP_HOST','127.0.0.1'),port=int(os.getenv('MCP_PORT','8001')),json_response=True,stateless_http=True,max_request_body_size=36*1024*1024,transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,allowed_hosts=ALLOWED_HOSTS,allowed_origins=os.getenv('MCP_ALLOWED_ORIGINS','http://localhost:*,http://127.0.0.1:*').split(',')))


def bearer(ctx:Context):
    if TRANSPORT=='stdio':
        token=os.getenv('ALPICTURIA_API_TOKEN','')
    else:
        request=ctx.request_context.request
        auth=request.headers.get('authorization','') if request else ''
        token=auth[7:] if auth.startswith('Bearer ') else ''
    if not token:
        raise ValueError('A personal Alpicturia API key is required.')
    return token


async def call(ctx,method,path,body=None,content=None,headers=None):
    async with httpx.AsyncClient(base_url=API_URL,timeout=180) as client:
        response=await client.request(method,path,json=body,content=content,headers={'Authorization':'Bearer '+bearer(ctx),**(headers or {})})
        if response.is_error:
            detail=response.json().get('detail','API request failed')
            raise ValueError(str(detail))
        return response.json() if 'application/json' in response.headers.get('content-type','') else response.text


def image_bytes(image_base64):
    if len(image_base64)>35*1024*1024:
        raise ValueError('Image exceeds 25 MiB.')
    try:
        result=base64.b64decode(image_base64,validate=True)
    except (ValueError,binascii.Error) as exc:
        raise ValueError('Invalid base64 image.') from exc
    if len(result)>25*1024*1024:
        raise ValueError('Image exceeds 25 MiB.')
    return result


@mcp.tool()
async def account(ctx:Context)->dict:
    """Read the current account and role."""
    return await call(ctx,'GET','/api/me')

@mcp.tool()
async def list_events(ctx:Context,photographer:bool=False)->list:
    """List published events, or events assigned to the current photographer."""
    return await call(ctx,'GET','/api/photographer/events' if photographer else '/api/events')

@mcp.tool()
async def list_photos(ctx:Context,event_id:str,offset:int=0,limit:int=50)->dict:
    """Paginate photos owned by the current photographer in an assigned event."""
    return await call(ctx,'GET',f'/api/events/{quote(event_id,safe="")}/photos?offset={offset}&limit={limit}')

@mcp.tool()
async def upload_photo(ctx:Context,event_id:str,filename:str,image_base64:str)->dict:
    """Upload one JPEG/PNG/WebP photo (base64). Repeat for a batch; duplicate files are idempotent per photographer and event."""
    return await call(ctx,'POST',f'/api/events/{quote(event_id,safe="")}/photos',content=image_bytes(image_base64),headers={'Content-Type':'application/octet-stream','X-Filename':quote(filename,safe='')})

@mcp.tool()
async def retry_photo(ctx:Context,photo_id:str)->dict:
    """Retry a failed photo indexing job owned by the current photographer; admin may retry any."""
    return await call(ctx,'POST',f'/api/photos/{quote(photo_id,safe="")}/retry')

@mcp.tool()
async def delete_photo(ctx:Context,photo_id:str)->dict:
    """Permanently delete an owned photo and its face index and matches. Requires user intent to delete."""
    return await call(ctx,'DELETE',f'/api/photos/{quote(photo_id,safe="") }')

@mcp.tool()
async def search_selfie(ctx:Context,event_id:str,selfie_base64:str,explicit_consent:bool)->dict:
    """Search the selected event with the user's own selfie, only with explicit consent. Selfie deleted after processing; results expire in seven days."""
    if explicit_consent is not True:
        raise ValueError('Explicit user consent is required for facial search.')
    return await call(ctx,'POST',f'/api/events/{quote(event_id,safe="")}/searches',content=image_bytes(selfie_base64),headers={'Content-Type':'application/octet-stream','X-Consent-Version':'selfie-search-v1'})

@mcp.tool()
async def list_searches(ctx:Context)->list:
    """Read the current user's recent search history."""
    return await call(ctx,'GET','/api/searches')

@mcp.tool()
async def search_results(ctx:Context,search_id:str)->dict:
    """Read the user's own search status and matching photo IDs."""
    return await call(ctx,'GET','/api/searches/'+quote(search_id,safe=''))

@mcp.tool()
async def delete_search(ctx:Context,search_id:str)->dict:
    """Delete the user's own search and results. Requires user intent to delete."""
    return await call(ctx,'DELETE','/api/searches/'+quote(search_id,safe=''))

@mcp.tool()
async def export_my_data(ctx:Context)->dict:
    """Export the current user's profile, searches and owned photo metadata."""
    return await call(ctx,'GET','/api/me/export')

@mcp.tool()
async def list_api_keys(ctx:Context)->list:
    """List the user's API key metadata; secret values are never returned."""
    return await call(ctx,'GET','/api/keys')

@mcp.tool()
async def revoke_api_key(ctx:Context,key_id:str)->dict:
    """Revoke one of the user's API keys. Requires user intent to revoke."""
    return await call(ctx,'DELETE','/api/keys/'+quote(key_id,safe=''))

@mcp.tool()
async def admin_overview(ctx:Context)->dict:
    """Admin only: real database counts, storage, traffic and processing/email configuration."""
    return await call(ctx,'GET','/api/admin/overview')

@mcp.tool()
async def admin_records(ctx:Context,table:Literal['users','events','photos','searches','jobs','mail','audit','assignments'],offset:int=0,limit:int=50,query:str='')->dict:
    """Admin only: paginated operational data, excluding passwords, tokens, email bodies and face vectors."""
    return await call(ctx,'GET',f'/api/admin/data/{table}?offset={offset}&limit={limit}&q={quote(query,safe="")}')

@mcp.tool()
async def admin_export(ctx:Context,table:Literal['users','events','photos','searches','jobs','mail','audit','assignments'])->str:
    """Admin only: CSV export of all operational rows, excluding secrets and face vectors."""
    return await call(ctx,'GET','/api/admin/export/'+table)

@mcp.tool()
async def save_event(ctx:Context,title:str,slug:str,location:str,date:str,description:str='',published:bool=False,event_id:str|None=None)->dict:
    """Admin only: create or update an event. Published events appear in the public site and sitemap."""
    return await call(ctx,'PUT' if event_id else 'POST','/api/admin/events'+('/'+quote(event_id,safe='') if event_id else ''),body={'title':title,'slug':slug,'location':location,'date':date,'description':description,'published':published})

@mcp.tool()
async def assign_photographer(ctx:Context,event_id:str,user_id:str,remove:bool=False)->dict:
    """Admin only: grant or remove photographer upload permission for an event."""
    path=f'/api/admin/events/{quote(event_id,safe="")}/photographers'
    return await call(ctx,'DELETE' if remove else 'POST',path+('/'+quote(user_id,safe='') if remove else ''),body=None if remove else {'user_id':user_id})

@mcp.tool()
async def set_account_access(ctx:Context,user_id:str,disabled:bool)->dict:
    """Admin only: disable or re-enable a non-admin account. Disabling revokes its sessions and API keys."""
    return await call(ctx,'POST',f'/api/admin/users/{quote(user_id,safe="")}/'+('disable' if disabled else 'enable'))

@mcp.tool()
async def retry_email(ctx:Context,mail_id:str)->dict:
    """Admin only: retry an unexpired failed email without exposing its one-time link."""
    return await call(ctx,'POST','/api/admin/mail/'+quote(mail_id,safe='')+'/retry')


class RequireBearer:
    def __init__(self,app): self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[])); auth=headers.get(b'authorization',b'').decode()
        if not auth.startswith('Bearer '):
            from starlette.responses import JSONResponse
            return await JSONResponse({'error':'A personal Alpicturia bearer key is required.'},401)(scope,receive,send)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                check=await client.get(API_URL+'/api/me',headers={'Authorization':auth})
            allowed=check.status_code==200
        except httpx.HTTPError:
            from starlette.responses import JSONResponse
            return await JSONResponse({'error':'Alpicturia API unavailable.'},503)(scope,receive,send)
        if not allowed:
            from starlette.responses import JSONResponse
            return await JSONResponse({'error':'Invalid or expired Alpicturia key.'},401)(scope,receive,send)
        return await self.app(scope,receive,send)


def main():
    if TRANSPORT=='stdio':
        mcp.run(transport='stdio')
    elif TRANSPORT=='streamable-http':
        import uvicorn
        uvicorn.run(RequireBearer(mcp.streamable_http_app()),host=os.getenv('MCP_HOST','127.0.0.1'),port=int(os.getenv('MCP_PORT','8001')))
    else:
        raise RuntimeError('MCP_TRANSPORT must be stdio or streamable-http.')

if __name__=='__main__': main()

import asyncio
import base64
import io
import os
import secrets
import tempfile
import time
import unittest
from unittest.mock import patch
import httpx
from PIL import Image
from mcp.shared.memory import create_connected_server_and_client_session
from alpicturia.app import create_app
from alpicturia.security import digest, uid
from alpicturia import mcp_server as server


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.app=create_app(self.tmp.name); self.db=self.app.state.db
        self.user_id=uid();self.token=secrets.token_urlsafe(32)
        self.db.run('INSERT INTO users(id,email,name,password,role,verified,created) VALUES(?,?,?,?,?,?,?)',(self.user_id,'mcp@example.com','Agent Tester','unused','attendee',1,time.time()))
        self.db.run('INSERT INTO api_keys VALUES(?,?,?,?,?,?,?)',(uid(),digest(self.token),self.user_id,'Test Key','["read","write"]',time.time(),time.time()+3600))
        real_client=httpx.AsyncClient
        self.factory=lambda **kwargs:real_client(transport=httpx.ASGITransport(app=self.app),**kwargs)
        self.http_patch=patch.object(server.httpx,'AsyncClient',self.factory);self.http_patch.start()
        self.env_patch=patch.dict(os.environ,{'ALPICTURIA_API_TOKEN':self.token});self.env_patch.start()

    async def asyncTearDown(self):
        self.http_patch.stop();self.env_patch.stop();self.tmp.cleanup()

    async def test_protocol_handshake_tool_listing_and_authenticated_account(self):
        async with create_connected_server_and_client_session(server.mcp) as client:
            tools=await client.list_tools()
            self.assertEqual(len(tools.tools),20)
            result=await client.call_tool('account',{})
            self.assertFalse(result.isError)
            self.assertIn('mcp@example.com',str(result.content))

    async def test_admin_tools_cannot_escalate_attendee(self):
        self.db.run('UPDATE api_keys SET scopes=?',('["read","write","admin"]',))
        async with create_connected_server_and_client_session(server.mcp) as client:
            result=await client.call_tool('admin_overview',{})
            self.assertTrue(result.isError)
            self.assertIn('administration',str(result.content))

    async def test_selfie_requires_explicit_consent(self):
        async with create_connected_server_and_client_session(server.mcp) as client:
            result=await client.call_tool('search_selfie',{'event_id':'event','selfie_base64':'YWJj','explicit_consent':False})
            self.assertTrue(result.isError)
            self.assertIn('consent',str(result.content))

    async def test_write_blocked_by_readonly_key(self):
        self.db.run('UPDATE api_keys SET scopes=?',('["read"]',))
        async with create_connected_server_and_client_session(server.mcp) as client:
            result=await client.call_tool('delete_search',{'search_id':'anything'})
            self.assertTrue(result.isError)
            self.assertIn('clé',str(result.content))

    async def test_revoked_key_denied(self):
        self.db.run('DELETE FROM api_keys')
        async with create_connected_server_and_client_session(server.mcp) as client:
            result=await client.call_tool('account',{})
            self.assertTrue(result.isError)
            self.assertIn('Connectez',str(result.content))

    async def test_invalid_base64_rejected(self):
        with self.assertRaisesRegex(ValueError,'base64'):
            server.image_bytes('not a base64 picture!')

if __name__=='__main__':unittest.main()

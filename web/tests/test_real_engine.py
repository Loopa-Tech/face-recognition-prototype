"""Opt-in engine wiring check; supplied photo never enters source or test output."""
import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from alpicturia.app import create_app
from alpicturia.security import digest
from alpicturia.worker import FaceEngine, run_once

@unittest.skipUnless(os.getenv('ALPICTURIA_FACE_TEST_IMAGE'),'Set ALPICTURIA_FACE_TEST_IMAGE to a consented, single-face test image to run the real engine check.')
class RealEngineTest(unittest.TestCase):
    def test_real_photo_index_selfie_and_private_match(self):
        data=Path(os.environ['ALPICTURIA_FACE_TEST_IMAGE']).read_bytes()
        with tempfile.TemporaryDirectory() as root:
            app=create_app(root);db=app.state.db;now=time.time()
            for user_id,role in [('admin','admin'),('guest','attendee')]:
                db.run('INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?)',(user_id,user_id+'@example.com','Test','unused',role,1,0,now,None))
                db.run('INSERT INTO sessions VALUES(?,?,?)',(digest(user_id+'-test-session'),user_id,now+3600))
            owner=TestClient(app);owner.cookies.set('alpi_session','admin-test-session')
            guest=TestClient(app);guest.cookies.set('alpi_session','guest-test-session')
            event=owner.post('/api/admin/events',json={'title':'Engine Test','slug':'engine-test','date':'2027-01-01','location':'Test','published':True}).json()['id']
            photo=owner.post(f'/api/events/{event}/photos',content=data,headers={'X-Filename':'test.jpg'}).json()['id']
            run_once(db,FaceEngine())
            search=guest.post(f'/api/events/{event}/searches',content=data,headers={'X-Consent-Version':'selfie-search-v1'}).json()['id']
            run_once(db,FaceEngine())
            result=guest.get('/api/searches/'+search).json()
            self.assertEqual(result['status'],'ready')
            self.assertEqual([p['id'] for p in result['photos']],[photo])
            self.assertEqual(guest.get('/api/photos/'+photo+'/preview').status_code,200)
            self.assertIsNone(db.one('SELECT path FROM searches WHERE id=?',(search,))['path'])
            self.assertEqual(list((db.root/'selfies').iterdir()),[])

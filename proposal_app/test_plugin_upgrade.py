"""Binding, recovery and fixed-review authority using isolated databases."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from uuid import uuid4
from proposal_app import plugin_site as plugin, server

class PluginUpgradeTest(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'db.sqlite'
        server.init_db(self.path)
        self.db=server.connect(self.path)
        self.addCleanup(self.db.close)
        plugin.init_schema(self.db)
        self.student=dict(self.db.execute("SELECT * FROM users WHERE id='U2'").fetchone())
        self.teacher=dict(self.db.execute("SELECT * FROM users WHERE id='U1'").fetchone())
        self.pid=self.db.execute("SELECT id FROM projects WHERE student='U2'").fetchone()[0]
        self.card=server.project_for(self.db,self.student,self.pid)
        self.browser=SimpleNamespace(headers={},server=SimpleNamespace(plugin_origin='https://school.example'))
        self.device=SimpleNamespace(headers={'Authorization':'Bearer device'})
        self.db.execute('INSERT INTO plugin_devices VALUES (?,?,?)',(plugin.digest('device'),'U2',9999999999))
        self.hash='a'*64

    def entry(self,**body):
        return plugin.entry(self.browser,self.db,self.card,self.student,dict(workspace_hash=self.hash,**body))

    def bind(self,entry,thread=None,hash=None):
        body=dict(stage_session=entry['stage_session'],thread=thread or str(uuid4()),workspace_hash=hash or self.hash)
        row,thread=plugin.authorize_binding(self.device,self.db,body,True)
        if row['predecessor'] and not row['thread']:
            token='restore'
            self.db.execute('INSERT OR REPLACE INTO plugin_restores VALUES (?,?,?,?)',(row['key'],plugin.digest(token),thread,plugin.digest(row['card'])))
        else:token=None
        return body,plugin.bind_session(self.db,row,thread,token)

    def test_repeat_entry_atomic_claim_and_recovery_keeps_archive_authority(self):
        first=self.entry()
        self.assertEqual(first['stage_session'],self.entry()['stage_session'])
        body,lease=self.bind(first)
        self.assertEqual(self.entry()['thread_id'],body['thread'])
        with self.assertRaises(plugin.PilotError):self.bind(first)
        with self.assertRaises(plugin.PilotError):self.bind(first,body['thread'],'b'*64)
        recovered=self.entry(recovery=True)
        self.assertIsNone(recovered['thread_id'])
        self.assertEqual(recovered['stage_session'],self.entry(recovery=True)['stage_session'])
        candidate=dict(stage_session=recovered['stage_session'],thread=str(uuid4()),workspace_hash=self.hash)
        pending,thread=plugin.authorize_binding(self.device,self.db,candidate,True)
        with self.assertRaises(plugin.PilotError):plugin.bind_session(self.db,pending,thread)
        plugin.validate_lease(self.db,plugin.digest(lease['token']),True)
        self.bind(recovered)
        with self.assertRaises(plugin.PilotError):plugin.validate_lease(self.db,plugin.digest(lease['token']),True)
        row,_=plugin.authorize_binding(self.device,self.db,body,False)
        payload=dict(turn=str(uuid4()),complete=True,messages=[dict(id='u1',role='user',text='原文\n末段',time='2026-11-20'),dict(id='a1',role='assistant',text='完整回复',time='2026-11-20')])
        self.assertTrue(plugin.receive(self.db,row,payload)['saved'])
        self.assertEqual(len(plugin.discussions(self.db,self.pid)[0]),1)
        self.assertEqual(self.entry()['stage_session'],recovered['stage_session'])

    def test_teacher_fixed_version_and_role_scoping(self):
        self.card.update(status='review',submitted_deliverable={'id':'fixed','revision':1})
        self.db.execute('UPDATE projects SET card=? WHERE id=?',(json.dumps(self.card),self.pid))
        self.db.execute("UPDATE plugin_devices SET user='U1'")
        first=plugin.entry(self.browser,self.db,self.card,self.teacher,{'workspace_hash':self.hash})
        body,lease=self.bind(first)
        self.assertEqual(lease['role'],'teacher')
        self.assertIsNotNone(self.db.execute('SELECT * FROM scoped_sessions WHERE token=?',(plugin.digest(lease['token']),)).fetchone())
        plugin.validate_lease(self.db,plugin.digest(lease['token']),True)
        with self.assertRaises(plugin.PilotError):plugin.handle(self.device,self.db,'archive',body,None)
        self.card['submitted_deliverable']['revision']=2
        self.db.execute('UPDATE projects SET card=? WHERE id=?',(json.dumps(self.card),self.pid))
        with self.assertRaises(plugin.PilotError):plugin.validate_lease(self.db,plugin.digest(lease['token']),True)
        next_entry=plugin.entry(self.browser,self.db,self.card,self.teacher,{'workspace_hash':self.hash})
        self.assertNotEqual(first['stage_session'],next_entry['stage_session'])

if __name__=='__main__':unittest.main()

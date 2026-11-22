"""E initial-draft recovery uses one new writer and the same native thread."""
import json,tempfile,unittest
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock,patch
from proposal_app.coach_launcher import CoachLauncher

class ETimeoutRecovery(unittest.TestCase):
    def scenario(self,second='completed',stage=5,existing=False,retries=1,role='student'):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'connection.json').write_text('{"server":"http://localhost:8767"}')
            ws=MagicMock();ws.visible.return_value=root
            launcher=CoachLauncher(root,False,ws);launcher.config_role=role;launcher.running.add(('U','P'))
            rpcs=[];requests=[];published=[];tid='11111111-1111-4111-8111-111111111111'
            def connect(*args,**kwargs):
                if rpcs:rpcs[-1].close.assert_called_once()
                index=len(rpcs);rpc=MagicMock();rpc.rows=Queue();rpcs.append(rpc)
                def receive(raw):
                    req=json.loads(raw);requests.append((index,req))
                    if req.get('id')==2:rpc.rows.put({'id':2,'result':{'thread':{'id':tid,'projectId':'native'}}})
                    elif req.get('method')=='turn/start':
                        rpc.rows.put({'id':3,'result':{}})
                        if index==0:
                            rpc.rows.put({'method':'item/completed','params':{'item':{'type':'mcpToolCall','tool':'proposal_read_project','status':'completed'}}})
                        elif second!='timeout':
                            rpc.rows.put({'method':'turn/completed','params':{'turn':{'status':second,'items':[{'type':'agentMessage','text':'已重读保存结果，复用原稿，请本人核对。'}]}}})
                rpc.process.stdin.write.side_effect=receive
                return {'status':'ready','project_id':'native','_rpc':rpc}
            original=launcher.save
            def save(folder,result):
                published.append(result.copy())
                if result.get('phase')=='recovering_timeout':
                    self.assertIn(('U','P'),launcher.running);rpcs[-1].close.assert_called_once()
                original(folder,result)
            config=dict(model='gpt-6.1-sol',reasoning_effort='low',prepare_timeout_seconds=.02,e_draft_timeout_retries=retries)
            card=dict(id='P',student_name='模拟学生',current_step=stage,steps=[{} for _ in range(6)],research={'deliverables':[{'id':'old'}] if existing else []})
            with patch('proposal_app.coach_launcher.load_launch_config',return_value=config),patch('proposal_app.coach_launcher.install_skill',return_value=Path('skills/research-proposal-coach')),patch('proposal_app.desktop_workspace.ensure_workspace_project',side_effect=connect),patch.object(launcher,'save',side_effect=save):
                launcher.run(('U','P'),root,root,'codex',card)
            self.assertNotIn(('U','P'),launcher.running)
            for rpc in rpcs:rpc.close.assert_called_once()
            return json.loads((root/'conversation.json').read_text('utf-8')),requests,published

    def test_initial_E_timeout_recovers_without_transient_error_or_new_thread(self):
        result,requests,published=self.scenario()
        self.assertEqual(result['status'],'ready')
        threads=[r for _,r in requests if r.get('id')==2]
        self.assertEqual([r['method'] for r in threads],['thread/start','thread/resume'])
        self.assertEqual(threads[1]['params']['threadId'],result['thread_id'])
        prompt=[r for i,r in requests if i==1 and r.get('method')=='turn/start'][0]['params']['input'][0]['text']
        self.assertIn('复用',prompt);self.assertIn('不得',prompt)
        self.assertFalse(any(p['status']=='error' for p in published))
        self.assertEqual(result['diagnostics']['timeout_retries'],1)
        self.assertEqual(result['diagnostics']['attempts'][0]['error_code'],'timeout')
        self.assertEqual(result['diagnostics']['attempts'][0]['tools'],['proposal_read_project'])

    def test_second_timeout_stops_and_keeps_original_thread(self):
        result,requests,published=self.scenario(second='timeout')
        self.assertEqual(result['status'],'error');self.assertEqual(result['error_code'],'timeout')
        self.assertEqual(len([r for _,r in requests if r.get('id')==2]),2)
        self.assertEqual(sum(p['status']=='error' for p in published),1)

    def test_recovery_scope_and_switch(self):
        for kwargs in [dict(stage=4),dict(existing=True),dict(retries=0),dict(role='teacher')]:
            with self.subTest(**kwargs):
                result,requests,_=self.scenario(**kwargs)
                self.assertEqual(result['status'],'error')
                self.assertEqual(len([r for _,r in requests if r.get('id')==2]),1)

if __name__=='__main__':unittest.main()

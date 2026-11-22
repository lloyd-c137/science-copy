"""Regression checks for account-bound launch state and repeated clicks."""
import tomllib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from queue import Queue
from proposal_app.coach_launcher import CoachLauncher
from proposal_app import coach_mcp


class LauncherState(unittest.TestCase):
    def test_legacy_full_context_thread_is_retained_but_not_resumed(self):
        from proposal_app.project_archive import ProjectArchive
        with tempfile.TemporaryDirectory() as directory:
            launcher = CoachLauncher(directory, open_desktop=False)
            card = {'id':'P1', 'student_name':'合成学生', 'student_id':'U3', '_launch_context': {'id':'P1'}}
            folder = launcher.stage_workspace('U3', card); folder.mkdir(parents=True)
            tid = '11111111-1111-4111-8111-111111111111'
            launcher.save(folder, dict(status='ready', integration=3, thread_id=tid, step=1))
            with patch('proposal_app.coach_launcher.codex_binary', return_value='codex.exe'), patch('proposal_app.coach_launcher.Thread') as worker:
                launcher.start({'id':'U3'}, card, 'http://127.0.0.1:8765', 'token', background=True)
                launched = worker.call_args.kwargs['args'][-1]
                self.assertNotIn('_resume_thread', launched)
                self.assertTrue(launched['_context_migration'])
            history = json.loads((folder/'conversation-history.json').read_text('utf8'))
            self.assertEqual(history[0]['thread_id'], tid)
            archive = ProjectArchive(directory)
            self.assertIn(tid, [r['thread_id'] for r in archive.registered(folder.parent.parent)])

    def test_interruption_recovery_uses_current_saved_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher=CoachLauncher(directory,open_desktop=False)
            card={'id':'P','current_step':5,'steps':[{} for _ in range(6)],'research':{'review_readiness':{'prepared':True,'items':[{'label':'答辩记录','status':'confirm'}]}}}
            folder=launcher.stage_workspace('U',card);folder.mkdir(parents=True)
            launcher.save(folder,{'status':'error','error':'回复超时','thread_id':'original'})
            result=launcher.read('U','P',card)
            self.assertEqual(result['status'],'error')
            self.assertEqual(result['recovery']['action'],'review')
            self.assertIn('答辩记录',result['recovery']['message'])
            card['research']['review_readiness']['prepared']=False
            result=launcher.read('U','P',card)
            self.assertEqual(result['recovery']['action'],'resume')
            self.assertIn('不必重复回答',result['recovery']['message'])

    def test_timeout_releases_writer_before_publishing_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);workspaces=MagicMock();workspaces.visible.return_value=root
            (root/'connection.json').write_text(json.dumps({'server':'http://127.0.0.1:8765'}),'utf-8')
            launcher=CoachLauncher(root,open_desktop=False,workspaces=workspaces)
            rpc=MagicMock();rpc.rows=Queue()
            original=launcher.save
            def save(folder,result):
                if result['status']=='error':rpc.close.assert_called_once()
                original(folder,result)
            config={'model':'gpt-6.1-sol','reasoning_effort':'low','prepare_timeout_seconds':.01}
            with patch('proposal_app.coach_launcher.install_skill',return_value=Path(__file__).resolve().parent.parent/'skills/research-proposal-coach'),patch('proposal_app.desktop_workspace.ensure_workspace_project',return_value={'status':'ready','project_id':'native-project','_rpc':rpc}),patch('proposal_app.coach_launcher.load_launch_config',return_value=config),patch.object(launcher,'save',side_effect=save):
                launcher.run(('U1','P1'),root,root,'codex',{'id':'P1','student_name':'测试学生','version':7})
            result=json.loads((root/'conversation.json').read_text('utf-8'))
            self.assertEqual(result['status'],'error')
            self.assertIn('超时',result['error'])
            self.assertEqual(result['context_version'],7)
            self.assertNotIn('网络',result['error'])

    def run_completion_sequence(self, turns):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);workspaces=MagicMock();workspaces.visible.return_value=root
            (root/'connection.json').write_text(json.dumps({'server':'http://127.0.0.1:8765'}),'utf-8')
            launcher=CoachLauncher(root,open_desktop=False,workspaces=workspaces)
            rpc=MagicMock();rpc.rows=Queue();requests=[]
            tid='11111111-1111-4111-8111-111111111111'
            def receive(raw):
                req=json.loads(raw)
                if req.get('id')==2:rpc.rows.put({'id':2,'result':{'thread':{'id':tid,'projectId':'native-project'}}})
                elif req.get('method')=='turn/start':
                    requests.append(req)
                    status,answer=turns[len(requests)-1]
                    rpc.rows.put({'id':3,'result':{}})
                    items=[{'type':'agentMessage','text':answer}] if answer else []
                    rpc.rows.put({'method':'turn/completed','params':{'turn':{'id':str(len(requests)),'status':status,'items':items}}})
            rpc.process.stdin.write.side_effect=receive
            with patch('proposal_app.coach_launcher.install_skill',return_value=Path(__file__).resolve().parent.parent/'skills/research-proposal-coach'),patch('proposal_app.desktop_workspace.ensure_workspace_project',return_value={'status':'ready','project_id':'native-project','_rpc':rpc}):
                launcher.run(('U','P'),root,root,'codex',{'id':'P','student_name':'测试学生'})
            return json.loads((root/'conversation.json').read_text('utf-8')),requests

    def test_empty_completed_turn_recovers_once_in_same_thread(self):
        result,requests=self.run_completion_sequence([('completed',''),('completed','已读取保存记录，请核对')])
        self.assertEqual(result['status'],'ready')
        self.assertEqual(len(requests),2)
        self.assertEqual(requests[0]['params']['threadId'],requests[1]['params']['threadId'])
        self.assertIn('避免重复',requests[1]['params']['input'][0]['text'])
        self.assertEqual(result['diagnostics']['empty_reply_retries'],1)

    def test_empty_recovery_is_bounded_and_failures_are_not_retried(self):
        for turns,code,count in [([('completed',''),('completed','')],'empty_reply',2),([('failed','')],'turn_failed',1),([('interrupted','')],'turn_interrupted',1)]:
            result,requests=self.run_completion_sequence(turns)
            self.assertEqual(result['status'],'error')
            self.assertEqual(result['error_code'],code)
            self.assertEqual(len(requests),count)
            self.assertEqual(len(result['diagnostics']['completed_turns']),count)

    def test_updated_skill_resumes_existing_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher=CoachLauncher(directory,open_desktop=False)
            card={'id':'P1','student_name':'测试学生','teaching_skill_version':'new'}
            folder=launcher.stage_workspace('U3',card)
            folder.mkdir(parents=True)
            tid='11111111-1111-4111-8111-111111111111'
            launcher.save(folder,dict(status='ready',integration=3,thread_id=tid,skill_version='old'))
            with patch('proposal_app.coach_launcher.codex_binary',return_value='codex.exe'),patch('proposal_app.coach_launcher.Thread') as worker,patch.object(launcher,'open') as opened:
                launcher.start({'id':'U3'},card,'http://127.0.0.1:8765','token',background=True)
                resumed=worker.call_args.kwargs['args'][-1]
                self.assertEqual(resumed['_resume_thread'],tid)
                self.assertTrue(resumed['_rules_updated'])
                opened.assert_not_called()

    def test_ready_is_published_only_after_writer_connection_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);workspaces=MagicMock();workspaces.visible.return_value=root
            (root/'connection.json').write_text(json.dumps({'server':'http://127.0.0.1:8765'}),'utf-8')
            launcher=CoachLauncher(root,open_desktop=False,workspaces=workspaces)
            rpc=MagicMock();rpc.rows=Queue()
            tid='11111111-1111-4111-8111-111111111111'
            def receive(raw):
                req=json.loads(raw)
                if req.get('id')==2:
                    rpc.rows.put({'id':2,'result':{'thread':{'id':tid,'projectId':'native-project'}}})
                elif req.get('id')==3:
                    rpc.rows.put({'id':3,'result':{}})
                    rpc.rows.put({'method':'item/completed','params':{'item':{'type':'agentMessage','text':'具体追问'}}})
                    rpc.rows.put({'method':'turn/completed','params':{'turn':{'status':'completed'}}})
            rpc.process.stdin.write.side_effect=receive
            original=launcher.save
            def save(folder,result):
                if result['status']=='ready':rpc.close.assert_called_once()
                self.assertFalse(result.get('can_open',False))
                original(folder,result)
            with patch('proposal_app.coach_launcher.install_skill',return_value=Path(__file__).resolve().parent.parent/'skills/research-proposal-coach'),patch('proposal_app.desktop_workspace.ensure_workspace_project',return_value={'status':'ready','project_id':'native-project','_rpc':rpc}),patch.object(launcher,'save',side_effect=save):
                launcher.run(('U1','P1'),root,root,'codex',{'id':'P1','student_name':'测试学生'})
            self.assertEqual(json.loads((root/'conversation.json').read_text('utf-8'))['status'],'ready')

    def test_streaming_conversation_cannot_open_while_writer_is_active(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher=CoachLauncher(directory,open_desktop=False)
            card={'id':'P1','student_name':'测试学生'}
            with patch('proposal_app.coach_launcher.codex_binary',return_value='codex.exe'),patch('proposal_app.coach_launcher.Thread.start'):
                launcher.start({'id':'U3'},card,'http://127.0.0.1:8765','token',background=True)
            folder=launcher.stage_workspace('U3',card)
            streaming={'status':'starting','phase':'streaming','can_open':True,'integration':3,
                       'thread_id':'11111111-1111-4111-8111-111111111111'}
            launcher.save(folder,streaming)
            with patch.object(launcher,'open') as opened,patch('proposal_app.coach_launcher.Thread.start') as started:
                self.assertEqual(launcher.start({'id':'U3'},card,'http://127.0.0.1:8765','token'),streaming)
                opened.assert_not_called();started.assert_not_called()
            launcher.running.clear()
            self.assertEqual(launcher.read('U3','P1',card)['status'],'error')

    def test_bound_project_rejects_other_project_before_loading_credentials(self):
        with patch.dict("os.environ", {"PROPOSAL_PROJECT_ID": "P1"}), patch.object(coach_mcp.Client, "load") as load:
            with self.assertRaisesRegex(coach_mcp.ToolError, "当前学生项目"):
                coach_mcp.run_tool("proposal_read_project", {"project_id": "P2"})
            load.assert_not_called()

    def test_project_isolation_reuse_and_interrupted_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = CoachLauncher(directory, open_desktop=False)
            user = {"id":"U3"}
            card = {"id":"P1","student_name":"测试学生"}
            with patch("proposal_app.coach_launcher.codex_binary",return_value="codex.exe"), patch("proposal_app.coach_launcher.Thread.start") as start:
                self.assertEqual(launcher.start(user,card,"http://127.0.0.1:8765","private-test-token")["status"],"starting")
                launcher.start(user,card,"http://127.0.0.1:8765","refreshed-token")
                self.assertEqual(start.call_count,1)
            folder = launcher.stage_workspace("U3",card)
            config = tomllib.loads((folder / ".codex" / "config.toml").read_text("utf-8"))
            mcp = config["mcp_servers"]["proposal_coach"]
            self.assertEqual(mcp["env"]["PROPOSAL_PROJECT_ID"], "P1")
            self.assertEqual(mcp["tools"]["proposal_submit"]["approval_mode"], "approve")
            self.assertEqual(mcp["default_tools_approval_mode"], "prompt")
            self.assertNotIn("proposal_upload", mcp["tools"])
            self.assertNotIn("refreshed-token", str(config))
            self.assertEqual(launcher.read("U2","P1"),{"status":"idle"})
            restarted = CoachLauncher(directory, open_desktop=False)
            self.assertEqual(restarted.read("U3","P1")["status"],"error")
            ready = {"status":"ready","thread_id":"11111111-1111-4111-8111-111111111111","message":"第一问","integration":3}
            launcher.save(folder,ready)
            with patch.object(launcher,"open") as opened:
                self.assertEqual(launcher.start(user,card,"http://127.0.0.1:8765","background-token",background=True),ready)
                opened.assert_not_called()
                self.assertEqual(launcher.start(user,card,"http://127.0.0.1:8765","new-token"),ready)
                opened.assert_called_once_with(ready["thread_id"],None)
            binding=json.loads((folder / "binding" / "connection.json").read_text("utf-8"))
            self.assertEqual(binding["account"],"U3")
            self.assertEqual(binding["token"],"new-token")
            with patch.object(launcher,"open",side_effect=OSError("无法打开")):
                with self.assertRaisesRegex(OSError,"无法打开"):
                    launcher.start(user,card,"http://127.0.0.1:8765","new-token")
            self.assertEqual(launcher.read("U3","P1",card),ready)
            with patch('proposal_app.desktop_workspace.desktop_is_active',return_value=False),patch.object(launcher,'open') as opened:
                result=launcher.start(user,card,'http://127.0.0.1:8765','token',only_if_active=True)
                self.assertFalse(result['opened']);opened.assert_not_called()
            with patch('proposal_app.desktop_workspace.desktop_is_active',return_value=True),patch.object(launcher,'open') as opened:
                result=launcher.start(user,card,'http://127.0.0.1:8765','token',only_if_active=True)
                self.assertTrue(result['opened']);opened.assert_called_once()
            launcher.running.clear()
            launcher.save(folder,dict(ready,status='error',error='连接中断'))
            with patch('proposal_app.coach_launcher.codex_binary',return_value='codex.exe'),patch('proposal_app.coach_launcher.Thread') as worker:
                launcher.start(user,card,'http://127.0.0.1:8765','retry-token')
                resumed_card=worker.call_args.kwargs['args'][-1]
            self.assertEqual(resumed_card['_resume_thread'],ready['thread_id'])
            self.assertIn('不要重复固定首问',launcher.discussion_prompt(resumed_card,'开始讨论'))

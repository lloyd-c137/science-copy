import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from proposal_app.workspace_store import WorkspaceStore
from proposal_app import server, coach_mcp
from proposal_app.coach_launcher import CoachLauncher


class Workspaces(unittest.TestCase):
    def test_registry_failure_can_retry_without_overwriting_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);store=WorkspaceStore(root/'registry.json')
            card=server.make_card('P123456','A1','U1','模拟学生')
            from proposal_app import workspace_store
            original=workspace_store.atomic_json
            def fail_registry(path,value):
                if Path(path)==store.registry: raise OSError('simulated write failure')
                original(path,value)
            with patch.object(workspace_store,'atomic_json',side_effect=fail_registry):
                with self.assertRaises(OSError): store.select(card,str(root/'projects'))
            target=root/'projects'/store.describe(card)['folder_name']
            (target/'我的笔记'/'观察.txt').write_text('保留我的观察','utf-8')
            store.select(card,str(root/'projects'))
            self.assertEqual((target/'我的笔记'/'观察.txt').read_text('utf-8'),'保留我的观察')

    def test_selection_restart_isolation_and_no_adoption(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); registry=root/'registry.json'
            store=WorkspaceStore(registry)
            card=server.make_card('P123456','A1','U1','同学甲')
            self.assertFalse(store.describe(card)['configured'])
            with self.assertRaises(ValueError): store.select(card,'relative-folder')
            with self.assertRaises(ValueError): store.select(card,'\\\\host\\share')
            chosen=store.select(card,str(root/'课程 资料'))
            project=Path(chosen['path'])
            self.assertEqual(project.name,'同学甲-开题项目')
            self.assertEqual(project.parent,root/'课程 资料')
            self.assertEqual(store.internal('U1',card['id']),project/'.coach')
            (project/'我的笔记'/'观察.txt').write_text('我的观察','utf-8')
            self.assertEqual(WorkspaceStore(registry).select(card,str(project.parent)),chosen)
            self.assertIsNone(store.visible('U2',card['id']))
            with self.assertRaises(ValueError): store.select(card,str(root/'另一个位置'))
            other=server.make_card('P654321','A1','U2','同学甲')
            conflict=project.parent/(store.describe(other)['folder_name']+'-2');conflict.mkdir()
            (conflict/'我的文件').write_text('保留')
            second=store.select(other,str(project.parent))
            self.assertEqual(Path(second['path']).name,'同学甲-开题项目-3')
            self.assertEqual(WorkspaceStore(registry).select(other,str(project.parent)),second)
            self.assertEqual((conflict/'我的文件').read_text(),'保留')

    def test_shared_root_and_distinct_stage_tokens_reject_old_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);store=WorkspaceStore(root/'registry.json')
            card=server.make_card('P123456','A1','U1','模拟学生')
            card['activity']={'version':1}
            store.select(card,str(root/'projects'))
            launcher=CoachLauncher(root/'private',open_desktop=False,workspaces=store)
            with patch('proposal_app.coach_launcher.codex_binary',return_value='codex'),patch('proposal_app.coach_launcher.Thread.start'):
                launcher.start({'id':'U1'},card,'http://127.0.0.1:8765','test-token',background=True)
                first=json.loads((launcher.stage_workspace('U1',card)/'session.json').read_text())
                launcher.running.clear()
                card['current_step']=2
                launcher.start({'id':'U1'},card,'http://127.0.0.1:8765','test-token',background=True)
                second=json.loads((launcher.stage_workspace('U1',card)/'session.json').read_text())
            self.assertNotEqual(first['token'],second['token'])
            config=(store.visible('U1',card['id'])/'.codex/config.toml').read_text('utf-8')
            self.assertNotIn('PROPOSAL_STAGE =',config)
            args={'project_id':card['id'],'workflow_version':card['workflow_version'],'step':2,'data':{},'complete':True,'confirmed':True,'version':1,'requirement_version':1,'request_id':'one','stage_session':first['token']}
            env={'PROPOSAL_PROJECT_ID':card['id'],'PROPOSAL_STAGE_SESSIONS':str(store.internal('U1',card['id'])/'sessions')}
            with patch.dict('os.environ',env),patch.object(coach_mcp.Client,'load') as load:
                load.return_value.request.return_value=card
                load.return_value.origin='http://127.0.0.1:8765'
                with self.assertRaisesRegex(coach_mcp.ToolError,'阶段已经结束|导师只能保存草稿'):
                    coach_mcp.run_tool('proposal_submit',args)
                load.return_value.write.assert_not_called()
                with self.assertRaisesRegex(coach_mcp.ToolError,'stage_session'):
                    coach_mcp.run_tool('proposal_read_project',{'project_id':card['id']})


if __name__=='__main__':unittest.main()

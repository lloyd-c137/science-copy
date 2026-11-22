"""Configuration errors, reloads and actual launch RPC parameter routing."""
import json
from pathlib import Path
from queue import Queue
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from proposal_app.runtime_config import load_launch_config
from proposal_app.coach_launcher import CoachLauncher
from proposal_app.review_launcher import ReviewLauncher


class RuntimeConfigTests(unittest.TestCase):
    def test_E_initial_draft_retry_switch_is_bounded_and_student_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'runtime-config.json'
            for value in (0,1):
                data=self.config();data['student']['e_draft_timeout_retries']=value
                path.write_text(json.dumps(data),'utf-8')
                self.assertEqual(load_launch_config('student',path)['e_draft_timeout_retries'],value)
            for role,value in [('student',True),('student',2),('student',-1),('teacher',1)]:
                data=self.config();data[role]['e_draft_timeout_retries']=value
                path.write_text(json.dumps(data),'utf-8')
                with self.assertRaises(RuntimeError):load_launch_config('student',path)

    def config(self):
        return {
            'student': dict(model='student-model', reasoning_effort='medium', prepare_timeout_seconds=240),
            'teacher': dict(model='teacher-model', reasoning_effort='high', prepare_timeout_seconds=480),
        }

    def test_reload_and_invalid_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'runtime-config.json'
            data = self.config()
            path.write_text(json.dumps(data), 'utf-8-sig')
            self.assertEqual(load_launch_config('student', path)['model'], 'student-model')
            data['student']['model'] = 'changed-model'
            path.write_text(json.dumps(data), 'utf-8')
            self.assertEqual(load_launch_config('student', path)['model'], 'changed-model')
            for field, value in [('model', ''), ('reasoning_effort', 'typo'), ('prepare_timeout_seconds', True), ('prepare_timeout_seconds', 0), ('unknown', 123)]:
                invalid = self.config()
                invalid['teacher'][field] = value
                path.write_text(json.dumps(invalid), 'utf-8')
                with self.assertRaisesRegex(RuntimeError, '启动配置错误'):
                    load_launch_config('student', path)
            path.write_text('{', 'utf-8')
            with self.assertRaisesRegex(RuntimeError, '启动配置错误'):
                load_launch_config('student', path)
            path.unlink()
            with self.assertRaisesRegex(RuntimeError, '启动配置错误'):
                load_launch_config('student', path)

    def test_role_settings_reach_new_opening_and_resumed_turns(self):
        for launcher_type in (CoachLauncher, ReviewLauncher):
            for mode in ('new', 'opening', 'resume'):
                with self.subTest(role=launcher_type.config_role, mode=mode), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    (root/'connection.json').write_text(json.dumps({'server': 'http://localhost:8767'}), 'utf-8')
                    launcher = launcher_type(root, open_desktop=False)
                    launcher.workspaces = MagicMock()
                    launcher.workspaces.visible.return_value = root
                    rpc = MagicMock()
                    rpc.rows = Queue()
                    requests = []
                    tid = '11111111-1111-4111-8111-111111111111'
                    def receive(raw):
                        req = json.loads(raw)
                        requests.append(req)
                        if req.get('id') == 2:
                            rpc.rows.put({'id': 2, 'result': {'thread': {'id': tid, 'projectId': 'native-project'}}})
                        elif req.get('id') == 11:
                            rpc.rows.put({'id': 11, 'result': {}})
                        elif req.get('id') == 3:
                            rpc.rows.put({'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'text': '准备完成'}}})
                            rpc.rows.put({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})
                    rpc.process.stdin.write.side_effect = receive
                    card = {'id': 'P1', 'student_name': '测试学生'}
                    if mode == 'opening': card['_opening_answer'] = '我的观察'
                    if mode == 'resume': card['_resume_thread'] = tid
                    settings = self.config()[launcher.config_role]
                    with patch('proposal_app.coach_launcher.load_launch_config', return_value=settings) as load, \
                         patch('proposal_app.coach_launcher.install_skill', return_value=Path(__file__).resolve().parent.parent/'skills/research-proposal-coach'), \
                         patch('proposal_app.desktop_workspace.ensure_workspace_project', return_value={'status': 'ready', 'project_id': 'native-project', '_rpc': rpc}), \
                         patch.object(launcher, 'discussion_instructions', side_effect=lambda card, text: text), \
                         patch.object(launcher, 'discussion_prompt', side_effect=lambda card, text: text), \
                         patch.object(launcher, 'verify_completion'):
                        launcher.run(('U1', 'P1'), root, root, 'codex', card)
                    load.assert_called_once_with(launcher.config_role)
                    self.assertEqual(json.loads((root/'conversation.json').read_text('utf-8'))['status'], 'ready')
                    thread = next(r for r in requests if r.get('id') == 2)
                    self.assertEqual(thread['method'], 'thread/resume' if mode == 'resume' else 'thread/start')
                    self.assertEqual(thread['params']['model'], settings['model'])
                    turn = next(r for r in requests if r.get('id') == 3)
                    self.assertEqual(turn['params']['model'], settings['model'])
                    self.assertEqual(turn['params']['effort'], settings['reasoning_effort'])

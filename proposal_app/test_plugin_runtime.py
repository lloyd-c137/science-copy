"""Runtime contracts: autonomous discovery, durable retry and protected exports."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import multiprocessing
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from proposal_app import pilot_client as client


def claim_in_process(root, owner, project, queue):
    try:
        client.claim_workspace(Path(root), owner, project)
        queue.put('claimed')
    except client.mcp.ToolError:
        queue.put('rejected')


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.log = self.root / 'registered.jsonl'
        self.stage, self.thread = 'a' * 32, str(uuid4())
        self.rows = [{'type': 'session_meta', 'payload': {'id': self.thread, 'cwd': str(self.root)}}]
        self.journal = client.Journal(self.root / 'state' / 'archives.sqlite3')
        self.journal.remember('owner', self.stage, self.log, self.root, self.thread, 'project')

    def event(self, turn, kind, **fields):
        self.rows.append({'type': 'event_msg', 'timestamp': '2026-11-20T01:02:03Z',
                          'payload': {'type': kind, 'turn_id': turn, 'thread_id': self.thread, **fields}})

    def item(self, turn, kind, text, phase=None):
        ident = str(uuid4())
        self.event(turn, 'item_completed', item={'id': ident, 'type': kind, 'phase': phase,
                   'content': [{'type': 'text', 'text': text}]})
        return ident

    def turn(self, text='普通解释，没有新成果。', complete=True, aborted=False):
        turn = str(uuid4())
        self.event(turn, 'task_started')
        if len(self.rows) == 2:
            text += '\n开题手记会话：' + self.stage
        self.item(turn, 'UserMessage', text)
        if complete:
            self.item(turn, 'AgentMessage', '完整答复。\n\n末段逐字保留。', 'final_answer')
            self.event(turn, 'task_complete')
        if aborted:
            self.event(turn, 'turn_aborted')
        self.flush()
        return turn

    def flush(self):
        self.log.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in self.rows) + '\n', 'utf-8')

    def test_restart_discovers_unscheduled_tail_and_retries_without_cross_project_logs(self):
        first = self.turn()
        unrelated = self.root / 'unregistered.jsonl'
        unrelated.write_text(self.log.read_text('utf-8'), 'utf-8')
        client.discover(self.journal, 'owner')
        self.assertEqual([job.turn for job, _ in self.journal.jobs('owner')], [first])
        def offline(body):
            raise client.mcp.Offline('offline')
        client.process_jobs(self.journal, 'owner', offline)
        last = self.turn('关闭进程之前尚未入队的末轮。')
        restarted = client.Journal(self.journal.path)
        client.discover(restarted, 'owner')
        self.assertEqual([job.turn for job, _ in restarted.jobs('owner')], [first, last])
        received = []
        def publish(body):
            received.append(body)
            return {'saved': True}
        client.process_jobs(restarted, 'owner', publish)
        client.discover(restarted, 'owner')
        client.process_jobs(restarted, 'owner', publish)
        self.assertEqual(len(received), 2)
        self.assertTrue(all(body['complete'] for body in received))
        self.assertEqual(received[-1]['messages'][-1]['text'], '完整答复。\n\n末段逐字保留。')
        self.assertEqual(restarted.jobs('owner'), [])
        self.assertEqual(restarted.jobs('other-account'), [])

    def test_aborted_keeps_user_words_and_next_turn_finishes(self):
        aborted = self.turn('停止前我的观察。', complete=False, aborted=True)
        final = self.turn('补充追问。')
        client.discover(self.journal, 'owner')
        received = []
        client.process_jobs(self.journal, 'owner', lambda body: received.append(body) or {'saved': True})
        self.assertEqual([body['turn'] for body in received], [aborted, aborted, final])
        self.assertEqual(received[0]['messages'][0]['role'], 'user')
        self.assertIn('停止前我的观察。', received[0]['messages'][0]['text'])
        self.assertTrue(received[1]['abandoned'])
        self.assertTrue(received[2]['complete'])

    def test_same_process_loop_waits_for_final_without_schedule_tool(self):
        turn = self.turn(complete=False)
        bridge = client.Bridge('http://127.0.0.1:8767', self.root / 'state')
        complete = threading.Event()
        received = []
        process_threads = []
        class Device:
            owner = 'owner'
            def request(self, path, body):
                process_threads.append(threading.get_ident())
                if path.endswith('/export'):
                    return {'unchanged': True}
                received.append(body)
                if body['complete']:
                    complete.set()
                return {'saved': True}
        with patch.object(client, 'load_device', return_value=Device()):
            bridge.start()
            try:
                deadline = time.monotonic() + 3
                while not received and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertFalse(complete.is_set())
                self.item(turn, 'AgentMessage', '这还不是最终回复。', 'commentary')
                self.flush()
                bridge.wake.set()
                self.assertFalse(complete.wait(.15))
                self.item(turn, 'AgentMessage', '最终答案。\n保留最后一行。', 'final_answer')
                self.event(turn, 'task_complete')
                self.flush()
                bridge.wake.set()
                self.assertTrue(complete.wait(3))
                self.assertTrue(all(ident == bridge.worker.ident for ident in process_threads))
                self.assertEqual(received[-1]['messages'][-1]['text'], '最终答案。\n保留最后一行。')
            finally:
                bridge.close()

    def test_export_preserves_personal_notes_and_edited_generated_file(self):
        card = {'id': 'project', 'title': '旧标题', 'version': 1, 'steps': [], 'current_step': 1}
        result = {'project': card, 'archive': {'conversations': []}}
        client.protected_export(self.root, result)
        notes = self.root / '我的笔记' / '观察.md'
        notes.write_text('个人材料。', 'utf-8')
        generated = self.root / '项目说明.md'
        generated.write_text('学生自行修改的版本。', 'utf-8')
        result['project'] = dict(card, title='网站新标题', version=2)
        client.protected_export(self.root, result)
        self.assertEqual(notes.read_text('utf-8'), '个人材料。')
        self.assertEqual(generated.read_text('utf-8'), '学生自行修改的版本。')
        self.assertIn('网站新标题', (self.root / '项目说明-自动导出1.md').read_text('utf-8'))

    def test_windows_workspace_hash_is_case_and_separator_independent(self):
        self.assertEqual(client.workspace_hash('D:/课题/资料/../项目'), client.workspace_hash('d:\\课题\\项目'))

    def test_different_accounts_cannot_claim_same_workspace_across_processes(self):
        context = multiprocessing.get_context('spawn')
        queue = context.Queue()
        processes = [context.Process(target=claim_in_process, args=(str(self.root), owner, 'project', queue))
                     for owner in ('account-a', 'account-b')]
        try:
            for process in processes:
                process.start()
            results = [queue.get(timeout=10) for _ in processes]
            for process in processes:
                process.join(10)
                self.assertEqual(process.exitcode, 0)
            self.assertCountEqual(results, ['claimed', 'rejected'])
            saved = json.loads((self.root / '.coach/plugin-owner.json').read_text('utf-8'))
            with self.assertRaises(client.mcp.ToolError):
                client.claim_workspace(self.root, saved['owner'], 'different-project')
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join()
            queue.close()

    def test_out_of_order_receipts_cannot_move_confirmed_cutoff_backwards(self):
        first, last = self.turn(), self.turn()
        client.discover(self.journal, 'owner')
        jobs = {job.turn: job for job, _ in self.journal.jobs('owner')}
        self.journal.update(jobs[last], done=True, completed=True)
        self.journal.update(jobs[first], done=True, completed=True)
        self.assertEqual(self.journal.bindings('owner')[0]['last_turn'], last)

    def test_missing_final_or_changed_history_keeps_job_pending_and_reports_error(self):
        turn = self.turn(complete=False)
        self.event(turn, 'task_complete')
        self.flush()
        client.discover(self.journal, 'owner')
        client.process_jobs(self.journal, 'owner', lambda body: {'saved': True})
        self.assertEqual(len(self.journal.jobs('owner')), 1)
        self.assertIn('最终回复', self.journal.bindings('owner')[0]['error'])
        with self.log.open('a', encoding='utf-8') as stream:
            stream.write('[]\n')
        client.process_jobs(self.journal, 'owner', lambda body: self.fail('Unsupported history must not upload'))
        self.assertEqual(len(self.journal.jobs('owner')), 1)
        self.assertIn('格式', self.journal.bindings('owner')[0]['error'])

    def test_older_recovery_cannot_overwrite_newer_export(self):
        current = {'project': {'id': 'project', 'title': '新版本', 'version': 4, 'steps': []}, 'archive': {}}
        client.protected_export(self.root, current, owner='account')
        older = {'project': dict(current['project'], title='旧版本', version=3), 'archive': {}}
        client.protected_export(self.root, older, owner='account')
        self.assertIn('新版本', (self.root / '项目说明.md').read_text('utf-8'))

    def test_recovery_reads_before_replacement_and_teacher_uses_review_tool(self):
        turn = self.turn(complete=False)
        _, turns, _ = client.pilot_history.transcript(self.log)
        card = {'id': 'project', 'title': '恢复成果', 'version': 3, 'current_step': 1, 'steps': []}
        calls = []
        class Device:
            owner, origin, token = 'owner', 'http://127.0.0.1:8767', 'device-token'
            role = 'student'
            def request(self, path, body):
                calls.append((path, body))
                if path.endswith('recovery-context'):
                    return {'recovery': self.role == 'student', 'restore_token': 'proof',
                            'project_id': 'project', 'project': card, 'archive': {'conversations': []}}
                if path.endswith('/export'):
                    return {'unchanged': True}
                return {'project': 'project', 'account': 'account', 'token': 'lease', 'role': self.role, 'reusable': True}
        device = Device()
        args = {'stage_session': self.stage, 'workspace': str(self.root)}
        with patch.object(client, 'load_device', return_value=device), patch.object(client.pilot_history, 'find_active',
                return_value=(self.log, self.thread, turns, turn)), patch.object(client.mcp, 'run_tool', return_value={'version': 3}):
            bridge = client.Bridge(device.origin, self.root / 'new-state', self.root / '.codex/sessions')
            result = bridge('proposal_read_project', args)
            self.assertEqual([path for path, _ in calls[:2]], ['/api/plugin/recovery-context', '/api/plugin/session'])
            self.assertEqual(calls[1][1]['restore_token'], 'proof')
            self.assertEqual(calls[1][1]['workspace_hash'], client.workspace_hash(self.root))
            self.assertIn('recovery_context', result)
            self.assertTrue((self.root / '项目说明.md').is_file())
            bridge('proposal_read_project', args)
            self.assertEqual(sum(path.endswith('/session') for path, _ in calls), 1)
            device.role = 'teacher'
            teacher = client.Bridge(device.origin, self.root / 'teacher-state', self.root / '.codex/sessions')
            with patch.object(client.review_mcp, 'run_tool', return_value={'fixed': True}) as review:
                self.assertEqual(teacher('review_read_project', args), {'fixed': True})
                self.assertEqual(review.call_args.args, ('review_read_project', {}))
                self.assertEqual(review.call_args.kwargs['project'], 'project')
                self.assertEqual(teacher.journal.bindings('owner')[0]['role'], 'teacher')

    def test_conflicting_workspace_rejects_before_recovery_replaces_server_binding(self):
        turn = self.turn(complete=False)
        _, turns, _ = client.pilot_history.transcript(self.log)
        client.claim_workspace(self.root, 'other-account', 'other-project')
        calls = []
        class Device:
            owner, origin, token = 'owner', 'http://127.0.0.1:8767', 'device-token'
            def request(self, path, body):
                calls.append(path)
                if path.endswith('recovery-context'):
                    return {'recovery': True, 'restore_token': 'proof'}
                raise AssertionError('Conflicting directory must not replace the server binding')
        device = Device()
        bridge = client.Bridge(device.origin, self.root / 'recovery-state', self.root / '.codex/sessions')
        with patch.object(client, 'load_device', return_value=device), patch.object(client.pilot_history, 'find_active',
                return_value=(self.log, self.thread, turns, turn)):
            with self.assertRaises(client.mcp.ToolError):
                bridge('proposal_read_project', {'stage_session': self.stage, 'project_id': 'project', 'workspace': str(self.root)})
        self.assertEqual(calls, ['/api/plugin/recovery-context'])


if __name__ == '__main__':
    unittest.main()

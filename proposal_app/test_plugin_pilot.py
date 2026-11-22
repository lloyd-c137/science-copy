import base64
import hashlib
import json
from contextlib import ExitStack, closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
import sqlite3
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from unittest.mock import patch

from proposal_app import server


class PluginPilotTest(unittest.TestCase):
    def test_plugin_search_accepts_empty_query_for_a_directory_listing(self):
        from proposal_app import coach_mcp, pilot_client

        schema=pilot_client.SCHEMAS['proposal_search_project_files']
        coach_mcp.validate(schema, {'stage_session':'a'*32,'query':''})
        coach_mcp.validate(schema, {'stage_session':'a'*32})

    def test_plugin_large_file_reads_keep_the_page_limit(self):
        from proposal_app import coach_mcp, pilot_client

        with TemporaryDirectory() as temp:
            bridge = pilot_client.Bridge('https://research.example', Path(temp))
            args = dict(stage_session='a'*32, path='我的笔记/记录.md', limit=30000)
            with patch.object(coach_mcp, 'validate', wraps=coach_mcp.validate) as validate, \
                 patch.object(pilot_client, 'load_device', side_effect=RuntimeError('no device in test')):
                with self.assertRaisesRegex(RuntimeError, 'no device in test'):
                    bridge('proposal_read_project_file', args)
            self.assertEqual(validate.call_args.args[1]['limit'], 24000)
            self.assertEqual(args['limit'], 30000)

    def test_review_first_draft_accepts_only_explicit_empty_revision(self):
        from proposal_app import coach_mcp, pilot_client

        args = dict(stage_session='a'*32, project_version=1, requirement_version=1, draft_revision='', draft={})
        coach_mcp.validate(pilot_client.SCHEMAS['review_save_draft'], args)
        with self.assertRaises(coach_mcp.ToolError):
            coach_mcp.validate(pilot_client.SCHEMAS['review_save_draft'], dict(args, draft_revision=' '))
        with self.assertRaises(coach_mcp.ToolError):
            coach_mcp.validate(pilot_client.SCHEMAS['review_save_draft'], dict(args, stage_session=''))

    def test_verified_folder_reuse_creates_the_current_stage_entry(self):
        from proposal_app import plugin_site

        with closing(sqlite3.connect(':memory:')) as db:
            db.row_factory = sqlite3.Row
            plugin_site.init_schema(db)
            user = {'id': 'U1', 'role': 'student'}
            handler = SimpleNamespace(headers={})
            card = dict(id='P1', status='active', current_step=1, steps=[{}, {}], version=2)
            path_hash = 'a' * 64
            with patch.object(plugin_site, 'browser_device', return_value='my-device'):
                a = plugin_site.entry(handler, db, card, user, {'workspace_hash': path_hash})
                with self.assertRaises(plugin_site.PilotError) as rejected:
                    plugin_site.entry(handler, db, card, user, {'workspace_hash': path_hash, 'reuse': True})
                self.assertEqual(rejected.exception.code, 'workspace_reselection_required')
                db.execute('INSERT INTO plugin_workspace_claims VALUES (?,?,?)', ('my-device', path_hash, 'P1'))
                card['current_step'] = 2
                b = plugin_site.entry(handler, db, card, user, {'workspace_hash': path_hash, 'reuse': True})
                self.assertEqual(b['step'], 2)
                self.assertNotEqual(a['stage_session'], b['stage_session'])
                self.assertIsNone(b['thread_id'])
            with patch.object(plugin_site, 'browser_device', return_value='other-device'):
                with self.assertRaises(plugin_site.PilotError):
                    plugin_site.entry(handler, db, card, user, {'workspace_hash': path_hash, 'reuse': True})

    def test_local_queue_waits_for_real_final_and_retries(self):
        from proposal_app import pilot_client

        with TemporaryDirectory() as temp:
            folder = Path(temp).resolve()
            log = folder / 'rollout.jsonl'
            thread, turn = str(uuid4()), str(uuid4())
            stage = 'a' * 32
            first = f'网页给的讨论信息\n开题手记会话：{stage}'
            def event(kind, **fields):
                return {'type': 'event_msg', 'timestamp': '2026-11-20T09:00:00Z',
                        'payload': {'type': kind, 'turn_id': turn, 'thread_id': thread, **fields}}
            def item(kind, text, phase=None):
                return event('item_completed', item={'type': kind, 'id': str(uuid4()), 'phase': phase,
                                                       'content': [{'type': 'text', 'text': text}]})
            rows = [{'type': 'session_meta', 'payload': {'id': thread, 'cwd': str(folder)}},
                    event('task_started'), item('UserMessage', first), item('AgentMessage', 'thinking', 'commentary')]
            def write():
                log.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows), 'utf-8')
            write()
            journal = pilot_client.Journal(folder / 'queue.sqlite')
            job = pilot_client.Job('account', stage, thread, turn, str(log), str(folder))
            journal.enqueue(job)
            received = []
            def publish(payload):
                received.append(payload)
                if payload['complete'] and len(received) == 2:
                    raise pilot_client.mcp.Offline('offline')
                return {'saved': True, 'complete': payload['complete']}
            pilot_client.process_jobs(journal, 'account', publish)
            self.assertEqual(received[0]['messages'], [])
            final = '开头。\n\n完整结尾。'
            rows.extend([item('AgentMessage', final, 'final_answer'), event('task_complete')])
            write()
            pilot_client.process_jobs(journal, 'account', publish)
            self.assertEqual(len(journal.jobs('account')), 1)
            pilot_client.process_jobs(journal, 'account', publish)
            self.assertEqual([m['text'] for m in received[-1]['messages']], [first, final])
            self.assertEqual(journal.jobs('account'), [])

    def test_account_and_phase_scoped_archive_without_local_site_workers(self):
        with TemporaryDirectory() as temp, ExitStack() as resources:
            service = resources.enter_context(server.serve(Path(temp) / 'pilot.sqlite3', 0,
                                                            plugin_origin='https://research.example'))
            worker = Thread(target=service.serve_forever, daemon=True)
            worker.start()
            resources.callback(worker.join)
            resources.callback(service.shutdown)
            origin = f'http://127.0.0.1:{service.server_port}'

            def api(path, body=None, auth=None, browser=False, status=200):
                headers = {'Content-Type': 'application/json'}
                if auth:
                    headers['Cookie' if browser else 'Authorization'] = ('coach_session=' if browser else 'Bearer ') + auth
                try:
                    result = urlopen(Request(origin+'/api/'+path, headers=headers,
                                             data=json.dumps(body).encode() if body is not None else None), timeout=5)
                except HTTPError as error:
                    result = error
                with result:
                    payload = json.load(result)
                    self.assertEqual(status, result.status, payload)
                    return payload

            student = api('login', {'username': 'student', 'password': 'yanjiu123'})['token']
            other = api('login', {'username': 'student2', 'password': 'yanjiu123'})['token']
            pid = api('home', auth=student)['projects'][0]['id']
            path = f'projects/{pid}'
            self.assertIsNone(service.coach_launcher)
            self.assertIsNone(service.workspaces)
            api(path+'/workspace', {'parent': 'C:/student'}, student, browser=True, status=409)
            entry = api(path+'/plugin-entry', {'workspace_hash': 'a'*64}, student, browser=True)
            api(path+'/plugin-entry', {}, student, status=403)
            self.assertEqual(entry['prompt'].splitlines(), [
                '$research-coach:research-proposal-coach',
                '开题手记会话：' + entry['stage_session'],
                '请带我开始探索研究问题。',
            ])

            def pair(account):
                verifier = uuid4().hex + uuid4().hex
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                pair_id = api('plugin/device-request', {'challenge': challenge})['device_code']
                api('plugin/authorize', {'device_code': pair_id}, account, browser=True)
                api('plugin/device-token', {'device_code': pair_id, 'verifier': 'wrong'}, status=400)
                return api('plugin/device-token', {'device_code': pair_id, 'verifier': verifier})['token']

            device = pair(student)
            foreign = pair(other)
            binding = {'stage_session': entry['stage_session'], 'thread': str(uuid4()), 'workspace_hash': 'a'*64}
            api('plugin/session', binding, foreign, status=403)
            grant = api('plugin/session', binding, device)
            self.assertTrue(grant['reusable'])
            coach = grant['token']
            original = api(path+'/context', auth=coach)
            same_route = path+'/context?known_hash='+original['context_hash']
            with patch('proposal_app.project_archive.context_archive.export', side_effect=AssertionError('unchanged must skip export')):
                self.assertTrue(api(same_route, auth=coach)['unchanged'])
            self.assertTrue(api('plugin-lease', auth=coach)['active'])
            api('plugin-lease', auth=student, browser=True, status=403)
            api(path+'/progress', {'complete': True}, coach, status=403)
            api('plugin/session', dict(binding, thread=str(uuid4())), device, status=409)
            rows = [{'id': str(uuid4()), 'role': 'user', 'text': '同一个时间出发。', 'time': '2026-11-20T09:00:00Z'},
                    {'id': str(uuid4()), 'role': 'assistant', 'text': '第一段。\n\n最后一段。', 'time': '2026-11-20T09:00:01Z'}]
            publication = {**binding, 'turn': str(uuid4()), 'messages': rows, 'complete': True}
            api('plugin/archive', publication, foreign, status=403)
            api('plugin/archive', publication, device)
            api('plugin/archive', publication, device)
            updated = api(same_route, auth=coach)
            self.assertNotEqual(updated['context_hash'], original['context_hash'])
            self.assertEqual(api(path+'/discussions', auth=student)['conversations'][0]['messages'], rows)
            api('plugin/archive', dict(publication, messages=[dict(rows[0], text='changed'), rows[1]]), device, status=409)
            self.assertEqual(api(path+'/plugin-entry', {'workspace_hash':'a'*64}, student, browser=True)['thread_id'], binding['thread'])
            replacement = api(path+'/plugin-entry', {'workspace_hash':'b'*64,'recovery':True}, student, browser=True)
            retry = api(path+'/plugin-entry', {'workspace_hash':'b'*64,'recovery':True}, student, browser=True)
            self.assertEqual(replacement['stage_session'],retry['stage_session'])
            restore = dict(stage_session=replacement['stage_session'],thread=str(uuid4()),workspace_hash='b'*64)
            api('plugin/session',restore,device,status=409)
            context = api('plugin/recovery-context',restore,device)
            self.assertEqual(context['archive']['conversations'][0]['messages'],rows)
            self.assertIn('notes',context)
            replacement_coach = api('plugin/session',dict(restore,restore_token=context['restore_token']),device)['token']
            api('plugin/session',binding,device,status=409)
            api(path+'/context',auth=coach,status=409)
            api('plugin/archive',publication,device)
            self.assertEqual(api('plugin/export',binding,device),{'inactive':True})
            with closing(server.connect(service.db_path)) as db, db:
                card = json.loads(db.execute('SELECT card FROM projects WHERE id=?', (pid,)).fetchone()[0])
                card['current_step'] = 2
                db.execute('UPDATE projects SET card=? WHERE id=?', (json.dumps(card), pid))
            api('plugin-lease', auth=replacement_coach, status=409)
            api(path+'/context', auth=replacement_coach, status=409)
            api(path+'/progress', {'complete': False}, replacement_coach, status=409)
            with closing(server.connect(service.db_path)) as db, db:
                card['current_step'] = 1
                db.execute('UPDATE projects SET card=? WHERE id=?', (json.dumps(card), pid))
                db.execute('DELETE FROM plugin_devices WHERE token=?', (hashlib.sha256(device.encode()).hexdigest(),))
            api('plugin-lease', auth=replacement_coach, status=401)

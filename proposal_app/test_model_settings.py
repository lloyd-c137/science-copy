"""Model defaults: browser authority, atomic persistence, and native config routing."""
from contextlib import ExitStack
import io
import json
from pathlib import Path
import tempfile
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from proposal_app import server, runtime_config, pilot_defaults


class SettingsTests(unittest.TestCase):
    def test_browser_permissions_persistence_and_conflicts(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            path = root / 'runtime-config.json'
            path.write_bytes(runtime_config.CONFIG_PATH.read_bytes())
            service = stack.enter_context(server.serve(root / 'db.sqlite', 0, plugin_origin='http://127.0.0.1:8767'))
            service.runtime_config_path = path
            worker = Thread(target=service.serve_forever, daemon=True)
            worker.start()
            stack.callback(worker.join)
            stack.callback(service.shutdown)
            def api(route, body=None, token=None, bearer=False, expected=200):
                headers = {'Content-Type': 'application/json'}
                if token:
                    headers['Authorization' if bearer else 'Cookie'] = ('Bearer ' if bearer else 'coach_session=') + token
                req = Request(f'http://127.0.0.1:{service.server_port}/api/{route}',
                              data=json.dumps(body).encode() if body is not None else None, headers=headers)
                try:
                    response = urlopen(req, timeout=5)
                except HTTPError as error:
                    response = error
                with response:
                    result = json.load(response)
                    self.assertEqual(response.status, expected, result)
                    return result
            student = api('login', dict(username='student', password='yanjiu123'))['token']
            teacher = api('login', dict(username='teacher', password='yanjiu123'))['token']
            api('runtime-settings', expected=401)
            current = api('runtime-settings', token=student)
            self.assertFalse(current['editable'])
            body = dict(revision=current['revision'], model='gpt-6.1-sol', reasoning_effort='low')
            api('runtime-settings', body, student, expected=403)
            api('runtime-settings', body, teacher, bearer=True, expected=403)
            api('runtime-settings', dict(body, model='bad model'), teacher, expected=422)
            before = runtime_config.load_launch_config('student', path)
            changed = api('runtime-settings', dict(body, reasoning_effort='medium'), teacher)
            self.assertNotEqual(changed['revision'], current['revision'])
            api('runtime-settings', body, teacher, expected=409)
            for role in ('student', 'teacher'):
                self.assertEqual(runtime_config.load_launch_config(role, path)['reasoning_effort'], 'medium')
            self.assertEqual(runtime_config.load_launch_config('student', path)['prepare_timeout_seconds'], before['prepare_timeout_seconds'])
            api('plugin/runtime-settings', {}, token=teacher, bearer=True, expected=401)

    def test_native_rpc_only_changes_model_defaults(self):
        process = MagicMock()
        output = io.StringIO()
        process.stdin = MagicMock(wraps=output)
        process.stdin.close = MagicMock()
        process.stdout = io.StringIO(json.dumps({'id': 1, 'result': {}}) + '\n' +
                                    json.dumps({'id': 2, 'result': {'status': 'ok'}}) + '\n')
        with patch.object(pilot_defaults.subprocess, 'Popen', return_value=process):
            pilot_defaults.apply_defaults(dict(model='gpt-6.1-sol', reasoning_effort='low'), executable='codex')
        requests = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([r['method'] for r in requests], ['initialize', 'config/batchWrite'])
        self.assertEqual(requests[1]['params']['edits'], [
            dict(keyPath='model', value='gpt-6.1-sol', mergeStrategy='replace'),
            dict(keyPath='model_reasoning_effort', value='low', mergeStrategy='replace')])
        process.wait.assert_called()

    def test_revision_applies_once_and_failure_retries(self):
        device = SimpleNamespace(origin='http://localhost:8767', account='student', request=MagicMock())
        device.request.return_value = dict(model='gpt-6.1-sol', reasoning_effort='low', revision='v1')
        with tempfile.TemporaryDirectory() as folder, patch.object(pilot_defaults, 'apply_defaults') as apply:
            apply.side_effect = [ValueError('temporarily unavailable'), {}, {}]
            with self.assertRaises(ValueError):
                pilot_defaults.sync(device, folder)
            pilot_defaults.sync(device, folder)
            pilot_defaults.sync(device, folder)
            self.assertEqual(apply.call_count, 2)
            device.request.return_value['revision'] = 'v2'
            pilot_defaults.sync(device, folder)
            self.assertEqual(apply.call_count, 3)


if __name__ == '__main__':
    unittest.main()

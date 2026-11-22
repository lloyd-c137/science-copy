from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import json
import unittest
from unittest.mock import patch

from proposal_app import pilot_folder


class FolderPickerTest(unittest.TestCase):
    def test_cloud_origin_and_nonce_are_required_before_local_path_is_returned(self):
        origin = 'https://school.example'
        nonce = 'a' * 48
        path = 'D:\\科研\\我的课题'
        ready = Event()
        choose = Event()
        servers = []
        real_server = pilot_folder.ThreadingHTTPServer

        def open_server(address, handler):
            server = real_server(address, handler)
            servers.append(server)
            ready.set()
            return server

        def select(create):
            self.assertFalse(create)
            choose.wait(5)
            return path

        with patch.object(pilot_folder, 'ThreadingHTTPServer', open_server), patch.object(pilot_folder, 'select_folder', select):
            worker = Thread(target=pilot_folder.handoff, args=(origin, nonce, False, 0), daemon=True)
            worker.start()
            self.assertTrue(ready.wait(5))

            def request(token, site):
                client = HTTPConnection('127.0.0.1', servers[0].server_port, timeout=5)
                try:
                    client.request('GET', '/folder/' + token, headers={'Origin': site})
                    response = client.getresponse()
                    return response.status, response.getheader('Access-Control-Allow-Origin'), response.read()
                finally:
                    client.close()

            self.assertEqual(request(nonce, 'https://other.example')[0], 403)
            self.assertEqual(request('b' * 48, origin)[0], 403)
            self.assertEqual(request(nonce, origin)[:2], (202, origin))
            choose.set()
            for _ in range(10):
                status, cors, raw = request(nonce, origin)
                if status == 200:
                    break
            self.assertEqual((status, cors, json.loads(raw)), (200, origin, {'path': path}))
            worker.join(5)
            self.assertFalse(worker.is_alive())

    def test_create_uses_selected_parent_and_requires_a_new_child_name(self):
        with TemporaryDirectory() as tmp, patch.object(pilot_folder.sys, 'platform', 'win32'):
            with patch.object(pilot_folder, 'windows_dialog', return_value=(tmp, '数字人观察')):
                created = Path(pilot_folder.select_folder(True))
                self.assertEqual(created.parent, Path(tmp).resolve())
                self.assertTrue(created.is_dir())
                with self.assertRaisesRegex(ValueError, '已存在'):
                    pilot_folder.select_folder(True)
            with patch.object(pilot_folder, 'windows_dialog', return_value=(tmp, '..')):
                with self.assertRaisesRegex(ValueError, '不能使用'):
                    pilot_folder.select_folder(True)
            with patch.object(pilot_folder, 'windows_dialog', return_value=(None, None)):
                self.assertIsNone(pilot_folder.select_folder(False))

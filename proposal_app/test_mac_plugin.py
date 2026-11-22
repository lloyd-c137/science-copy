import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from proposal_app import build_plugin_pilot, pilot_client, pilot_install


class MacPluginTests(unittest.TestCase):
    def test_portable_package_and_installed_mcp_use_external_interpreter(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1], prefix='.mac-test-') as temporary:
            root = Path(temporary)
            zip_path = root / 'mac.zip'
            build_plugin_pilot.build(zip_path, 'https://school.example', 'macos')
            with ZipFile(zip_path) as archive:
                prefix = '开题手记-macOS/'
                self.assertEqual([name for name in archive.namelist() if name.endswith('.command')],
                                 [prefix + '安装开题手记.command'])
                for name in ('安装开题手记.command',):
                    script = archive.getinfo(prefix + name)
                    self.assertEqual(script.create_system, 3)
                    self.assertEqual((script.external_attr >> 16) & 0o777, 0o755)
                    self.assertTrue(archive.read(script).startswith(b'#!/bin/bash\n'))
                config = json.loads(archive.read(prefix + 'website.json'))
                self.assertEqual(config['platform'], 'macos')
                self.assertFalse(any('/runtime/' in name for name in archive.namelist()))
                archive.extractall(root / 'package')
            bundle = root / 'package' / prefix
            interpreter = Path(sys.executable)
            release, state, origin = pilot_install.install(
                bundle, root / 'Application Support', 'other.school.example', interpreter=interpreter)
            plugin = release / 'marketplace/plugins/research-coach'
            manifest = json.loads((plugin / '.codex-plugin/plugin.json').read_text('utf-8'))
            self.assertEqual(manifest['version'], pilot_install.VERSION)
            mcp = json.loads((plugin / '.mcp.json').read_text('utf-8'))['mcpServers']['proposal_coach']
            self.assertEqual(mcp['command'], str(interpreter))
            self.assertEqual(mcp['args'][-2:], ['--origin', 'https://other.school.example'])
            self.assertEqual(mcp['env']['PROPOSAL_PILOT_STATE'], str(state))
            self.assertEqual(origin, 'https://other.school.example')
            for skill in ('research-proposal-coach', 'research-proposal-review'):
                self.assertTrue((plugin / 'skills' / skill / 'SKILL.md').is_file())

    def test_mac_hash_matches_browser_and_keeps_case(self):
        path = '/Users/Lin/Documents/开题 Café'
        self.assertEqual(pilot_client.workspace_hash('/Users/Lin/Desktop/../Documents/开题 Cafe\u0301'),
                         hashlib.sha256(('macos:' + path).encode()).hexdigest())
        self.assertNotEqual(pilot_client.workspace_hash(path.lower()), pilot_client.workspace_hash(path))


if __name__ == '__main__':
    unittest.main()

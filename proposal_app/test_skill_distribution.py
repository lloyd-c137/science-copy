import io
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.request import urlopen
import zipfile

from proposal_app import server, skill_distribution as skills, coach_mcp
from proposal_app.coach_launcher import CoachLauncher
from proposal_app.review_launcher import ReviewLauncher


class SkillDownloadTests(unittest.TestCase):
    def test_role_packages_include_complete_references_and_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in (skills.NAME, skills.REVIEW_NAME):
                manifest, files = skills.release(name)
                self.assertIn('references/workflow.md', files)
                with patch.object(skills, 'build_opener') as opener:
                    opener.return_value.open.return_value.__enter__.return_value.read.return_value = skills.bundle(name)
                    folder = skills.install(directory, 'http://localhost:8765', skills.version(name), name=name)
                    self.assertEqual(folder.name, name)
                    self.assertEqual(skills.installed(directory, name), folder)
                    self.assertEqual(set(manifest['files']), set(files))
                    opener.return_value.open.assert_called_once_with('http://localhost:8765' + skills.download_path(name), timeout=20)
            self.assertNotEqual(skills.version(), skills.version(skills.REVIEW_NAME))

    def test_wrong_role_and_undeclared_archive_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(skills, 'build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = skills.bundle()
            with self.assertRaises(ValueError):
                skills.install(directory, 'http://localhost:8765', name=skills.REVIEW_NAME)
            output = io.BytesIO(skills.bundle())
            with zipfile.ZipFile(output, 'a') as archive:
                archive.writestr(skills.PREFIX + 'references/undeclared.md', 'unexpected')
            response.read.return_value = output.getvalue()
            with self.assertRaises(ValueError):
                skills.install(directory, 'http://localhost:8765')
            self.assertIsNone(skills.installed(directory))

    def test_expected_release_updates_old_package_and_reuses_current(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(skills, 'build_opener') as opener:
                opener.return_value.open.return_value.__enter__.return_value.read.return_value=skills.bundle()
                folder=skills.install(directory,'http://localhost:8765',expected_version=skills.version())
                manifest_path=folder/'distribution.json'
                manifest=json.loads(manifest_path.read_text('utf-8'))
                manifest['version']='older-release'
                manifest_path.write_text(json.dumps(manifest),'utf-8')
                skills.install(directory,'http://localhost:8765',expected_version=skills.version())
                self.assertEqual(json.loads(manifest_path.read_text('utf-8'))['version'],skills.version())
                self.assertEqual(opener.call_count,2)
                skills.install(directory,'http://localhost:8765',expected_version=skills.version())
                self.assertEqual(opener.call_count,2)

    def test_clean_workstation_download_install_read_and_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with server.serve(root/'test.sqlite', 0) as api:
                worker = Thread(target=api.serve_forever, daemon=True)
                worker.start()
                origin = f'http://127.0.0.1:{api.server_port}'
                try:
                    with urlopen(origin+skills.DOWNLOAD) as response:
                        self.assertEqual(response.headers.get_content_type(), 'application/zip')
                        self.assertIn('attachment', response.headers['Content-Disposition'])
                        with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                            self.assertIn(skills.PREFIX+'SKILL.md', archive.namelist())
                    project = root/'new-student'
                    self.assertFalse(project.exists())
                    installed = skills.install(project, origin)
                    self.assertTrue((installed/'references/yau-review.md').is_file())
                    # Read exactly the installed files through the teaching MCP.
                    with patch.dict(coach_mcp.LESSONS, {'coach':installed/'SKILL.md'}):
                        self.assertIn('research-proposal-coach', coach_mcp.run_tool('proposal_guide', {}))
                    with patch.object(skills, 'build_opener', side_effect=AssertionError('不应重复下载')):
                        self.assertEqual(skills.install(project, origin), installed)
                    (installed/'SKILL.md').write_text('incomplete', 'utf-8')
                    self.assertIsNone(skills.installed(project))
                    self.assertEqual(skills.install(project, origin), installed)
                    self.assertIsNotNone(skills.installed(project))
                    teacher = skills.install(root/'new-teacher', origin, name=skills.REVIEW_NAME)
                    self.assertEqual(teacher.name, skills.REVIEW_NAME)
                    text = ReviewLauncher(root/'reviews').discussion_instructions(
                        {'_skill_dir':str(teacher),'_reviewer_name':'老师','student_name':'学生','id':'P1'}, '')
                    self.assertIn('辅助审阅助手', text)
                    self.assertIn((teacher/'references/workflow.md').read_text('utf-8'), text)
                finally:
                    api.shutdown()
                    worker.join()

    def test_bad_download_leaves_no_installed_skill_and_can_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(skills, 'build_opener') as opener:
                response = opener.return_value.open.return_value.__enter__.return_value
                response.read.return_value = b'not a zip'
                with self.assertRaisesRegex(ValueError, '无法从网站安装'):
                    skills.install(directory, 'http://localhost:8765')
                self.assertIsNone(skills.installed(directory))
                response.read.return_value = skills.bundle()
                self.assertTrue((skills.install(directory, 'http://localhost:8765')/'SKILL.md').is_file())

    def test_launcher_failure_never_opens_codex_without_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'connection.json').write_text(json.dumps({'server':'http://localhost:8765'}),'utf-8')
            launcher=CoachLauncher(root,open_desktop=False)
            with patch('proposal_app.coach_launcher.install_skill',side_effect=ValueError('Skill 下载失败')), patch('proposal_app.coach_launcher.subprocess.Popen') as process:
                launcher.run(('U1','P1'),root,root,'codex',{'id':'P1'})
                process.assert_not_called()
            result=json.loads((root/'conversation.json').read_text('utf-8'))
            self.assertEqual(result['status'],'error')
            self.assertIn('Skill',result['error'])


if __name__ == '__main__':
    unittest.main()

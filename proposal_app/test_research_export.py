import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from proposal_app import research_export, server


class ResearchExportTests(unittest.TestCase):
    def test_package_keeps_fixed_version_and_existing_exports_without_private_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'.coach').mkdir();(root/'我的笔记').mkdir()
            (root/'成果.md').write_text('实际自动导出','utf-8')
            (root/'我的笔记/私人.md').write_text('自己写的笔记','utf-8')
            (root/'.coach/readable-manifest.json').write_text(json.dumps({'files':{'result':'成果.md'}}),'utf-8')
            card={'research':{'objects':[],'deliverables':[{'id':'P','revision':1,'chapters':{'method':'原提交的方法'}}]},'files':[],'materials':[]}
            raw=research_export.bundle(card,root,[{'name':'研究.csv','content':b'x,y\n1,2'}])
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                self.assertIn('原提交的方法',archive.read('Proposal/提交版本-001.md').decode())
                self.assertEqual(archive.read('本地成果/成果.md').decode(),'实际自动导出')
                self.assertEqual(archive.read('附件/001-研究.csv'),b'x,y\n1,2')
                self.assertFalse(any('私人' in name for name in archive.namelist()))
                self.assertIn('正式研究结果尚待开展',archive.read('研究过程/报告章节映射.md').decode())
            self.assertEqual((root/'我的笔记/私人.md').read_text('utf-8'),'自己写的笔记')

    def test_legacy_database_is_refused_without_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.sqlite3'
            with closing(sqlite3.connect(path)) as c, c:
                c.execute('CREATE TABLE projects(card TEXT)')
                c.execute('INSERT INTO projects VALUES(?)',(json.dumps({'id':'old','current_step':3}),))
            before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'旧六阶段'):
                server.init_db(path)
            self.assertEqual(path.read_bytes(),before)


if __name__=='__main__': unittest.main()

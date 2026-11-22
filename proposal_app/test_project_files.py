import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from proposal_app import project_files

class ProjectFiles(unittest.TestCase):
    def test_notes_search_read_pagination_and_no_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);notes=root/'我的笔记';notes.mkdir()
            p=notes/'观察.md';p.write_text('个人猜想\n手语输入：需要计入改错时间。\n尚未验证。','utf-8')
            before=p.read_bytes();stamp=p.stat().st_mtime_ns
            result=project_files.search(root,'手语 改错')
            self.assertEqual(result['files'][0]['path'],'我的笔记/观察.md')
            self.assertEqual(result['files'][0]['matches'][0]['line'],2)
            first=project_files.read(root,'我的笔记/观察.md',limit=7)
            second=project_files.read(root,'我的笔记/观察.md',offset=first['next_offset'])
            self.assertEqual(first['text']+second['text'],before.decode())
            self.assertEqual(p.read_bytes(),before);self.assertEqual(p.stat().st_mtime_ns,stamp)

    def test_private_paths_and_traversal_are_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir();(root/'.coach').mkdir()
            (root/'.coach/token.txt').write_text('secret')
            (Path(tmp)/'outside.txt').write_text('private')
            for name in ('../outside.txt',str(Path(tmp)/'outside.txt'),'.coach/token.txt','file.txt:stream'):
                with self.assertRaises(ValueError):project_files.read(root,name)
            self.assertEqual(project_files.search(root,'secret')['files'],[])

    def test_symlink_does_not_escape_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir();outside=Path(tmp)/'private.txt';outside.write_text('private')
            try:(root/'link.txt').symlink_to(outside)
            except OSError:self.skipTest('Symlink creation unavailable')
            with self.assertRaises(ValueError):project_files.read(root,'link.txt')
            self.assertEqual(project_files.search(root,'private')['files'],[])

    def test_word_and_unparsed_documents_report_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with zipfile.ZipFile(root/'笔记.docx','w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>试测记录</w:t></w:r></w:p></w:body></w:document>')
            (root/'论文.pdf').write_bytes(b'%PDF')
            self.assertIn('试测记录',project_files.read(root,'笔记.docx')['text'])
            self.assertFalse(project_files.read(root,'论文.pdf')['readable'])

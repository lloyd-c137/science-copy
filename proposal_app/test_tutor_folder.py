import json
from pathlib import Path
import tempfile
import unittest

from proposal_app.configure_tutor_folder import configure
from proposal_app.tutor_folder import shared_root, project_folder
from proposal_app.tutor_environment import profile

class FolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.root=self.base/'开题';self.root.mkdir()

    def test_configuration_reusable_for_new_children_and_no_duplicate_hooks(self):
        configure(self.root)
        first=(self.root/'.codex/hooks.json').read_bytes()
        configure(self.root)
        self.assertEqual(first,(self.root/'.codex/hooks.json').read_bytes())
        for name in ('手语识别','化学炼丹','新增项目'):
            p=self.root/name;p.mkdir()
            self.assertEqual(shared_root(p),self.root.resolve())
            self.assertNotIn('[[hooks.',profile(p,home=self.base/'empty-home'))
        outside=self.base/'私人项目';outside.mkdir()
        self.assertIsNone(shared_root(outside))

    def test_never_reads_siblings_or_resolves_external_path(self):
        configure(self.root)
        a=self.root/'A';b=self.root/'B'
        for p in (a,b):
            (p/'.coach').mkdir(parents=True)
            (p/'.coach/identity.json').write_text('{}')
        sub=a/'资料';sub.mkdir()
        self.assertEqual(project_folder(sub,self.root),a.resolve())
        self.assertIsNone(project_folder(self.root,self.root))
        self.assertIsNone(project_folder(self.base,self.root))

    def test_independent_child_repository_rejected_before_modification(self):
        (self.root/'child/.git').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'独立仓库'):configure(self.root)
        self.assertFalse((self.root/'.tanyue-coach').exists())

    def test_missing_native_hook_does_not_disable_project_hook(self):
        configure(self.root)
        (self.root/'.codex/hooks.json').unlink()
        self.assertIsNone(shared_root(self.root))

    def test_foreign_configuration_never_overwritten(self):
        p=self.root/'.codex/hooks.json';p.parent.mkdir();p.write_text('{}')
        with self.assertRaises(ValueError):configure(self.root)
        self.assertEqual(p.read_text(),'{}')

if __name__=='__main__':unittest.main()

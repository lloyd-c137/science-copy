import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from proposal_app.project_archive import ProjectArchive
from proposal_app.readable_archive import export_attachment, export_readable


class ReadableArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.card = {"title": "校园照片研究", "steps": [
            {"number": 1, "title": "提出问题", "fields": [{"key": "question", "label": "我想研究的问题"}], "data": {"question": "如何比较清晰度？"}},
            {"number": 2, "title": "阅读文献", "fields": [], "data": {}},
            {"number": 6, "title": "整理报告", "fields": [{"key": "method", "label": "研究方法"}], "data": {"method": "固定放大倍数"}}],
            "materials": [{"title": "照片质量", "url": "https://example.org/paper", "help": "定义指标", "limit": "样本不同"}]}
        self.archive = {"conversations": [{"step": 1, "messages": [
            {"id": "u1", "role": "user", "text": "我观察到了模糊"},
            {"id": "a1", "role": "assistant", "text": "试着固定观察位置"},
            {"role": "tool", "text": "private tool output"}]}],
            "feedback": [{"step": 1, "dimension": "使用证据", "observation": "给出了观察", "evidence_id": "u1", "next_action": "记录比较条件"}]}

    def test_research_materials_skip_discussion_navigation_links(self):
        card = dict(self.card, id='P123', student_id='U1', current_step=3, files=[])
        text = ('[开题手记](https://192.168.0.96:8843/?project=P123)\n'
                '[连接插件](https://192.168.0.96:8843/first-use.html)\n'
                '[项目旧地址](https://old.example.test/?project=P123)\n'
                '[原文](https://journal.example.test/paper)')
        data = {'conversations': [{'step': 3, 'messages': [{'id': 'M1', 'role': 'assistant', 'text': text}]}]}
        archive = ProjectArchive(self.root, site_origin='https://192.168.0.96:8843')
        with patch.object(archive, 'read', return_value=data):
            result = archive.enrich(card)
        self.assertEqual([m['title'] for m in result['materials']], ['原文'])
        self.assertEqual(data['conversations'][0]['messages'][0]['text'], text)

    def test_human_labels_and_visible_messages(self):
        export_readable(self.root, self.card, self.archive)
        stage = (self.root / "阶段成果/01-提出问题.md").read_text("utf-8")
        self.assertIn("## 我想研究的问题", stage)
        self.assertIn("如何比较清晰度？", stage)
        self.assertFalse((self.root / "阶段成果/02-阅读文献.md").exists())
        self.assertIn("## 研究方法", (self.root / "开题报告.md").read_text("utf-8"))
        refs = (self.root / "文献/参考资料.md").read_text("utf-8")
        for value in self.card["materials"][0].values():
            self.assertIn(value, refs)
        chat = (self.root / "学习记录/阶段01-对话.md").read_text("utf-8")
        self.assertIn("我观察到了模糊", chat)
        self.assertNotIn("private tool output", chat)
        self.assertIn("> 我观察到了模糊", (self.root / "学习记录/学习反馈.md").read_text("utf-8"))

    def test_personal_files_untouched_and_repeat_export_stable(self):
        (self.root / "我的笔记").mkdir()
        note = self.root / "我的笔记/想法.md"
        note.write_text("我的原创", "utf-8")
        existing = self.root / "项目说明.md"
        existing.write_text("自己的说明", "utf-8")
        first = export_readable(self.root, self.card, self.archive)
        paths = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.card["title"] = "新问题"
        second = export_readable(self.root, self.card, self.archive)
        self.assertEqual(first, second)
        self.assertEqual(paths, sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")))
        self.assertEqual(existing.read_text("utf-8"), "自己的说明")
        self.assertEqual(note.read_text("utf-8"), "我的原创")
        self.assertIn("新问题", (self.root / first["project"]).read_text("utf-8"))
        self.card["steps"][0]["data"] = {}
        export_readable(self.root, self.card, self.archive)
        self.assertNotIn("如何比较清晰度", (self.root / first["stage:1"]).read_text("utf-8"))

    def test_empty_report_not_generated(self):
        self.card["steps"][-1]["data"] = {}
        export_readable(self.root, self.card, {})
        self.assertFalse((self.root / "开题报告.md").exists())
        self.assertEqual(list((self.root / "我的笔记").iterdir()), [])

    def test_empty_sections_are_absent_but_owned_files_can_be_cleared(self):
        self.card["materials"] = [{}]
        archive = {"feedback": [{}], "conversations": [{"step": 2, "messages": []}]}
        export_readable(self.root, self.card, archive)
        for relative in ("文献/参考资料.md", "学习记录/学习反馈.md", "学习记录/阶段02-对话.md"):
            self.assertFalse((self.root / relative).exists())
        self.card["materials"] = [{"title": "论文", "url": "https://example.org/paper"}]
        export_readable(self.root, self.card, self.archive)
        material_path = self.root / "文献/参考资料.md"
        self.assertNotIn("局限：", material_path.read_text("utf-8"))
        self.assertNotIn("对本研究的帮助：", material_path.read_text("utf-8"))
        self.card["materials"] = []
        export_readable(self.root, self.card, {})
        self.assertEqual(material_path.read_text("utf-8").strip(), "# 参考资料")
        self.assertEqual((self.root / "学习记录/学习反馈.md").read_text("utf-8").strip(), "# 学习反馈")

    def test_extra_data_and_nested_papers_are_preserved_with_chinese_labels(self):
        self.card["steps"][0]["data"].update({
            "route": "pilot", "notes": "需要重新拍照", "empty": "  ",
            "count": 0, "confirmed": False, "custom": "额外研究发现",
            "papers": [{"title": "研究文献", "study": "照片压缩", "location": "第3页", "finding": "边缘变化", "limit": "仅有白天样本", "source": "https://example.org", "key": "控制变量"}],
        })
        export_readable(self.root, self.card, self.archive)
        stage = (self.root / "阶段成果/01-提出问题.md").read_text("utf-8")
        for value in ("## 后续方向", "先做小试", "## 补充记录", "需要重新拍照", "研究对象与内容：照片压缩", "原文位置：第3页", "研究发现：边缘变化", "局限：仅有白天样本", "要点：控制变量", "额外研究发现", "## count\n\n0", "## confirmed\n\nFalse"):
            self.assertIn(value, stage)
        self.assertNotIn("## empty", stage)
        description = (self.root / "项目说明.md").read_text("utf-8")
        self.assertIn("由工作台自动同步更新", description)
        self.assertIn("个人补充请放在“我的笔记”中", description)

    def test_attachment_safety_routing_collision_and_stability(self):
        pdf = export_attachment(self.root, "F1234567890abcdefgh", "../../研究文献.pdf", b"PDF")
        self.assertTrue(pdf.startswith("文献/研究文献-F1234567890"))
        self.assertEqual((self.root / pdf).read_bytes(), b"PDF")
        self.assertEqual(pdf, export_attachment(self.root, "F1234567890abcdefgh", "changed.pdf", b"NEW"))
        self.assertEqual((self.root / pdf).read_bytes(), b"NEW")
        other = export_attachment(self.root, "F1234567890zzzzzzzz", "研究文献.pdf", b"OTHER")
        self.assertNotEqual(pdf, other)
        text = export_attachment(self.root, "../../bad", "C:\\fake\\CON.txt", b"notes")
        self.assertTrue(text.startswith("研究过程/_CON-"))
        self.assertTrue((self.root / text).resolve().is_relative_to(self.root.resolve()))
        manifest = json.loads((self.root / ".coach/readable-manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["files"]["attachment:../../bad"], text)

    def test_unknown_attachment_collision_preserves_original(self):
        original = export_attachment(self.root, "F1", "资料.pdf", b"personal")
        # Without manifest ownership an existing file belongs to the student.
        (self.root / ".coach/readable-manifest.json").write_text('{"files": {}}', "utf-8")
        exported = export_attachment(self.root, "F1", "资料.pdf", b"exported")
        self.assertNotEqual(original, exported)
        self.assertEqual((self.root / original).read_bytes(), b"personal")
        self.assertEqual((self.root / exported).read_bytes(), b"exported")

    def test_concurrent_exports_retain_all_manifest_entries(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            paths = list(pool.map(lambda i: export_attachment(self.root, f"F{i}", "数据.csv", str(i).encode()), range(8)))
        export_readable(self.root, self.card, self.archive)
        manifest = json.loads((self.root / ".coach/readable-manifest.json").read_text("utf-8"))["files"]
        for i, path in enumerate(paths):
            self.assertEqual(manifest[f"attachment:F{i}"], path)
            self.assertEqual((self.root / path).read_bytes(), str(i).encode())


if __name__ == "__main__":
    unittest.main()

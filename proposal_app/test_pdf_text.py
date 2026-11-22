"""PDF extraction tests use disposable documents, never classroom materials."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from proposal_app import pdf_text, project_files


@unittest.skipUnless(importlib.util.find_spec('pymupdf'), 'Optional PyMuPDF is not installed')
class PdfProjectFiles(unittest.TestCase):
    def fixture(self, root, pages):
        import pymupdf
        path = Path(root) / 'paper.pdf'
        with pymupdf.open() as pdf:
            for content in pages:
                page = pdf.new_page()
                if content:
                    page.insert_text((60, 60), content)
            pdf.save(path)
        return path

    def test_physical_pages_search_pagination_and_original_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root, ['Baseline observations', 'Independent replication'])
            before = path.read_bytes(), path.stat().st_mtime_ns
            found = project_files.search(root, 'replication')['files'][0]
            self.assertEqual(found['matches'][0]['page'], 2)
            full = project_files.read(root, path.name)
            self.assertTrue(full['document']['complete'])
            self.assertEqual([p['page'] for p in full['pages']], [1, 2])
            start = full['pages'][1]['start_offset']
            first = project_files.read(root, path.name, limit=start)
            second = project_files.read(root, path.name, offset=first['next_offset'])
            self.assertEqual(first['text'] + second['text'], full['text'])
            self.assertEqual(second['pages'][0]['page'], 2)
            self.assertIn('Independent replication', second['text'])
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_no_text_and_mixed_documents_explicitly_report_unparsed_pages(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root, [None, None])
            result = project_files.read(root, path.name)
            self.assertFalse(result['readable'])
            self.assertEqual(result['document']['unparsed_pages'], [1, 2])
            self.assertFalse(result['document']['complete'])
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root, ['Readable', None])
            result = project_files.read(root, path.name)
            self.assertTrue(result['readable'])
            self.assertFalse(result['document']['complete'])
            self.assertIn('扫描页未解析：2', result['coverage'])

    def test_page_and_decoded_text_limits_do_not_claim_full_reading(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root, ['First page', 'Second page'])
            with patch.object(pdf_text, 'MAX_PAGES', 1):
                result = project_files.read(root, path.name)
            self.assertTrue(result['document']['extraction_limited'])
            self.assertFalse(result['document']['complete'])
            self.assertEqual(result['document']['processed_pages'], 1)
            self.assertNotIn('Second page', result['text'])
            text, coverage, details = pdf_text.extract(path.read_bytes(), 40)
            self.assertTrue(details['extraction_limited'])
            self.assertLessEqual(len((text or '').encode()), 40)
            self.assertIn('后续页未读取', coverage)

    def test_encrypted_pdf_and_oversize_are_unreadable(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root, ['Protected'])
            encrypted = Path(root) / 'encrypted.pdf'
            with pymupdf.open(path) as pdf:
                pdf.save(encrypted, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                         owner_pw='owner-test', user_pw='reader-test')
            self.assertFalse(project_files.read(root, encrypted.name)['readable'])
            with patch.object(project_files, 'MAX_BYTES', 20):
                self.assertFalse(project_files.read(root, path.name)['readable'])


class PdfUnavailable(unittest.TestCase):
    def test_search_budget_counts_extracted_body_not_only_compressed_file(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ('a.pdf', 'b.pdf'):
                (Path(root) / name).write_bytes(b'%PDF')
            with patch.object(project_files, 'MAX_BYTES', 20), patch.object(
                    project_files, 'document_details', return_value=('x' * 300, 'PDF文字层', {})):
                result = project_files.search(root)
            self.assertTrue(result['scan_limited'])
            self.assertTrue(result['files'][0]['readable'])
            self.assertFalse(result['files'][1]['readable'])

    def test_missing_dependency_is_explicit(self):
        with patch.dict('sys.modules', {'pymupdf': None}):
            text, coverage, details = pdf_text.extract(b'%PDF', 100)
        self.assertIsNone(text)
        self.assertIn('requirements-pdf.txt', coverage)
        self.assertFalse(details['complete'])

    def test_corrupt_pdf_does_not_interrupt_search(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'bad.pdf').write_bytes(b'%PDF-invalid')
            (Path(root) / 'good.txt').write_text('needle')
            self.assertEqual(project_files.search(root, 'needle')['files'][0]['path'], 'good.txt')
            self.assertFalse(project_files.read(root, 'bad.pdf')['readable'])


if __name__ == '__main__':
    unittest.main()

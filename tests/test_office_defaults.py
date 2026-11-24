import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import office_defaults  # noqa: E402


class OfficeDefaults(unittest.TestCase):
    def test_creates_documents(self):
        self.assertEqual(len(office_defaults.new_presentation().slides), 0)
        self.assertEqual(len(office_defaults.new_document().paragraphs), 0)

    def test_falls_back_when_library_template_is_unreadable(self):
        import docx
        import pptx
        from pptx.exc import PackageNotFoundError
        calls = []
        real_presentation, real_document = pptx.Presentation, docx.Document

        def broken_presentation(*args):
            calls.append(args)
            if not args:
                raise PackageNotFoundError("broken default template")
            return real_presentation(*args)

        def broken_document(*args):
            if not args:
                raise PackageNotFoundError("broken default template")
            return real_document(*args)

        with mock.patch.object(pptx, "Presentation", broken_presentation), \
             mock.patch.object(docx, "Document", broken_document):
            self.assertEqual(len(office_defaults.new_presentation().slide_layouts), 11)
            self.assertEqual(len(office_defaults.new_document().paragraphs), 0)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[1][0].endswith(".package"))

    def test_unrelated_errors_are_not_hidden(self):
        import pptx
        with mock.patch.object(pptx, "Presentation", side_effect=RuntimeError("other")):
            with self.assertRaises(RuntimeError):
                office_defaults.new_presentation()

    def test_bundled_templates_are_valid_packages(self):
        import base64
        import io
        import zipfile
        for name in ("default-presentation", "default-document"):
            text = (office_defaults.TEMPLATES / f"{name}.b64.txt").read_text(encoding="ascii")
            self.assertIsNone(zipfile.ZipFile(io.BytesIO(base64.b64decode(text))).testzip())


if __name__ == "__main__":
    unittest.main()

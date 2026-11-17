import importlib.util
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "plugins/myway/skills/office-docs/scripts/long-manual/gen_toc.py"
SPEC = importlib.util.spec_from_file_location("manual_gen_toc", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TableOfContentsTests(unittest.TestCase):
    def test_exact_heading_ignores_earlier_mention(self):
        result = MODULE.find_titles("See Section Two later\fSection Two\nbody\f", ["Section Two"])
        self.assertEqual(result[0]["page"], 2)

    def test_missing_or_ambiguous_title_fails(self):
        for text in ("other text\f", "Title\fTitle\f"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                MODULE.find_titles(text, ["Title"])

    def test_duplicate_title_and_bad_skip_fail(self):
        with self.assertRaises(ValueError):
            MODULE.find_titles("Title\f", ["Title", "Title"])
        with self.assertRaises(ValueError):
            MODULE.find_titles("Title\f", ["Title"], skip_pages=3)

    def test_final_pdf_skip_counts_actual_page(self):
        self.assertEqual(MODULE.find_titles("Title\fTitle\f", ["Title"], skip_pages=1)[0]["page"], 2)

    def test_two_toc_pages_and_sixty_unique_headings(self):
        titles = [f"Section {i:02d}" for i in range(1, 61)]
        text = "\f".join(["contents one", "contents two", *titles])
        result = MODULE.find_titles(text, titles, skip_pages=2)
        self.assertEqual(len(result), 60)
        self.assertEqual([item["page"] for item in result], list(range(3, 63)))

    def test_extraction_explicit_utf8_timeout_and_exclusive_output(self):
        output = io.StringIO()
        inputs = {"titles.json": io.StringIO(json.dumps(["First title"]))}
        def open_file(name, mode="r", **kwargs):
            return mock.MagicMock(__enter__=lambda _: output if mode == "x" else inputs[name],
                                  __exit__=lambda *_: False)
        with mock.patch.object(MODULE.subprocess, "run", return_value=mock.Mock(stdout="First title\f")) as run, \
             mock.patch("builtins.open", side_effect=open_file) as opened:
            MODULE.main(["a.pdf", "titles.json", "out.json"])
        self.assertEqual(json.loads(output.getvalue())[0]["page"], 1)
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["timeout"], 120)
        self.assertEqual(opened.call_args.args[1], "x")

    def test_output_rejects_escape_and_preserves_existing_file(self):
        helper = SCRIPT.parent / "output_safety.js"
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required to test manual output safety")
        script = r'''
const {outputPath, copyExclusive} = require(process.argv[1]);
const root = process.argv[2];
for (const name of ['../escape.docx', '..\\escape.docx', 'C:escape.docx', 'NUL.docx']) {
  let rejected = false;
  try { outputPath(root, name); } catch (_) { rejected = true; }
  if (!rejected) throw new Error('unsafe name accepted');
}
let rejected = false;
try { copyExclusive(outputPath(root, 'candidate.docx'), outputPath(root, 'existing.docx')); }
catch (error) { rejected = error.code === 'EEXIST'; }
if (!rejected) throw new Error('existing file was not protected');
'''
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "candidate.docx").write_bytes(b"candidate")
            target = Path(tmp) / "existing.docx"
            target.write_bytes(b"original")
            result = subprocess.run([node, "-e", script, str(helper), tmp], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertEqual(target.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()

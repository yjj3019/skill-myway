import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_edit_tokens.py"
SPEC = importlib.util.spec_from_file_location("check_edit_tokens", SCRIPT)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class EditTokenGuardTests(unittest.TestCase):
    def test_exact_count_reports_removed_and_added_items(self):
        rows = guard.compare("--dry-run 3회 --dry-run", "--dry-run 3회 3회", ["--dry-run", "3회"])
        self.assertEqual([(r["source_count"], r["edited_count"], r["status"]) for r in rows],
                         [(2, 1, "CHANGED"), (1, 2, "CHANGED")])

    def test_matching_literals_do_not_assert_semantic_equivalence(self):
        rows = guard.compare("승인 후 3회", "승인 전 3회", ["3회"])
        self.assertEqual(rows[0]["status"], "MATCH")

    def test_bad_lists_and_absent_source_item_rejected(self):
        for items in ([], [""], ["x", "x"], [True], ["missing"], ["x"] * 257):
            with self.subTest(items=items), self.assertRaises(ValueError):
                guard.compare("x", "x", items)

    def test_cli_never_includes_protected_text_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in (("original", "가상비밀 문자열"), ("edited", "가상비밀 문자열"),
                                  ("tokens", json.dumps(["가상비밀"], ensure_ascii=False))):
                (root / name).write_text(content, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = guard.main(["--source", str(root / "original"), "--edited", str(root / "edited"),
                                     "--protected", str(root / "tokens")])
            self.assertEqual(status, 0)
            self.assertNotIn("가상비밀", output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["semantics"], "NOT VERIFIED")

    def test_cli_reports_unreadable_or_absent_inputs_without_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "original").write_text("원문", encoding="utf-8")
            (root / "edited").write_text("변경", encoding="utf-8")
            (root / "tokens").write_text('["없는값"]', encoding="utf-8")
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                code = guard.main(["--source", str(root / "original"), "--edited", str(root / "edited"),
                                   "--protected", str(root / "tokens")])
            self.assertEqual(code, 2)
            self.assertNotIn("없는값", error.getvalue())

    def test_cli_reports_changed_count_with_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "original").write_text("버전 2.1", encoding="utf-8")
            (root / "edited").write_text("버전 2.2", encoding="utf-8")
            (root / "tokens").write_text('["2.1"]', encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = guard.main(["--source", str(root / "original"), "--edited", str(root / "edited"),
                                   "--protected", str(root / "tokens")])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "CHANGED")


if __name__ == "__main__":
    unittest.main()

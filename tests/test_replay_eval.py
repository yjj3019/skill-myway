import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import replay_eval  # noqa: E402

CASES = {"cases": [
    {"id": "a", "request": "가상", "required": [["alpha"]], "forbidden": []},
    {"id": "b", "request": "가상", "required": [["beta"]], "forbidden": ["bad"]},
    {"id": "c", "request": "가상", "required": [["gamma"]], "forbidden": []},
]}


def summary(entries):
    return {"cases": [{"id": cid, "runs": [{"passed_auto_checks": saved}]} for cid, saved in entries]}


class ReplayEval(unittest.TestCase):
    def run_replay(self, entries, outputs):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "cases.json").write_text(json.dumps(CASES), encoding="utf-8")
            (tmp / "run").mkdir()
            (tmp / "run" / "summary.json").write_text(json.dumps(summary(entries)), encoding="utf-8")
            for name, text in outputs.items():
                (tmp / "run" / f"{name}.md").write_text(text, encoding="utf-8")
            cases = replay_eval.load_cases(tmp / "cases.json")
            return {row["case"]: row["status"] for row in replay_eval.replay_summary(tmp / "run" / "summary.json", cases)}

    def test_classifies_before_and_after(self):
        statuses = self.run_replay(
            [("a", True), ("b", True), ("c", False), ("d", True), ("e", None)],
            {"a": "alpha", "b": "beta bad", "c": "gamma"})
        self.assertEqual(statuses["a"], "SAME_PASS")
        self.assertEqual(statuses["b"], "PASS_TO_FAIL")
        self.assertEqual(statuses["c"], "FAIL_TO_PASS")
        self.assertEqual(statuses["d"], "CASE_REMOVED")
        self.assertEqual(statuses["e"], "CASE_REMOVED")

    def test_missing_output_and_unchecked(self):
        statuses = self.run_replay([("a", True), ("b", None)], {"b": "beta"})
        self.assertEqual(statuses["a"], "MISSING_OUTPUT")
        self.assertEqual(statuses["b"], "SAVED_UNCHECKED")

    def test_same_fail(self):
        self.assertEqual(self.run_replay([("a", False)], {"a": "nothing"})["a"], "SAME_FAIL")

    def test_empty_output_fails(self):
        self.assertEqual(self.run_replay([("a", True)], {"a": "  "})["a"], "PASS_TO_FAIL")

    def test_main_rejects_missing_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(replay_eval.main([tmp]), 2)


if __name__ == "__main__":
    unittest.main()

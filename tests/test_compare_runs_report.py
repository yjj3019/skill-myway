import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import contract_json  # noqa: E402
import compare_runs_report  # noqa: E402


BASE = [
    {"id": "a", "repeats": 3, "attempted": 3, "completed": 2, "execution_failed": 1,
     "timed_out": 0, "not_run": 0, "auto_check_pass_rate": 0.67, "overall_status": "NOT VERIFIED"},
    {"id": "b", "repeats": 2, "attempted": 0, "completed": 0, "execution_failed": 0,
     "timed_out": 0, "not_run": 2, "auto_check_pass_rate": None},
]
CAND = [
    {"id": "a", "repeats": 3, "attempted": 3, "completed": 3, "execution_failed": 0,
     "timed_out": 0, "not_run": 0, "auto_check_pass_rate": 1.0},
    {"id": "c", "repeats": 1, "attempted": 1, "completed": 1, "execution_failed": 0,
     "timed_out": 0, "not_run": 0, "auto_check_pass_rate": 1.0},
]


def doc(cases):
    return {"schema_version": 5, "platform": "codex", "cases": cases}


class TestRead(unittest.TestCase):
    def test_wrong_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "base.json")
            with open(base, "w", encoding="utf-8") as handle:
                json.dump({"schema_version": 4, "platform": "codex", "cases": []}, handle)
            with open(os.path.join(tmp, "cand.json"), "w", encoding="utf-8") as handle:
                json.dump(doc([]), handle)
            self.assertEqual(
                compare_runs_report.main(["--baseline", base, "--candidate", os.path.join(tmp, "cand.json"),
                                          "--out", os.path.join(tmp, "out")]), 1)

    def test_duplicate_case_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "base.json")
            with open(base, "w", encoding="utf-8") as handle:
                json.dump({"schema_version": 5, "platform": "codex", "cases": [{"id": "a"}, {"id": "a"}]}, handle)
            with open(os.path.join(tmp, "cand.json"), "w", encoding="utf-8") as handle:
                json.dump(doc([]), handle)
            self.assertEqual(
                compare_runs_report.main(["--baseline", base, "--candidate", os.path.join(tmp, "cand.json"),
                                          "--out", os.path.join(tmp, "out")]), 1)

    def test_unreadable_input_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "base.json"), "w", encoding="utf-8") as handle:
                json.dump(doc([{"id": "a"}]), handle)
            self.assertEqual(
                compare_runs_report.main(["--baseline", os.path.join(tmp, "base.json"),
                                          "--candidate", os.path.join(tmp, "missing.json"),
                                          "--out", os.path.join(tmp, "out")]), 1)


class TestRows(unittest.TestCase):
    def test_pairing_and_side_flags(self):
        rows, totals, status = compare_runs_report.build_rows(
            {c["id"]: c for c in BASE}, {c["id"]: c for c in CAND})
        by_id = {row[0]: row for row in rows}
        self.assertEqual(by_id["b"][2], ["baseline"])
        self.assertEqual(by_id["c"][2], ["candidate"])
        self.assertEqual(len(by_id["a"][2]), 2)
        self.assertEqual(status["auto_state_differs"], 1)
        self.assertEqual(totals["baseline"]["attempted"], 3)
        self.assertEqual(totals["baseline"]["auto_passed"], 2)
        self.assertEqual(totals["candidate"]["auto_passed"], 4)

    def test_markdown_has_denominators(self):
        rows, totals, status = compare_runs_report.build_rows(
            {c["id"]: c for c in BASE}, {c["id"]: c for c in CAND})
        md = compare_runs_report.build_markdown("b.json", "c.json", "out", rows, totals, status)
        self.assertIn("기준선·후보 대조 요약", md)
        self.assertIn("미실행 2", md)
        self.assertIn("| 측 | 예정 | 시도 | 완료 | 실패 | 타임아웃 | 미실행 | 자동 통과 |", md)


class TestMain(unittest.TestCase):
    def test_saves_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "base.json")
            cand = os.path.join(tmp, "cand.json")
            out = os.path.join(tmp, "out")
            with open(base, "w", encoding="utf-8") as handle:
                json.dump(doc(BASE), handle)
            with open(cand, "w", encoding="utf-8") as handle:
                json.dump(doc(CAND), handle)
            rc = compare_runs_report.main(["--baseline", base, "--candidate", cand, "--out", out])
            self.assertEqual(rc, 0)
            with open(os.path.join(out, "compare-runs-summary.json"), encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertEqual(saved["totals"]["baseline"]["repeats"], 5)
            self.assertEqual(saved["state"]["both"], 1)
            with open(os.path.join(out, "compare-runs-summary.md"), encoding="utf-8") as handle:
                md = handle.read()
            self.assertIn("| a |", md)
            self.assertIn("NOT VERIFIED", md)


if __name__ == "__main__":
    unittest.main()

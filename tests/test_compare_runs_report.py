import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import contract_json  # noqa: E402
import compare_runs_report  # noqa: E402


BASE = [
    {"id": "a", "repeats": 3, "attempted": 3, "completed": 2, "execution_failed": 1,
     "timed_out": 0, "not_run": 0, "passed_count": 2, "auto_check_pass_rate": 0.67,
     "overall_status": "NOT VERIFIED"},
    {"id": "b", "repeats": 2, "attempted": 0, "completed": 0, "execution_failed": 0,
     "timed_out": 0, "not_run": 2, "passed_count": 0, "auto_check_pass_rate": None},
]
CAND = [
    {"id": "a", "repeats": 3, "attempted": 3, "completed": 3, "execution_failed": 0,
     "timed_out": 0, "not_run": 0, "passed_count": 3, "auto_check_pass_rate": 1.0},
    {"id": "c", "repeats": 1, "attempted": 1, "completed": 1, "execution_failed": 0,
     "timed_out": 0, "not_run": 0, "passed_count": 1, "auto_check_pass_rate": 1.0},
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

    def test_auto_passed_uses_passed_count_not_rounded_rate(self):
        # 101/200 -> rate 0.51을 다시 곱해 반올림하면 102가 되지만 원본 passed_count 101을 쓴다.
        entry = {"id": "a", "repeats": 200, "attempted": 200, "completed": 200, "execution_failed": 0,
                 "timed_out": 0, "not_run": 0, "passed_count": 101, "auto_check_pass_rate": 0.51}
        rows, totals, status = compare_runs_report.build_rows({entry["id"]: entry}, {})
        self.assertEqual(rows[0][1]["baseline"]["auto_passed"], 101)
        self.assertEqual(totals["baseline"]["auto_passed"], 101)
        self.assertEqual(totals["baseline"]["auto_passed_unknown"], 0)

    def test_partial_not_run_still_counts_passed_count(self):
        # 미실행이 있어 rate가 None이어도 passed_count는 정확하므로 집계에 넣는다.
        entry = {"id": "a", "repeats": 3, "attempted": 2, "completed": 2, "execution_failed": 0,
                 "timed_out": 0, "not_run": 1, "passed_count": 2, "auto_check_pass_rate": None}
        rows, totals, status = compare_runs_report.build_rows({entry["id"]: entry}, {})
        self.assertEqual(rows[0][1]["baseline"]["auto_passed"], 2)
        self.assertEqual(totals["baseline"]["auto_passed"], 2)
        self.assertEqual(totals["baseline"]["auto_passed_unknown"], 0)

    def test_invalid_passed_count_is_unknown_and_excluded(self):
        raw = [
            {"id": "a", "repeats": 3, "attempted": 3, "completed": 3, "execution_failed": 0,
             "timed_out": 0, "not_run": 0, "auto_check_pass_rate": 1.0},
            {"id": "b", "repeats": 3, "attempted": 3, "completed": 3, "execution_failed": 0,
             "timed_out": 0, "not_run": 0, "passed_count": -1, "auto_check_pass_rate": None},
            {"id": "c", "repeats": 3, "attempted": 3, "completed": 3, "execution_failed": 0,
             "timed_out": 0, "not_run": 0, "passed_count": 3, "auto_check_pass_rate": None},
        ]
        rows, totals, status = compare_runs_report.build_rows({c["id"]: c for c in raw}, {})
        by_id = {row[0]: row for row in rows}
        self.assertIsNone(by_id["a"][1]["baseline"]["auto_passed"])
        self.assertIsNone(by_id["b"][1]["baseline"]["auto_passed"])
        self.assertEqual(by_id["c"][1]["baseline"]["auto_passed"], 3)
        self.assertEqual(totals["baseline"]["auto_passed"], 3)
        self.assertEqual(totals["baseline"]["auto_passed_unknown"], 2)
        md = compare_runs_report.build_markdown("b.json", "c.json", "out", rows, totals, status)
        self.assertIn("자동 통과 미확인 케이스(합계 제외): 기준선 2건, 후보 0건", md)

    def test_null_repeats_makes_passed_unknown(self):
        # repeats 없이는 상한 검증이 불가하므로 passed_count가 정수여도 미확인으로 둔다.
        entry = {"id": "a", "repeats": None, "attempted": 200, "completed": 200, "execution_failed": 0,
                 "timed_out": 0, "not_run": 0, "passed_count": 101, "auto_check_pass_rate": None}
        rows, totals, status = compare_runs_report.build_rows({entry["id"]: entry}, {})
        self.assertIsNone(rows[0][1]["baseline"]["auto_passed"])
        self.assertEqual(totals["baseline"]["auto_passed"], 0)
        self.assertEqual(totals["baseline"]["auto_passed_unknown"], 1)

    def test_bool_values_are_not_counts(self):
        # bool은 int의 하위형이지만 true를 1로 세지 않는다.
        entry = {"id": "a", "repeats": True, "attempted": True, "completed": True, "execution_failed": 0,
                 "timed_out": 0, "not_run": 0, "passed_count": True, "auto_check_pass_rate": None}
        rows, totals, status = compare_runs_report.build_rows({entry["id"]: entry}, {})
        self.assertIsNone(rows[0][1]["baseline"]["repeats"])
        self.assertIsNone(rows[0][1]["baseline"]["auto_passed"])
        self.assertEqual(totals["baseline"]["auto_passed"], 0)
        self.assertEqual(totals["baseline"]["auto_passed_unknown"], 1)

    def test_inconsistent_counts_are_unknown(self):
        entry = {"id": "a", "repeats": 3, "attempted": 1, "completed": 1,
                 "execution_failed": 0, "timed_out": 0, "not_run": 2, "passed_count": 3}
        rows, totals, _ = compare_runs_report.build_rows({"a": entry}, {})
        self.assertIsNone(rows[0][1]["baseline"]["auto_passed"])
        self.assertEqual(totals["baseline"]["auto_passed_unknown"], 1)

    def test_inconsistent_partition_marks_all_counts_unknown(self):
        entry = dict(BASE[0], not_run=1)
        rows, totals, _ = compare_runs_report.build_rows({"a": entry}, {})
        self.assertIsNone(rows[0][1]["baseline"]["repeats"])
        self.assertEqual(totals["baseline"]["repeats_unknown"], 1)
        self.assertEqual(totals["baseline"]["auto_passed_unknown"], 1)

    def test_partial_counts_that_already_exceed_attempts_are_unknown(self):
        entry = {"id": "a", "repeats": 3, "attempted": 2, "completed": 2,
                 "execution_failed": 1, "timed_out": None, "not_run": 1, "passed_count": 2}
        rows, totals, _ = compare_runs_report.build_rows({"a": entry}, {})
        self.assertIsNone(rows[0][1]["baseline"]["completed"])
        self.assertEqual(totals["baseline"]["completed_unknown"], 1)

    def test_unknown_counts_in_totals_are_not_reported_as_zero(self):
        entries = {"a": dict(BASE[0]), "b": {"id": "b"}}
        rows, totals, status = compare_runs_report.build_rows(entries, {})
        md = compare_runs_report.build_markdown("b", "c", "o", rows, totals, status)
        self.assertIn("? (확인 합계 3, 미확인 1건)", md)
        self.assertEqual(totals["baseline"]["repeats_unknown"], 1)
        self.assertIn("? (확인 합계 2, 미확인 1건)", md)


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

    def test_existing_output_blocks_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "base.json")
            cand = os.path.join(tmp, "cand.json")
            out = os.path.join(tmp, "out")
            with open(base, "w", encoding="utf-8") as handle:
                json.dump(doc(BASE), handle)
            with open(cand, "w", encoding="utf-8") as handle:
                json.dump(doc(CAND), handle)
            os.makedirs(out)
            md_path = os.path.join(out, "compare-runs-summary.md")
            with open(md_path, "w", encoding="utf-8") as handle:
                handle.write("기존 보고서\n")
            rc = compare_runs_report.main(["--baseline", base, "--candidate", cand, "--out", out])
            self.assertEqual(rc, 1)
            with open(md_path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "기존 보고서\n")
            self.assertFalse(os.path.exists(os.path.join(out, "compare-runs-summary.json")))

    def test_existing_both_outputs_are_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "base.json")
            cand = os.path.join(tmp, "cand.json")
            out = os.path.join(tmp, "out")
            with open(base, "w", encoding="utf-8") as handle:
                json.dump(doc(BASE), handle)
            with open(cand, "w", encoding="utf-8") as handle:
                json.dump(doc(CAND), handle)
            os.makedirs(out)
            for name in ("compare-runs-summary.json", "compare-runs-summary.md"):
                with open(os.path.join(out, name), "w", encoding="utf-8") as handle:
                    handle.write(f"기존 {name}\n")
            rc = compare_runs_report.main(["--baseline", base, "--candidate", cand, "--out", out])
            self.assertEqual(rc, 1)

    def test_second_publish_failure_preserves_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "base.json")
            cand = os.path.join(tmp, "cand.json")
            out = os.path.join(tmp, "out")
            with open(base, "w", encoding="utf-8") as handle:
                json.dump(doc(BASE), handle)
            with open(cand, "w", encoding="utf-8") as handle:
                json.dump(doc(CAND), handle)
            real = compare_runs_report.new_output
            calls = {"count": 0}

            def flaky(path):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise OSError("두 번째 게시 주입 실패")
                return real(path)

            with mock.patch.object(compare_runs_report, "new_output", side_effect=flaky):
                rc = compare_runs_report.main(["--baseline", base, "--candidate", cand, "--out", out])
            self.assertEqual(rc, 1)
            self.assertTrue(os.path.exists(os.path.join(out, "compare-runs-summary.json")))
            self.assertFalse(os.path.exists(os.path.join(out, "compare-runs-summary.md")))

    def test_same_bytes_replacement_is_preserved_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, cand, out = (os.path.join(tmp, name) for name in ("base.json", "cand.json", "out"))
            for path in (base, cand):
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(doc(BASE), handle)
            real = compare_runs_report.new_output
            calls = 0
            saved = []
            def flaky(path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    target = os.path.join(out, "compare-runs-summary.json")
                    with open(target, "rb") as handle:
                        contents = handle.read()
                    saved.append(contents)
                    replacement = os.path.join(out, "replacement")
                    with open(replacement, "wb") as handle:
                        handle.write(contents)
                    os.replace(replacement, target)
                    raise OSError("failure")
                return real(path)
            with mock.patch.object(compare_runs_report, "new_output", side_effect=flaky):
                self.assertEqual(compare_runs_report.main(["--baseline", base, "--candidate", cand, "--out", out]), 1)
            with open(os.path.join(out, "compare-runs-summary.json"), "rb") as handle:
                self.assertEqual(handle.read(), saved[0])

    def test_concurrent_runs_do_not_mix_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, cand, out = (os.path.join(tmp, name) for name in ("base.json", "cand.json", "out"))
            other = os.path.join(tmp, "other.json")
            for path in (base, cand, other):
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(doc(BASE), handle)
            barrier = threading.Barrier(2, timeout=10)
            real = compare_runs_report.new_output
            def synchronized(path):
                if path.name.endswith(".json"):
                    barrier.wait()
                return real(path)
            results = []
            def run(baseline):
                results.append(compare_runs_report.main(["--baseline", baseline, "--candidate", cand, "--out", out]))
            with mock.patch.object(compare_runs_report, "new_output", side_effect=synchronized):
                threads = [threading.Thread(target=run, args=(path,)) for path in (base, other)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=15)
                self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(sorted(results), [0, 1])
            for name in ("compare-runs-summary.json", "compare-runs-summary.md"):
                self.assertTrue(os.path.isfile(os.path.join(out, name)))
            with open(os.path.join(out, "compare-runs-summary.json"), encoding="utf-8") as handle:
                baseline = json.load(handle)["baseline_path"]
            with open(os.path.join(out, "compare-runs-summary.md"), encoding="utf-8") as handle:
                self.assertIn(f"- 기준선: {baseline}\n", handle.read())

    def test_rollback_keeps_replaced_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "base.json")
            cand = os.path.join(tmp, "cand.json")
            out = os.path.join(tmp, "out")
            with open(base, "w", encoding="utf-8") as handle:
                json.dump(doc(BASE), handle)
            with open(cand, "w", encoding="utf-8") as handle:
                json.dump(doc(CAND), handle)
            real = compare_runs_report.new_output
            calls = {"count": 0}

            def flaky(path):
                calls["count"] += 1
                if calls["count"] == 2:
                    json_path = os.path.join(out, "compare-runs-summary.json")
                    with open(json_path, "wb") as handle:
                        handle.write(b'{"foreign": true}')
                    raise OSError("두 번째 게시 주입 실패")
                return real(path)

            with mock.patch.object(compare_runs_report, "new_output", side_effect=flaky):
                rc = compare_runs_report.main(["--baseline", base, "--candidate", cand, "--out", out])
            self.assertEqual(rc, 1)
            json_path = os.path.join(out, "compare-runs-summary.json")
            self.assertTrue(os.path.exists(json_path))
            with open(json_path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), '{"foreign": true}')
            self.assertFalse(os.path.exists(os.path.join(out, "compare-runs-summary.md")))


if __name__ == "__main__":
    unittest.main()

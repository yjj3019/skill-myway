import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import run_eval  # noqa: E402
import simulate_eval  # noqa: E402


def sample_cases():
    skills = simulate_eval.skill_names()
    return {
        "schema_version": 1,
        "cases": [
            {"skill": name, "id": f"{name}-x", "request": f"{name} 가상 요청입니다. 충분히 긴 요청.",
             "required": ["결과"], "forbidden": [], "max_chars": 4000}
            for name in skills
        ],
    }


class SimulateEval(unittest.TestCase):
    def test_coverage_and_schema_pass(self):
        self.assertEqual(simulate_eval.validate(sample_cases()), [])

    def test_missing_coverage_fails(self):
        doc = sample_cases()
        doc["cases"] = doc["cases"][:-1]
        errors = simulate_eval.validate(doc)
        self.assertTrue(any("커버리지" in e for e in errors))

    def test_duplicate_and_unknown_skill_fail(self):
        doc = sample_cases()
        doc["cases"].append(dict(doc["cases"][0]))
        doc["cases"].append({"skill": "nope", "id": "nope-1", "request": "충분히 긴 가상 요청입니다.",
                             "required": [], "forbidden": [], "max_chars": 1000})
        errors = simulate_eval.validate(doc)
        self.assertTrue(any("중복" in e for e in errors))
        self.assertTrue(any("알 수 없는 스킬" in e for e in errors))

    def test_unsafe_request_rejected(self):
        doc = sample_cases()
        # 검증기 자신의 예시 규칙(실제 형식 CVE/이메일 금지)에 걸리지 않도록 조각으로 조립한다.
        unsafe = "연락은 test@" + "example.com 으로, " + "CVE-" + "2024" + "-12345 참고"
        doc["cases"][0]["request"] = unsafe
        errors = simulate_eval.validate(doc)
        self.assertTrue(any("민감 패턴" in e for e in errors))

    def test_manifest_is_deterministic(self):
        doc = sample_cases()
        first = simulate_eval.manifest(doc)
        second = simulate_eval.manifest(doc)
        self.assertEqual(first, second)
        self.assertEqual(len(first["cases"]), len(doc["cases"]))
        for item in first["cases"]:
            self.assertEqual(len(item["request_sha256"]), 64)
            self.assertEqual(len(item["skill_sha256"]), 64)


class RunEval(unittest.TestCase):
    def test_evaluate_output_checks(self):
        case = {"required": ["결론", "근거"], "forbidden": ["혁신"], "max_chars": 100}
        ok = run_eval.evaluate_output("결론과 근거를 적었습니다.", case)
        self.assertEqual(ok["missing_required"], [])
        self.assertEqual(ok["forbidden_found"], [])
        self.assertTrue(ok["within_limit"])
        bad = run_eval.evaluate_output("혁신적인 결론", case)
        self.assertEqual(bad["missing_required"], ["근거"])
        self.assertEqual(bad["forbidden_found"], ["혁신"])

    def test_visual_review_cases_need_human_judgment(self):
        document = simulate_eval.load_cases(simulate_eval.DEFAULT_CASES)
        self.assertEqual(simulate_eval.validate(document), [])
        cases = {case["id"]: case for case in document["cases"]}
        for case_id in ("evidence-first-visual-02", "code-review-independent-02"):
            case = cases[case_id]
            self.assertEqual(case["required"], [])
            self.assertEqual(case["forbidden"], [])
            checks = run_eval.evaluate_output("", case)
            # 필수 항목이 없어도 빈 응답은 자동 통과하지 않는다.
            self.assertFalse(checks["nonempty"])
            self.assertEqual(checks["missing_required"], [])
            self.assertEqual(checks["forbidden_found"], [])
            self.assertTrue(checks["within_limit"])

    def test_optional_ending_check_and_schema(self):
        self.assertTrue(run_eval.evaluate_output("내용\n끝. \n", {"ends_with": "끝."})["ends_with_ok"])
        self.assertFalse(run_eval.evaluate_output("끝.\n메모", {"ends_with": "끝."})["ends_with_ok"])
        doc = sample_cases()
        doc["cases"][0]["ends_with"] = "끝."
        self.assertTrue(simulate_eval.validate(doc))
        doc["schema_version"] = 2
        self.assertEqual(simulate_eval.validate(doc), [])
        self.assertEqual(simulate_eval.manifest(doc)["cases"][0]["ends_with"], "끝.")

    def test_length_limit(self):
        case = {"required": [], "forbidden": [], "max_chars": 5}
        self.assertFalse(run_eval.evaluate_output("0123456", case)["within_limit"])

    def test_required_alternatives(self):
        case = {"required": [["미검증", "UNVERIFIED"], "skip"], "forbidden": [], "max_chars": 1000}
        ok = run_eval.evaluate_output("상태는 UNVERIFIED이며 skip 1건입니다.", case)
        self.assertEqual(ok["missing_required"], [])
        bad = run_eval.evaluate_output("상태는 확인됨입니다.", case)
        self.assertEqual(len(bad["missing_required"]), 2)

    def test_forbidden_alternatives(self):
        case = {"forbidden": [["금지", "blocked"]]}
        self.assertEqual(run_eval.evaluate_output("BLOCKED", case)["forbidden_found"], [["금지", "blocked"]])

    def test_main_does_not_grade_failed_or_empty_runs(self):
        doc = sample_cases()
        case = doc["cases"][0]
        case["required"] = []
        case["forbidden"] = []
        runs = [
            {"exit_code": 1, "output": "partial", "stderr_tail": "error", "seconds": 0},
            {"exit_code": None, "output": "", "stderr_tail": "timeout", "seconds": 0},
            {"exit_code": 0, "output": "  ", "stderr_tail": "", "seconds": 0},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cases.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            out = Path(tmp) / "out"
            with mock.patch.object(run_eval, "run_case", side_effect=runs):
                self.assertEqual(run_eval.main(["--cases", str(source), "--out", str(out),
                                                "--only", case["skill"], "--repeat", "3"]), 1)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            results = summary["cases"][0]["runs"]
            self.assertIsNone(results[0]["checks"])
            self.assertIsNone(results[1]["checks"])
            self.assertFalse(results[2]["checks"]["nonempty"])
            self.assertTrue(all(not item["passed_auto_checks"] for item in results))
            self.assertEqual(summary["input_manifest"]["cases"][0]["id"], case["id"])

    def test_usage_limit_stops_remaining_cases_without_grading(self):
        doc = sample_cases()
        message = "You've hit your 5-hour limit · resets 3:50am (Asia/Seoul)"
        run = {"exit_code": 1, "output": message, "stderr_tail": "", "seconds": 1}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cases.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            out = Path(tmp) / "out"
            with mock.patch.object(run_eval, "run_case", return_value=run) as call:
                self.assertEqual(run_eval.main(["--cases", str(source), "--out", str(out), "--repeat", "2"]), 1)
                self.assertEqual(call.call_count, 1)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["schema_version"], 3)
            self.assertEqual(summary["stop_reason"], "claude_usage_limit")
            self.assertIsNone(summary["cases"][0]["pass_rate"])
            self.assertIsNone(summary["cases"][0]["runs"][1]["passed_auto_checks"])
            self.assertEqual(summary["cases"][0]["runs"][0]["status"], "execution_failed")
            self.assertIsNone(summary["cases"][0]["runs"][0]["checks"])
            self.assertEqual(sum(c["not_run"] for c in summary["cases"]), len(doc["cases"]) * 2 - 1)
            self.assertTrue(all(c["attempted"] + c["not_run"] == c["repeats"] for c in summary["cases"]))

    def test_limit_in_diagnostics_detected_before_tail_truncation(self):
        msg = "You've hit your 5-hour limit · resets 3:50am (Asia/Seoul)"
        process = mock.Mock(returncode=1, stdout="warning\n" + msg, stderr="x" * 900)
        with mock.patch.object(run_eval.subprocess, "run", return_value=process):
            result = run_eval.run_case(sample_cases()["cases"][0], "claude", 5)
        self.assertTrue(result["usage_limit"])
        self.assertEqual(result["usage_limit_message"], msg)
        process.returncode = 0
        process.stdout = msg
        with mock.patch.object(run_eval.subprocess, "run", return_value=process):
            self.assertFalse(run_eval.run_case(sample_cases()["cases"][0], "claude", 5)["usage_limit"])

    def test_usage_limit_requires_exact_error_message(self):
        msg = "You've hit your 5-hour limit · resets 3:50am (Asia/Seoul)"
        self.assertTrue(run_eval.claude_usage_limit(msg))
        self.assertFalse(run_eval.claude_usage_limit("설명: " + msg))
        self.assertFalse(run_eval.claude_usage_limit(msg + "\n분석 결과입니다."))
        self.assertFalse(run_eval.claude_usage_limit("A limit should reset later"))

    def test_result_paths_and_existing_files(self):
        doc = sample_cases()
        case = doc["cases"][0]
        case["id"] = "../escape"
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cases.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            out = Path(tmp) / "out"
            run = {"exit_code": 0, "output": "결과", "stderr_tail": "", "seconds": 0}
            with mock.patch.object(run_eval, "run_case", return_value=run) as call:
                args = ["--cases", str(source), "--out", str(out), "--only", case["skill"]]
                self.assertEqual(run_eval.main(args), 0)
                self.assertTrue((out / (run_eval.output_stem(case["id"]) + ".md")).is_file())
                self.assertFalse((Path(tmp) / "escape.md").exists())
                self.assertEqual(run_eval.main(args), 1)
                self.assertEqual(call.call_count, 1)

    def test_long_and_unicode_ids_have_bounded_stems(self):
        for case_id in ("가" * 1000, "a" * 1000, "../escape", "CON"):
            stem = run_eval.output_stem(case_id)
            self.assertLessEqual(len(stem), 100)
            self.assertNotIn("/", stem)
            self.assertNotIn("\\", stem)
        self.assertEqual(run_eval.output_stem("short-id"), "short-id")
        self.assertNotEqual(run_eval.output_stem("가" * 1000), run_eval.output_stem("나" * 1000))

    def test_dry_run_does_not_call_model(self):
        code = run_eval.main(["--dry-run", "--only", "writing"])
        self.assertEqual(code, 0)

    def test_platform_commands(self):
        claude = run_eval.platform_command("claude", "hi")
        self.assertEqual(claude[:2], ["claude", "--plugin-dir"])
        self.assertEqual(run_eval.platform_command("codex", "hi")[:2], ["codex", "exec"])
        self.assertEqual(run_eval.platform_command("grok", "hi")[:2], ["grok", "-p"])
        with self.assertRaises(ValueError):
            run_eval.platform_command("nope", "hi")

    def test_prepare_workdir(self):
        import shutil
        for platform, rel in (("claude", None), ("codex", ".agents/skills"), ("grok", ".grok/skills")):
            workdir = run_eval.prepare_workdir(platform)
            try:
                if rel is None:
                    self.assertEqual(list(workdir.iterdir()), [])
                else:
                    base = workdir / rel
                    self.assertTrue(base.is_dir())
                    names = {p.name for p in base.iterdir() if (p / "SKILL.md").is_file()}
                    self.assertEqual(names, set(simulate_eval.skill_names()))
            finally:
                shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

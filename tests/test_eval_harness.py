import json
import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import run_eval  # noqa: E402
import simulate_eval  # noqa: E402
import check_office  # noqa: E402


def sample_cases():
    skills = simulate_eval.skill_names()
    return {
        "schema_version": 1,
        "cases": [
            {"skill": name, "id": f"{name}-x", "request": f"{name} 가상 요청입니다. 충분히 긴 요청.",
             "required": ["결과"], "forbidden": [], "max_chars": 4000,
             **({"artifact_policy": "conditional"} if name == "office-docs" else {})}
            for name in skills
        ],
    }


class SimulateEval(unittest.TestCase):
    def test_coverage_and_schema_pass(self):
        self.assertEqual(simulate_eval.validate(sample_cases()), [])

    def test_public_cases_cover_each_audit_boundary(self):
        doc = simulate_eval.load_cases(simulate_eval.DEFAULT_CASES)
        self.assertEqual(simulate_eval.validate(doc), [])
        cases = {case["id"]: case for case in doc["cases"]}
        for skill in simulate_eval.skill_names():
            for kind in ("missing", "boundary", "injection"):
                case_id = f"{skill}-audit-{kind}"
                self.assertIn(case_id, cases)
                self.assertTrue(cases[case_id]["required"])
        self.assertTrue(all(case.get("required") or case.get("ends_with") for case in doc["cases"]))

    def test_rhel_missing_identifier_case_checks_response_mode(self):
        doc = simulate_eval.load_cases(simulate_eval.DEFAULT_CASES)
        case = next(case for case in doc["cases"] if case["id"] == "rhel-cve-audit-missing")
        good = run_eval.evaluate_output("CVE 식별자를 알려주세요. 영향 여부는 대화로 답하겠습니다.", case)
        bad = run_eval.evaluate_output("CVE 식별자를 알려주세요. 대화 후 리포트로 정리하겠습니다.", case)
        self.assertEqual(good["missing_required"], [])
        self.assertEqual(good["forbidden_found"], [])
        self.assertTrue(bad["forbidden_found"])

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

    def test_invalid_skill_types_report_errors_without_crashing(self):
        for invalid in ([], {}, None, 42):
            with self.subTest(skill=invalid):
                doc = sample_cases()
                doc["cases"][0]["skill"] = invalid
                errors = simulate_eval.validate(doc)
                self.assertTrue(any("알 수 없는 스킬" in e for e in errors))
                self.assertTrue(any("커버리지 누락" in e for e in errors))

    def test_whitespace_only_ids_are_rejected(self):
        for invalid in ("", "   ", "\t\n"):
            with self.subTest(case_id=invalid):
                doc = sample_cases()
                doc["cases"][0]["id"] = invalid
                self.assertIn("id가 비어 있습니다", simulate_eval.validate(doc))

    def test_max_chars_requires_positive_integer_not_boolean(self):
        for invalid in (True, False, 0, -1, 1.5, "10", None):
            with self.subTest(max_chars=invalid):
                doc = sample_cases()
                doc["cases"][0]["max_chars"] = invalid
                self.assertTrue(any("max_chars가 잘못됐습니다" in e for e in simulate_eval.validate(doc)))
        doc = sample_cases()
        doc["cases"][0]["max_chars"] = 1
        self.assertEqual(simulate_eval.validate(doc), [])

    def test_advisory_check_flag_requires_boolean(self):
        doc = sample_cases()
        doc["cases"][0]["forbid_unprovided_advisories"] = "yes"
        self.assertTrue(any("forbid_unprovided_advisories" in error for error in simulate_eval.validate(doc)))
        doc["cases"][0]["requires_followup"] = 1
        self.assertTrue(any("requires_followup" in error for error in simulate_eval.validate(doc)))

    def test_unprovided_advisory_detection_preserves_input_and_fake_examples(self):
        identifier = "CVE-" + "2024-" + "12345"
        case = {"request": "가상 질문입니다", "forbid_unprovided_advisories": True}
        self.assertEqual(run_eval.evaluate_output(identifier, case)["unexpected_advisory_count"], 1)
        case["request"] += " " + identifier
        self.assertEqual(run_eval.evaluate_output(identifier, case)["unexpected_advisory_count"], 0)
        self.assertEqual(run_eval.evaluate_output("CVE-2099-00001", case)["unexpected_advisory_count"], 0)
        case["forbid_unprovided_advisories"] = False
        case["request"] = "가상 질문입니다"
        self.assertEqual(run_eval.evaluate_output(identifier, case)["unexpected_advisory_count"], 0)

    def test_evaluation_entrypoint_rejects_invalid_cases_before_execution(self):
        doc = sample_cases()
        doc["cases"][0]["skill"] = []
        doc["cases"][0]["max_chars"] = True
        doc["cases"][1]["id"] = " \t "
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output), mock.patch.object(run_eval, "run_case") as run_case:
                result = run_eval.main(["--cases", str(path), "--platform", "codex", "--dry-run"])
        self.assertEqual(result, 1)
        self.assertIn("알 수 없는 스킬", output.getvalue())
        self.assertIn("max_chars가 잘못됐습니다", output.getvalue())
        self.assertIn("id가 비어 있습니다", output.getvalue())
        run_case.assert_not_called()

    def test_unsafe_request_rejected(self):
        doc = sample_cases()
        # 검증기 자신의 예시 규칙(실제 형식 CVE/이메일 금지)에 걸리지 않도록 조각으로 조립한다.
        unsafe = "연락은 admin@" + "mycorp.io 으로 " + "문의하세요"
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
            self.assertEqual(len(item["skill_tree_sha256"]), 64)
            self.assertEqual(item["skill_files_sha256"]["SKILL.md"], item["skill_sha256"])

    def test_manifest_tracks_add_change_and_removal_of_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "sample"
            skill.mkdir()
            (skill / "SKILL.md").write_text("skill", encoding="utf-8")
            document = {"cases": [{"id": "sample-1", "skill": "sample", "request": "example"}]}
            with mock.patch.object(simulate_eval, "SKILLS", root):
                base = simulate_eval.manifest(document)["cases"][0]
                refdir = skill / "references"
                refdir.mkdir()
                ref = refdir / "guide.md"
                ref.write_text("one", encoding="utf-8")
                added = simulate_eval.manifest(document)["cases"][0]
                ref.write_text("two", encoding="utf-8")
                changed = simulate_eval.manifest(document)["cases"][0]
                ref.unlink()
                removed = simulate_eval.manifest(document)["cases"][0]
            self.assertNotEqual(base["skill_tree_sha256"], added["skill_tree_sha256"])
            self.assertNotEqual(added["skill_tree_sha256"], changed["skill_tree_sha256"])
            self.assertEqual(base["skill_tree_sha256"], removed["skill_tree_sha256"])
            self.assertEqual(base["skill_sha256"], changed["skill_sha256"])

    def test_manifest_rejects_linked_skill_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "sample"
            skill.mkdir()
            (skill / "SKILL.md").write_text("skill", encoding="utf-8")
            linked = skill / "linked.md"
            linked.write_text("content", encoding="utf-8")
            original = Path.is_symlink
            with mock.patch.object(simulate_eval, "SKILLS", root), \
                 mock.patch.object(Path, "is_symlink", lambda p: p == linked or original(p)):
                with self.assertRaises(ValueError):
                    simulate_eval.skill_tree_hashes("sample")

    def test_schema_rejects_boolean_missing_fields_and_unknown_fields(self):
        for kind in ("boolean", "missing", "unknown"):
            with self.subTest(kind=kind):
                doc = sample_cases()
                if kind == "boolean":
                    doc["schema_version"] = True
                elif kind == "missing":
                    del doc["cases"][0]["required"]
                else:
                    doc["cases"][0]["max_char"] = 1
                self.assertTrue(simulate_eval.validate(doc))

    def test_schema_rejects_invalid_optional_artifact_settings(self):
        for key, invalid in (("artifact_policy", "unexpected"), ("expected_extensions", ["../bad"])):
            with self.subTest(key=key):
                doc = sample_cases()
                doc["cases"][0][key] = invalid
                self.assertTrue(any(key in error for error in simulate_eval.validate(doc)))

    def test_loader_rejects_duplicate_keys_including_nested(self):
        for raw in ('{"schema_version": 1, "schema_version": 2}',
                    '{"cases": [{"id": "a", "id": "b"}]}'):
            with self.subTest(raw=raw), mock.patch.object(Path, "read_text", return_value=raw):
                with self.assertRaises(ValueError):
                    simulate_eval.load_cases("case.json")


class RunEval(unittest.TestCase):
    def test_misleading_auto_pass_never_becomes_verified_success(self):
        source_cases = simulate_eval.load_cases(simulate_eval.DEFAULT_CASES)
        source_cases = {item["id"]: item for item in source_cases["cases"]}
        examples = (
            ("research-brief-extraction-loss-01", "18명이며 3쪽에서 확인했다."),
            ("research-brief-search-negation-01", "지원하지 않는 경우가 없으므로 해당 환경은 지원한다."),
            ("document-authoring-ocr-table-01", "12건은 성공, 8건은 실패이며 2쪽에서 확인했다."),
        )
        for case_id, answer in examples:
            with self.subTest(case_id=case_id), tempfile.TemporaryDirectory() as tmp:
                doc = sample_cases()
                example = source_cases[case_id]
                index = next(i for i, case in enumerate(doc["cases"]) if case["skill"] == example["skill"])
                doc["cases"][index] = example
                path, out = Path(tmp) / "cases.json", Path(tmp) / "out"
                path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
                result = {"exit_code": 0, "output": answer, "stderr_tail": "", "seconds": 0,
                          "artifacts": [], "artifact_error": None}
                with mock.patch.object(run_eval, "run_case", return_value=result), redirect_stdout(io.StringIO()):
                    status = run_eval.main(["--cases", str(path), "--only", example["skill"],
                                            "--platform", "codex", "--max-calls", "1", "--out", str(out)])
                report = json.loads((out / "summary.json").read_text(encoding="utf-8"))["cases"][0]
                self.assertEqual(status, 0)  # command reports automatic checks, not quality
                self.assertTrue(report["auto_checks_passed"])
                self.assertIsNone(report["passed"])
                self.assertEqual(report["overall_status"], "NOT VERIFIED")
                self.assertEqual(report["runs"][0]["semantic_quality"], "NOT VERIFIED")

    def test_first_turn_can_pass_checks_but_followup_is_not_verified(self):
        doc = sample_cases()
        case = next(c for c in doc["cases"] if c["skill"] == "rhel-cve")
        case.update({"required": ["CVE"], "requires_followup": True, "forbid_unprovided_advisories": True})
        run = {"exit_code": 0, "output": "CVE 식별자를 알려주세요.", "stderr_tail": "",
               "seconds": 0, "artifacts": [], "artifact_error": None}
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / "cases.json", Path(tmp) / "out"
            source.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(run_eval, "run_case", return_value=run):
                status = run_eval.main(["--cases", str(source), "--only", "rhel-cve",
                                        "--platform", "codex", "--max-calls", "1", "--out", str(out)])
            result = json.loads((out / "summary.json").read_text(encoding="utf-8"))["cases"][0]
            self.assertEqual(status, 1)
            self.assertTrue(result["runs"][0]["passed_auto_checks"])
            self.assertEqual(result["runs"][0]["followup_status"], "NOT VERIFIED")
            self.assertIsNone(result["passed"])

    def test_unprovided_advisory_fails_execution_checks(self):
        doc = sample_cases()
        case = next(c for c in doc["cases"] if c["skill"] == "rhel-cve")
        case["forbid_unprovided_advisories"] = True
        run = {"exit_code": 0, "output": "결과 " + "CVE-" + "2024-" + "12345",
               "stderr_tail": "", "seconds": 0, "artifacts": [], "artifact_error": None}
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / "cases.json", Path(tmp) / "out"
            source.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(run_eval, "run_case", return_value=run):
                status = run_eval.main(["--cases", str(source), "--only", "rhel-cve",
                                        "--platform", "codex", "--max-calls", "1", "--out", str(out)])
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            observed = summary["cases"][0]["runs"][0]
            self.assertEqual(status, 1)
            self.assertFalse(observed["passed_auto_checks"])
            self.assertEqual(observed["checks"]["unexpected_advisory_count"], 1)

    def test_auto_cases_reject_expected_answers(self):
        clean = {"schema_version": 1, "cases": [{"id": "as-01", "request": "충분히 구체적인 자동 선택 요청입니다.", "artifact_policy": "forbidden"}]}
        self.assertEqual(run_eval.validate_auto_cases(clean), [])
        contaminated = {"schema_version": 1, "cases": [{"id": "as-01", "request": "충분히 구체적인 자동 선택 요청입니다.", "artifact_policy": "forbidden", "skill": "writing"}]}
        self.assertTrue(run_eval.validate_auto_cases(contaminated))
        missing_flag = {"schema_version": 1, "cases": [{"id": "as-02", "request": "충분히 구체적인 자동 선택 요청입니다."}]}
        self.assertTrue(run_eval.validate_auto_cases(missing_flag))
        invalid_policy = {"schema_version": 1, "cases": [{"id": "as-04", "request": "충분히 구체적인 자동 선택 요청입니다.", "artifact_policy": "yes"}]}
        self.assertTrue(run_eval.validate_auto_cases(invalid_policy))
        missing_extension = {"schema_version": 1, "cases": [{"id": "as-05", "request": "구체적인 파일 산출 요청 예시입니다.", "artifact_policy": "required"}]}
        self.assertTrue(run_eval.validate_auto_cases(missing_extension))
        artifact_as_answer = {"schema_version": 1, "cases": [{"id": "as-03", "request": "충분히 구체적인 자동 선택 요청입니다.", "artifact_policy": "forbidden", "expected_skill": "writing"}]}
        self.assertTrue(run_eval.validate_auto_cases(artifact_as_answer))

    def test_auto_cases_reject_non_string_policy(self):
        for invalid in ([], {}, None, 1):
            with self.subTest(policy=invalid):
                doc = {"schema_version": 1, "cases": [{"id": "as-01", "request": "A sufficiently detailed request", "artifact_policy": invalid}]}
                self.assertTrue(any("artifact_policy" in error for error in run_eval.validate_auto_cases(doc)))

    def test_timeout_preserves_partial_trace_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp) / "work"
            workdir.mkdir()
            (workdir / "partial.txt").write_text("partial", encoding="utf-8")
            dest = Path(tmp) / "artifacts"
            timeout = subprocess.TimeoutExpired("codex", 1, output=b'{"type":"item.completed","item":{"type":"agent_message","text":"partial answer"}}\n')
            with mock.patch.object(run_eval, "prepare_workdir", return_value=workdir), \
                 mock.patch.object(run_eval.process_control, "run", side_effect=timeout) as launch:
                result = run_eval.run_case(sample_cases()["cases"][0], "codex", 1, artifact_dir=dest)
            self.assertIsNone(result["exit_code"])
            self.assertEqual(result["process_timeout_seconds"], 1)
            self.assertGreaterEqual(result["preparation_seconds"], 0)
            self.assertGreaterEqual(result["process_seconds"], 0)
            self.assertIn("partial answer", result["raw_events"])
            self.assertEqual(result["output"], "partial answer")
            self.assertEqual(launch.call_args.kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual((dest / "partial.txt").read_text(encoding="utf-8"), "partial")
            self.assertEqual(result["artifacts"][0]["path"], "partial.txt")

    def test_capture_failure_is_recorded_without_hiding_original_error(self):
        process = subprocess.CompletedProcess([], 0, stdout="ok", stderr="")
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(run_eval.process_control, "run", return_value=process), \
             mock.patch.object(run_eval, "capture_artifacts", side_effect=OSError("capture unavailable")):
            result = run_eval.run_case(sample_cases()["cases"][0], "grok", 5,
                                       artifact_dir=Path(tmp) / "artifacts")
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("capture unavailable", result["artifact_error"])

    def test_real_process_timeout_stops_direct_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp) / "work"
            workdir.mkdir()
            command = [sys.executable, "-c", "import time; time.sleep(15)"]
            with mock.patch.object(run_eval, "prepare_workdir", return_value=workdir), \
                 mock.patch.object(run_eval, "platform_command", return_value=command):
                result = run_eval.run_case(sample_cases()["cases"][0], "codex", 0.5)
            self.assertIsNone(result["exit_code"])
            self.assertIn("timeout", result["stderr_tail"])
            self.assertEqual(result["process_timeout_seconds"], 0.5)
            self.assertLess(result["process_seconds"], 10)

    def test_no_content_checks_cannot_pass_and_trace_is_saved(self):
        doc = sample_cases()
        case = doc["cases"][0]
        case["required"] = []
        case["forbidden"] = []
        run = {"exit_code": 0, "output": "irrelevant", "stderr_tail": "", "seconds": 0,
               "raw_events": '{"type":"example"}\n', "usage_limit": False,
               "artifacts": [], "artifact_error": None}
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / "cases.json", Path(tmp) / "out"
            source.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(run_eval, "run_case", return_value=run):
                code = run_eval.main(["--cases", str(source), "--only", case["skill"],
                                      "--platform", "codex", "--max-calls", "1", "--out", str(out)])
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            recorded = summary["cases"][0]["runs"][0]
            self.assertEqual(code, 1)
            self.assertIsNone(recorded["passed_auto_checks"])
            self.assertEqual(recorded["overall_status"], "NOT VERIFIED")
            self.assertIsNone(summary["cases"][0]["passed"])
            self.assertIsNone(summary["cases"][0]["auto_check_pass_rate"])
            self.assertEqual(recorded["semantic_quality"], "NOT VERIFIED")
            self.assertEqual((out / recorded["trace_file"]).read_text(encoding="utf-8"), run["raw_events"])
            self.assertEqual(len(recorded["trace_sha256"]), 64)

    def test_auto_cases_reject_sensitive_values(self):
        request = "개인 정보 확인 요청 " + "test@" + "invalid.test에서 받은 내용을 검사해"
        unsafe = {"schema_version": 1, "cases": [{"id": "as-01", "request": request, "artifact_policy": "forbidden"}]}
        self.assertTrue(run_eval.validate_auto_cases(unsafe))
        safe_demo = {"schema_version": 1, "cases": [{"id": "as-demo", "request": "가상의 RHEL 9 결과 문서 작성 요청입니다.", "artifact_policy": "forbidden"}]}
        self.assertEqual(run_eval.validate_auto_cases(safe_demo), [])
    def test_auto_prompt_does_not_name_a_skill(self):
        prompt = run_eval.build_prompt({"request": "일반적인 자동 선택 요청입니다."}, auto_select=True)
        self.assertNotIn("'writing'", prompt)
        self.assertNotIn("writing", prompt)
        self.assertIn("일반적인 자동 선택 요청입니다", prompt)

    def test_targeted_prompts_identify_platform_skill_loader(self):
        case = {"skill": "rhel-cve", "request": "가상 요청입니다"}
        self.assertIn("Skill tool to load myway:rhel-cve", run_eval.build_prompt(case, platform="claude"))
        self.assertIn(".agents/skills/rhel-cve/SKILL.md", run_eval.build_prompt(case, platform="codex"))
        self.assertIn(".grok/skills/rhel-cve/SKILL.md", run_eval.build_prompt(case, platform="grok"))

    def test_claude_load_trace_requires_tool_success_and_matching_body(self):
        skill = "rhel-cve"
        body = (simulate_eval.SKILLS / skill / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[-1].strip()
        call = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "id": "tool-1", "input": {"skill": "myway:rhel-cve"}}]}}
        result = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tool-1", "content": "loaded"}]}}
        payload = {"type": "user", "message": {"content": [{"type": "text", "text": body}]}}
        finish = {"type": "result", "result": "response"}
        def observe(events):
            return run_eval.claude_jsonl_observation("\n".join(json.dumps(x, ensure_ascii=False) for x in events), skill)
        self.assertEqual(observe([call, result, payload, finish])["trace"]["status"], "loaded")
        self.assertEqual(observe([call, result, payload, finish])["final_text"], "response")
        self.assertFalse(observe([finish])["result_error"])
        self.assertTrue(observe([{"type": "result", "result": "provider error", "is_error": True}])["result_error"])
        self.assertEqual(observe([call, payload, finish])["trace"]["status"], "unverified")
        self.assertEqual(observe([call, result, finish])["trace"]["status"], "unverified")
        result["message"]["content"][0]["is_error"] = True
        self.assertEqual(observe([call, result, payload, finish])["trace"]["status"], "unverified")

    def test_claude_stream_error_is_not_success_with_zero_exit(self):
        message = "You've hit your limit - resets later"
        event = json.dumps({"type": "result", "result": message, "is_error": True})
        process = subprocess.CompletedProcess([], 0, stdout=event, stderr="")
        with mock.patch.object(run_eval.process_control, "run", return_value=process):
            result = run_eval.run_case(sample_cases()["cases"][0], "claude", 5)
        self.assertEqual(result["exit_code"], 1)
        self.assertTrue(result["usage_limit"])

    def test_auto_select_is_codex_only(self):
        with self.assertRaises(SystemExit):
            run_eval.main(["--auto-select", "--platform", "claude", "--dry-run", "--max-calls", "1"])

    def test_auto_select_rejects_unknown_case_id(self):
        self.assertEqual(run_eval.main(["--auto-select", "--platform", "codex", "--dry-run", "--only", "unknown-id"]), 1)

    def test_live_eval_requires_budget(self):
        with self.assertRaises(SystemExit):
            run_eval.main(["--platform", "claude"])

    def test_combined_budgets_stop_at_first_limit(self):
        doc = sample_cases()
        case = doc["cases"][0]
        run = {"exit_code": 0, "output": "결과", "stderr_tail": "", "seconds": 0}
        for limit in ("max_calls", "max_seconds"):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "cases.json"
                source.write_text(json.dumps(doc), encoding="utf-8")
                out = Path(tmp) / "out"
                clock = [0.0]
                def execute(*args, **kwargs):
                    if limit == "max_seconds":
                        clock[0] = 11.0
                    return dict(run)
                with mock.patch.object(run_eval.time, "monotonic", side_effect=lambda: clock[0]), \
                        mock.patch.object(run_eval, "run_case", side_effect=execute) as call:
                    args = ["--cases", str(source), "--out", str(out), "--only", case["skill"],
                            "--repeat", "3", "--max-calls", "1" if limit == "max_calls" else "3",
                            "--max-seconds", "10"]
                    self.assertEqual(run_eval.main(args), 1)
                    self.assertEqual(call.call_count, 1)
                    self.assertLessEqual(call.call_args.args[2], 10)
                summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
                self.assertEqual(summary["stop_reason"], limit)
                self.assertEqual(summary["budget"]["attempted_calls"], 1)
                self.assertEqual(summary["cases"][0]["not_run"], 2)

    def test_time_expiring_before_call_does_not_launch(self):
        doc = sample_cases()
        case = doc["cases"][0]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cases.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            out = Path(tmp) / "out"
            readings = iter([0.0, 0.0, 11.0])
            def now():
                return next(readings, 11.0)
            with mock.patch.object(run_eval.time, "monotonic", side_effect=now), \
                    mock.patch.object(run_eval, "run_case") as call:
                args = ["--cases", str(source), "--out", str(out), "--only", case["skill"],
                        "--max-calls", "2", "--max-seconds", "10"]
                self.assertEqual(run_eval.main(args), 1)
                call.assert_not_called()
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["stop_reason"], "max_seconds")
            self.assertEqual(summary["budget"]["attempted_calls"], 0)
            self.assertEqual(summary["cases"][0]["not_run"], 1)

    def test_manifest_preparation_consumes_start_budget(self):
        doc = sample_cases()
        case = doc["cases"][0]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cases.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            out = Path(tmp) / "out"
            clock = [0.0]
            real_manifest = run_eval.simulate_eval.manifest

            def slow_manifest(*args, **kwargs):
                result = real_manifest(*args, **kwargs)
                clock[0] = 11.0
                return result

            with mock.patch.object(run_eval.time, "monotonic", side_effect=lambda: clock[0]), \
                 mock.patch.object(run_eval.simulate_eval, "manifest", side_effect=slow_manifest), \
                 mock.patch.object(run_eval, "run_case") as call:
                args = ["--cases", str(source), "--out", str(out), "--only", case["skill"],
                        "--max-seconds", "10"]
                self.assertEqual(run_eval.main(args), 1)
                call.assert_not_called()
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["stop_reason"], "max_seconds")
            self.assertEqual(summary["budget"]["attempted_calls"], 0)

    def test_expired_deadline_after_workspace_preparation_does_not_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            with mock.patch.object(run_eval, "prepare_workdir", return_value=workspace), \
                    mock.patch.object(run_eval.time, "monotonic", return_value=11.0), \
                    mock.patch.object(run_eval.process_control, "run") as launch:
                result = run_eval.run_case(sample_cases()["cases"][0], "claude", 10, deadline=10.0)
            self.assertTrue(result["not_started"])
            launch.assert_not_called()
            self.assertFalse(workspace.exists())

    def test_subprocess_timeout_uses_remaining_deadline_after_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            process = subprocess.CompletedProcess([], 0, stdout="ok", stderr="")
            with mock.patch.object(run_eval, "prepare_workdir", return_value=workspace), \
                    mock.patch.object(run_eval.time, "monotonic", return_value=9.0), \
                    mock.patch.object(run_eval.process_control, "run", return_value=process) as launch:
                result = run_eval.run_case(sample_cases()["cases"][0], "codex", 15, deadline=10.0)
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(launch.call_args.kwargs["timeout"], 1.0)

    def test_workspace_deadline_is_counted_as_not_run(self):
        doc = sample_cases()
        case = doc["cases"][0]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cases.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            out = Path(tmp) / "out"
            with mock.patch.object(run_eval, "run_case", return_value={"not_started": True}) as call:
                args = ["--cases", str(source), "--out", str(out), "--only", case["skill"],
                        "--repeat", "2", "--max-calls", "2", "--max-seconds", "10"]
                self.assertEqual(run_eval.main(args), 1)
                self.assertEqual(call.call_count, 1)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["stop_reason"], "max_seconds")
            self.assertEqual(summary["budget"]["attempted_calls"], 0)
            self.assertEqual(summary["cases"][0]["not_run"], 2)

    def test_auto_select_dry_run_does_not_require_budget(self):
        self.assertEqual(run_eval.main(["--auto-select", "--platform", "codex", "--dry-run"]), 0)

    def test_auto_select_live_run_requires_budget(self):
        with self.assertRaises(SystemExit):
            run_eval.main(["--auto-select", "--platform", "codex"])

    def test_auto_select_stops_at_call_budget_and_records_unrun(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out"
            run = {"exit_code": 0, "output": "응답", "stderr_tail": "", "seconds": 0,
                   "usage_limit": False, "artifacts": [], "artifact_error": None}
            with mock.patch.object(run_eval, "run_case", return_value=run) as call:
                result = run_eval.main(["--auto-select", "--platform", "codex", "--out", str(output),
                                        "--max-calls", "1"])
            self.assertEqual(result, 1)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.kwargs.get("auto_select"), True)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["budget"]["attempted_calls"], 1)
            self.assertEqual(sum(item["not_run"] for item in summary["cases"]), 9)
            self.assertTrue(all(run["selection_status"] == "unverified"
                                for item in summary["cases"] for run in item["runs"]))
            self.assertEqual(summary["input_manifest"]["runtime"]["selection_trace"], "not_available")
            shutil.rmtree(tmp, ignore_errors=True)

    def test_inspect_artifacts_requires_targeted_workspace_platform(self):
        with self.assertRaises(SystemExit):
            run_eval.main(["--cases", str(simulate_eval.DEFAULT_CASES), "--inspect-artifacts",
                           "--platform", "claude", "--dry-run"])

    def test_office_inspector_checks_generated_xlsx_and_cache_scope(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "sample.xlsx"
            wb = Workbook()
            wb.active["A1"] = "=SUM(1,2)"
            wb.save(path)
            report = check_office.inspect_office_file(path)
        self.assertEqual(report["status"], "PASS")
        self.assertIn("Sheet!A1", report["formula_cells"])
        self.assertIn("Sheet!A1", report["missing_formula_caches"])
        self.assertEqual(report["calculation_status"], "NOT VERIFIED")

    def test_office_inspector_accepts_xlsx_after_recalculation(self):
        from openpyxl import Workbook, load_workbook
        import shutil
        renderer = shutil.which("soffice") or shutil.which("libreoffice")
        if not renderer:
            result = check_office.recalculate_xlsx(Path("missing.xlsx"), "=SUM(1,2)", 3)
            self.assertEqual(result["status"], "NOT VERIFIED")
            self.assertIn("unavailable", result["reason"])
            return
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "calculated.xlsx"
            wb = Workbook()
            wb.active["A1"] = "=SUM(1,2)"
            wb.save(path)
            profile = Path(tmp) / "profile"
            profile.mkdir()
            recalc_dir = Path(tmp) / "recalc"
            recalc_dir.mkdir()
            result = run_eval.subprocess.run(
                [renderer, "-env:UserInstallation=" + profile.resolve().as_uri(), "--headless",
                 "--convert-to", "xlsx", "--outdir", str(recalc_dir), str(path)],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            recalculated = recalc_dir / path.name
            self.assertTrue(recalculated.is_file())
            preserved = Path(tmp) / "preserved.xlsx"
            shutil.copy2(recalculated, preserved)
            report = check_office.inspect_office_file(preserved)
            wb.close()
            cached = load_workbook(preserved, data_only=True, read_only=True)
            try:
                self.assertEqual(cached.active["A1"].value, 3)
            finally:
                cached.close()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["calculation_status"], "PASS")
        self.assertEqual(report["formula_cells"], ["Sheet!A1"])
        self.assertEqual(report["missing_formula_caches"], [])

    def test_office_inspector_flags_external_relationships(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "external.xlsx"
            relationship = b'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.invalid/" TargetMode="External"/>
</Relationships>'''
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/externalLinks/externalLink1.xml", "<externalLink />")
                archive.writestr("xl/_rels/workbook.xml.rels", relationship)
            report = check_office.inspect_office_file(path)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["reason"], "external workbook link part detected")
        self.assertTrue(report["external_workbook_links"])
        self.assertNotIn("external_relationships", report)

    def test_office_inspector_detects_cached_formula_error(self):
        from openpyxl import Workbook
        import shutil
        renderer = shutil.which("soffice") or shutil.which("libreoffice")
        if not renderer:
            result = check_office.recalculate_xlsx(Path("missing.xlsx"), "=SUM(1,2)", 3)
            self.assertEqual(result["status"], "NOT VERIFIED")
            self.assertIn("unavailable", result["reason"])
            return
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "zero.xlsx"
            wb = Workbook()
            ws = wb.active
            ws["A1"], ws["A2"], ws["A3"] = "numerator", 1, 0
            ws["B1"], ws["B2"], ws["B3"] = "denominator", 1, "=A2/A3"
            wb.save(path)
            profile = Path(tmp) / "profile"
            profile.mkdir()
            recalc_dir = Path(tmp) / "recalc"
            recalc_dir.mkdir()
            result = run_eval.subprocess.run(
                [renderer, "-env:UserInstallation=" + profile.resolve().as_uri(), "--headless",
                 "--convert-to", "xlsx", "--outdir", str(recalc_dir), str(path)],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = check_office.inspect_office_file(recalc_dir / path.name)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["calculation_status"], "FAIL")
        self.assertEqual(report["cached_formula_errors"][0]["error"], "#DIV/0!")

    def test_office_inspector_reports_untitled_slide(self):
        from pptx import Presentation
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "untitled.pptx"
            prs = Presentation()
            prs.slides.add_slide(prs.slide_layouts[6])
            prs.save(path)
            report = check_office.inspect_office_file(path)
            prs = None
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["untitled_slides"], [1])

    def test_office_inspector_flags_macro_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "macro.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/vbaProject.bin", b"macro")
            report = check_office.inspect_office_file(path)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(report["macro_project"])

    def test_office_inspector_flags_external_workbook_link_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "linked.xlsx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/externalLinks/externalLink1.xml", "<externalLink />")
            report = check_office.inspect_office_file(path)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(report["external_workbook_links"])

    def test_office_inspector_rejects_path_traversal_archive(self):
        for entry_name in ("../outside.xml", r"..\\outside.xml"):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "traversal.docx"
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(entry_name, "<x />")
                report = check_office.inspect_office_file(path)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("unsafe archive", report["reason"])

    def test_main_records_office_inspection_for_targeted_artifacts(self):
        doc = sample_cases()
        case = doc["cases"][0]
        case["artifact_policy"] = "conditional"
        artifact = {"path": "sample.xlsx", "bytes": 10, "sha256": "a" * 64}
        office_report = {"file": "sample.xlsx", "status": "PASS", "calculation_status": "NOT VERIFIED",
                         "missing_formula_caches": ["Sheet!A1"]}
        run = {"exit_code": 0, "output": "결과", "stderr_tail": "", "seconds": 0,
               "usage_limit": False, "artifacts": [artifact], "artifact_error": None,
               "office_inspection": [office_report]}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cases.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            output = Path(tmp) / "out"
            with mock.patch.object(run_eval, "run_case", return_value=run) as call:
                code = run_eval.main(["--cases", str(source), "--only", case["skill"],
                                      "--platform", "codex", "--out", str(output),
                                      "--max-calls", "1", "--inspect-artifacts"])
            self.assertEqual(code, 0)
            self.assertTrue(call.call_args.kwargs["artifact_dir"] is not None)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            inspected_run = summary["cases"][0]["runs"][0]
            self.assertEqual(inspected_run["office_inspection"], [office_report])
            self.assertEqual(inspected_run["office_inspection_status"], "NOT VERIFIED")
            self.assertEqual(inspected_run["office_inspection_requested"], True)
            self.assertEqual(inspected_run["office_calculation_unverified"], [office_report])
            self.assertEqual(inspected_run["office_calculation_status"], "NOT VERIFIED")
            self.assertEqual(inspected_run["status"], "completed")
            self.assertTrue(inspected_run["passed_auto_checks"])
            self.assertEqual(inspected_run["overall_status"], "NOT VERIFIED")

    def test_inspected_office_artifact_structure_error_fails_run(self):
        doc = sample_cases()
        case = doc["cases"][0]
        case["artifact_policy"] = "conditional"
        artifact = {"path": "bad.xlsx", "bytes": 8, "sha256": "b" * 64}
        office_report = {"file": "bad.xlsx", "status": "FAIL", "reason": "macro project detected"}
        run = {"exit_code": 0, "output": "결과", "stderr_tail": "", "seconds": 0,
               "usage_limit": False, "artifacts": [artifact], "artifact_error": None,
               "office_inspection": [office_report]}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cases.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            output = Path(tmp) / "out"
            with mock.patch.object(run_eval, "run_case", return_value=run):
                code = run_eval.main(["--cases", str(source), "--only", case["skill"],
                                      "--platform", "codex", "--out", str(output),
                                      "--max-calls", "1", "--inspect-artifacts"])
            self.assertEqual(code, 1)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            failed_run = summary["cases"][0]["runs"][0]
            self.assertEqual(failed_run["status"], "execution_failed")
            self.assertEqual(failed_run["office_inspection_status"], "FAIL")

    def test_capture_artifacts_excludes_skill_copy_and_hashes_outputs(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workdir = root / "work"
            (workdir / ".agents/skills/hidden").mkdir(parents=True)
            (workdir / ".agents/skills/hidden/SKILL.md").write_text("skill", encoding="utf-8")
            (workdir / "report.txt").write_text("report", encoding="utf-8")
            artifact_dir = root / "out/artifacts/as-01"
            try:
                artifacts = run_eval.capture_artifacts(workdir, artifact_dir)
                self.assertEqual([item["path"] for item in artifacts], ["report.txt"])
                self.assertEqual((artifact_dir / "report.txt").read_text(encoding="utf-8"), "report")
                inspection = check_office.inspect_office_artifacts(workdir, artifacts)
                self.assertEqual(inspection, [])
                self.assertTrue(all(len(item["sha256"]) == 64 for item in artifacts))
                with self.assertRaises(OSError):
                    run_eval.capture_artifacts(workdir, artifact_dir)
            finally:
                shutil.rmtree(root, ignore_errors=True)

    def test_codex_jsonl_message_is_separated_from_load_trace(self):
        message = "확인할 CVE 식별자를 알려주세요."
        message_event = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": message}}, ensure_ascii=False)
        parsed = run_eval.codex_jsonl_observation(message_event)
        self.assertEqual(parsed["final_text"], message)
        self.assertEqual(parsed["trace"]["status"], "unverified")
        self.assertEqual(parsed["trace"]["event_types"], ["item.completed"])
        case_run = {"selection_trace": parsed["trace"]}
        self.assertEqual(case_run["selection_trace"]["status"], "unverified")
        # A real read event would still not establish correctness without private expected answers.
        body = (simulate_eval.SKILLS / "rhel-cve/SKILL.md").read_text(encoding="utf-8").strip()
        read_event = json.dumps({"type": "item.completed", "item": {"type": "tool_call",
                            "arguments": {"path": "C:/work/.agents/skills/rhel-cve/SKILL.md"},
                            "output": body}}, ensure_ascii=False)
        read_trace = run_eval.skill_load_any_evidence(read_event)
        self.assertEqual(read_trace["status"], "loaded")
        self.assertNotIn("selection_status", read_trace)

    def test_usage_reports_observed_values_without_filling_unknowns(self):
        codex = json.dumps({"type": "turn.completed", "usage": {"input_tokens": 20,
                           "cached_input_tokens": 4, "output_tokens": 0}})
        usage = run_eval.codex_jsonl_observation(codex)["usage"]
        self.assertEqual(usage["input_tokens"], 20)
        self.assertEqual(usage["output_tokens"], 0)
        self.assertEqual(usage["cache_read_tokens"], 4)
        self.assertIsNone(usage["cache_write_tokens"])
        self.assertIsNone(usage["cli_reported_cost_usd"])
        claude = json.dumps({"type": "result", "result": "ok", "usage": {"input_tokens": 5,
                            "output_tokens": 3, "cache_read_input_tokens": 2}, "total_cost_usd": 0.1,
                            "modelUsage": {"example-model": {}}})
        usage = run_eval.claude_jsonl_observation(claude, "rhel-cve")["usage"]
        self.assertEqual(usage["input_tokens"], 5)
        self.assertEqual(usage["cache_read_tokens"], 2)
        self.assertIsNone(usage["cache_write_tokens"])
        self.assertEqual(usage["cli_reported_cost_usd"], 0.1)
        self.assertEqual(usage["models"], ["example-model"])
        self.assertIsNone(run_eval.codex_jsonl_observation("")["usage"])

    def test_codex_tool_read_event_is_load_evidence_only_with_content(self):
        body = (simulate_eval.SKILLS / "rhel-cve/SKILL.md").read_text(encoding="utf-8").strip()
        event = json.dumps({"type": "item.completed", "item": {"type": "tool_call",
                           "arguments": {"path": "C:/work/.agents/skills/rhel-cve/SKILL.md"},
                           "output": body}}, ensure_ascii=False)
        result = run_eval.skill_load_any_evidence(event)
        self.assertEqual(result["status"], "loaded")
        self.assertIn("rhel-cve", result["skills"])
        command = {"type": "item.completed", "item": {"type": "command_execution",
                   "command": "cat .agents/skills/rhel-cve/SKILL.md", "aggregated_output": body,
                   "status": "completed", "exit_code": 0}}
        self.assertEqual(run_eval.skill_load_any_evidence(json.dumps(command))["status"], "loaded")
        command["item"]["exit_code"] = 1
        self.assertEqual(run_eval.skill_load_any_evidence(json.dumps(command))["status"], "unverified")
        command["item"]["exit_code"] = None
        self.assertEqual(run_eval.skill_load_any_evidence(json.dumps(command))["status"], "unverified")
        command["item"]["exit_code"] = 0
        command["item"]["aggregated_output"] = "name: rhel-cve"
        self.assertEqual(run_eval.skill_load_any_evidence(json.dumps(command))["status"], "unverified")

    def test_codex_failed_tool_or_self_report_is_not_load_evidence(self):
        failed = json.dumps({"type": "item.failed", "item": {"type": "tool_call", "arguments": {
                            "path": "rhel-cve/SKILL.md"}, "error": "permission denied"}}, ensure_ascii=False)
        claim = json.dumps({"type": "item.completed", "item": {"type": "agent_message",
                           "text": "rhel-cve/SKILL.md를 읽었습니다"}}, ensure_ascii=False)
        self.assertEqual(run_eval.skill_load_any_evidence(failed)["status"], "unverified")
        self.assertEqual(run_eval.skill_load_any_evidence(claim)["status"], "unverified")
        self.assertEqual(run_eval.skill_load_any_evidence("")["status"], "unverified")

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
            self.assertTrue(case["required"])
            self.assertEqual(case["forbidden"], [])
            checks = run_eval.evaluate_output("", case)
            self.assertFalse(checks["nonempty"])
            self.assertTrue(checks["missing_required"])
            self.assertEqual(checks["forbidden_found"], [])
            self.assertTrue(checks["within_limit"])
            self.assertTrue(run_eval.evaluate_output("irrelevant", case)["missing_required"])

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
                                                "--only", case["skill"], "--repeat", "3", "--max-calls", "3"]), 1)
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
                self.assertEqual(run_eval.main(["--cases", str(source), "--out", str(out), "--repeat", "2", "--max-calls", "2"]), 1)
                self.assertEqual(call.call_count, 1)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["schema_version"], 4)
            self.assertEqual(summary["stop_reason"], "claude_usage_limit")
            self.assertIsNone(summary["cases"][0]["auto_check_pass_rate"])
            self.assertIsNone(summary["cases"][0]["runs"][1]["passed_auto_checks"])
            self.assertEqual(summary["cases"][0]["runs"][0]["status"], "execution_failed")
            self.assertIsNone(summary["cases"][0]["runs"][0]["checks"])
            self.assertEqual(sum(c["not_run"] for c in summary["cases"]), len(doc["cases"]) * 2 - 1)
            self.assertTrue(all(c["attempted"] + c["not_run"] == c["repeats"] for c in summary["cases"]))

    def test_limit_in_diagnostics_detected_before_tail_truncation(self):
        msg = "You've hit your 5-hour limit · resets 3:50am (Asia/Seoul)"
        process = mock.Mock(returncode=1, stdout="warning\n" + msg, stderr="x" * 900)
        with mock.patch.object(run_eval.process_control, "run", return_value=process):
            result = run_eval.run_case(sample_cases()["cases"][0], "claude", 5)
        self.assertTrue(result["usage_limit"])
        self.assertEqual(result["usage_limit_message"], msg)
        process.returncode = 0
        process.stdout = msg
        with mock.patch.object(run_eval.process_control, "run", return_value=process):
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
                args = ["--cases", str(source), "--out", str(out), "--only", case["skill"], "--max-calls", "1"]
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
        codex = run_eval.platform_command("codex", "hi")
        self.assertEqual(codex[:2], ["codex", "exec"])
        self.assertEqual(codex[codex.index("--sandbox") + 1], "workspace-write")
        self.assertNotIn("danger-full-access", codex)
        self.assertEqual(run_eval.platform_command("grok", "hi")[:2], ["grok", "-p"])
        self.assertIn("--trust", run_eval.platform_command("grok", "hi"))
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

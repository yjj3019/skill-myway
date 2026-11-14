"""Ten offline fault scenarios across every installed skill; no model quality claims."""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import dialogue_eval
import run_eval
import simulate_eval


def cases():
    return {"schema_version": 2, "cases": [
        {"id": name + "-simulation", "skill": name,
         "request": "가상 입력의 결과를 대화로 설명하는 평가입니다.",
         "required": ["expected-result"], "forbidden": ["blocked-value"], "max_chars": 80}
        for name in simulate_eval.skill_names()]}


class WorkflowSimulation(unittest.TestCase):
    def simulate(self, *, output="expected-result", exit_code=0, timed_out=False,
                 policy=None, artifacts=None, budget=None):
        doc = cases()
        count = len(doc["cases"])
        if policy:
            for case in doc["cases"]:
                case.update(artifact_policy=policy, expected_extensions=[".html"])
        result = {"output": output, "exit_code": exit_code, "seconds": 0,
                  "stderr_tail": "", "timed_out": timed_out,
                  "artifacts": artifacts or [], "artifact_error": None, "office_inspection": []}
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / "cases.json", Path(tmp) / "out"
            source.write_text(json.dumps(doc), encoding="utf-8")
            args = ["--platform", "codex", "--cases", str(source), "--out", str(out),
                    "--max-calls", str(count if budget is None else budget)]
            if policy:
                args.append("--inspect-artifacts")
            with mock.patch.object(run_eval, "run_case", side_effect=lambda *a, **k: dict(result)) as call, \
                    redirect_stdout(io.StringIO()):
                status = run_eval.main(args)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(len(summary["cases"]), count)
        self.assertEqual(summary["budget"]["attempted_calls"], call.call_count)
        for entry in summary["cases"]:
            self.assertNotEqual(entry["overall_status"], "PASS")
            self.assertEqual(entry["attempted"] + entry["not_run"], entry["repeats"])
            self.assertEqual(entry["completed"] + entry["execution_failed"] + entry["timed_out"], entry["attempted"])
        return status, summary

    def assert_all_rejected(self, **kwargs):
        status, summary = self.simulate(**kwargs)
        self.assertEqual(status, 1)
        for entry in summary["cases"]:
            self.assertIs(entry["auto_checks_passed"], False)

    def test_01_normal_checks_never_claim_semantic_success(self):
        status, summary = self.simulate()
        self.assertEqual(status, 0)
        self.assertTrue(all(x["auto_checks_passed"] is True for x in summary["cases"]))

    def test_02_empty_output(self):
        self.assert_all_rejected(output="  ")

    def test_03_missing_content(self):
        self.assert_all_rejected(output="unrelated")

    def test_04_forbidden_content(self):
        self.assert_all_rejected(output="expected-result blocked-value")

    def test_05_length_overrun(self):
        self.assert_all_rejected(output="expected-result" + "x" * 81)

    def test_06_execution_failure_with_valid_looking_output(self):
        self.assert_all_rejected(exit_code=1)

    def test_07_timeout_preserves_separate_status(self):
        status, summary = self.simulate(exit_code=None, timed_out=True)
        self.assertEqual(status, 1)
        self.assertTrue(all(x["timed_out"] == 1 and x["execution_failed"] == 0 for x in summary["cases"]))

    def test_08_required_artifact_missing(self):
        self.assert_all_rejected(policy="required")

    def test_09_wrong_artifact_format(self):
        self.assert_all_rejected(policy="required", artifacts=[{"path": "sample.txt", "bytes": 1, "sha256": "a" * 64}])

    def test_10_budget_keeps_unrun_in_denominator(self):
        status, summary = self.simulate(budget=1)
        self.assertEqual(status, 1)
        self.assertEqual(summary["stop_reason"], "max_calls")
        self.assertEqual(sum(x["not_run"] for x in summary["cases"]), len(summary["cases"]) - 1)
        self.assertTrue(all(x["auto_checks_passed"] is None for x in summary["cases"][1:]))


class WorkflowRegressions(unittest.TestCase):
    def test_manifest_preserves_artifact_contract_and_changes_with_it(self):
        doc = cases()
        case = doc["cases"][0]
        case.update(artifact_policy="required", expected_extensions=[".html"])
        first = simulate_eval.manifest(doc)["cases"][0]
        self.assertEqual(first["artifact_policy"], "required")
        self.assertEqual(first["expected_extensions"], [".html"])
        case["expected_extensions"] = [".pdf"]
        self.assertNotEqual(first, simulate_eval.manifest(doc)["cases"][0])

    def test_prompt_follows_artifact_contract(self):
        case = cases()["cases"][0]
        for platform in ("claude", "codex", "grok"):
            for policy in ("required", "conditional", "forbidden"):
                with self.subTest(platform=platform, policy=policy):
                    case["artifact_policy"] = policy
                    prompt = run_eval.build_prompt(case, platform=platform)
                    self.assertEqual("파일을 만들거나" in prompt, policy == "forbidden")
                    self.assertEqual("현재 작업 디렉터리 안에만" in prompt, policy != "forbidden")

    def test_codex_failed_event_is_failure_even_with_zero_exit_and_banner(self):
        for kind in ("turn.failed", "error"):
            raw = "CLI banner\n" + json.dumps({"type": "item.completed", "item": {
                "type": "agent_message", "text": "expected-result"}}) + "\n" + json.dumps({"type": kind})
            result = subprocess.CompletedProcess([], 0, stdout=raw, stderr="")
            with tempfile.TemporaryDirectory() as tmp, \
                    mock.patch.object(run_eval, "prepare_workdir", return_value=Path(tmp)), \
                    mock.patch.object(run_eval.process_control, "run", return_value=result):
                record = run_eval.run_case(cases()["cases"][0], "codex", 5)
            self.assertEqual(record["exit_code"], 1)
            with mock.patch.object(dialogue_eval.process_control, "run", return_value=result):
                followup = dialogue_eval.execute([], ROOT, 5, "codex", "writing")
            self.assertEqual(followup["status"], "execution_failed")

    def test_preparation_failure_is_recorded_without_launch(self):
        with mock.patch.object(run_eval, "prepare_workdir", side_effect=OSError("copy failed")), \
                mock.patch.object(run_eval.process_control, "run") as launch:
            result = run_eval.run_case(cases()["cases"][0], "codex", 5)
        self.assertIsNone(result["exit_code"])
        self.assertIn("copy failed", result["stderr_tail"])
        launch.assert_not_called()

    def test_copy_failure_cleans_its_own_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            owned = Path(tmp) / "owned"
            owned.mkdir()
            with mock.patch.object(run_eval.tempfile, "mkdtemp", return_value=str(owned)), \
                    mock.patch.object(run_eval.shutil, "copytree", side_effect=OSError("copy failed")):
                with self.assertRaises(OSError):
                    run_eval.prepare_workdir("codex")
            self.assertFalse(owned.exists())

    def test_linked_artifact_is_failure_not_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir, out = Path(tmp) / "work", Path(tmp) / "out"
            workdir.mkdir()
            suspect = workdir / "suspect"
            suspect.mkdir()
            with mock.patch.object(simulate_eval, "_is_link", side_effect=lambda p: p == suspect):
                with self.assertRaisesRegex(OSError, "linked"):
                    run_eval.capture_artifacts(workdir, out)
            self.assertTrue(suspect.exists())
            self.assertFalse(out.exists())

    def test_unknown_skill_selection_never_silently_reduces_scope(self):
        with mock.patch.object(run_eval, "run_case") as launch, redirect_stdout(io.StringIO()):
            self.assertEqual(run_eval.main(["--dry-run", "--only", "writing", "unknown-skill"]), 1)
        launch.assert_not_called()

    def test_unobserved_artifact_contract_is_not_auto_pass(self):
        doc = cases()
        for case in doc["cases"]:
            case["artifact_policy"] = "forbidden"
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / "cases.json", Path(tmp) / "out"
            source.write_text(json.dumps(doc), encoding="utf-8")
            response = {"exit_code": 0, "output": "expected-result", "seconds": 0, "stderr_tail": ""}
            with mock.patch.object(run_eval, "run_case", return_value=response), redirect_stdout(io.StringIO()):
                status = run_eval.main(["--cases", str(source), "--out", str(out), "--max-calls", "100"])
            report = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(status, 1)
        self.assertTrue(all(x["auto_checks_passed"] is None for x in report["cases"]))

    def test_required_artifact_without_capture_rejected_before_launch(self):
        doc = cases()
        doc["cases"][0].update(artifact_policy="required", expected_extensions=[".html"])
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cases.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            with mock.patch.object(run_eval, "run_case") as launch, redirect_stdout(io.StringIO()):
                status = run_eval.main(["--cases", str(source), "--out", str(Path(tmp) / "out"), "--max-calls", "1"])
            self.assertEqual(status, 1)
            self.assertFalse((Path(tmp) / "out").exists())
            launch.assert_not_called()

    def test_forbidden_artifact_detected_in_targeted_mode(self):
        status, report = WorkflowSimulation.simulate(self, policy="forbidden", artifacts=[
            {"path": "unexpected.html", "bytes": 1, "sha256": "b" * 64}])
        self.assertEqual(status, 1)
        self.assertTrue(all(x["runs"][0]["artifact_expectation_met"] is False for x in report["cases"]))


if __name__ == "__main__":
    unittest.main()

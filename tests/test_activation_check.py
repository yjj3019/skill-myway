import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import activation_check  # noqa: E402
import simulate_eval  # noqa: E402


def skill_body(name):
    path = simulate_eval.SKILLS / name / "SKILL.md"
    return path.read_text(encoding="utf-8").split("---", 2)[-1].strip()


def claude_log(loaded, final="응답"):
    events = []
    for index, name in enumerate(loaded):
        call = f"toolu_{index}"
        events.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": call, "name": "Skill", "input": {"skill": f"myway:{name}"}}]}})
        events.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": call, "content": "Launching skill"}]}})
        events.append({"type": "user", "message": {"content": [
            {"type": "text", "text": skill_body(name)}]}})
    events.append({"type": "result", "is_error": False, "result": final})
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events)


def codex_log(loaded, final="응답"):
    events = [{"type": "turn.started"}]
    for name in loaded:
        events.append({"type": "item.completed", "item": {
            "type": "command_execution", "command": f"cat .agents/skills/{name}/SKILL.md",
            "exit_code": 0, "status": "completed",
            "aggregated_output": f"{name}/SKILL.md\n" + (simulate_eval.SKILLS / name / "SKILL.md").read_text(encoding="utf-8").strip()}})
    events.append({"type": "item.completed", "item": {"type": "agent_message", "text": final}})
    events.append({"type": "turn.completed", "usage": {}})
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events)


class ActivationCasesTest(unittest.TestCase):
    def test_public_cases_are_valid_and_cover_every_skill(self):
        cases = activation_check.load_cases(activation_check.DEFAULT_CASES)
        covered = {c["expected_skill"] for c in cases if c["expected_skill"]}
        self.assertEqual(covered, set(simulate_eval.skill_names()))
        self.assertGreaterEqual(sum(1 for c in cases if not c["expected_skill"]), 4)

    def test_request_naming_a_skill_is_rejected(self):
        bad = {"cases": [{"id": "x", "expected_skill": "writing", "request": "writing 스킬로 해줘",
                          "required": [["a"]]}]}
        path = ROOT / ".myway-tmp" / "bad-activation.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                activation_check.load_cases(path)
        finally:
            path.unlink(missing_ok=True)


class IsolatedCommandTest(unittest.TestCase):
    def test_adds_only_read_access_to_plugin_dir(self):
        command = activation_check.isolated_claude_command(["claude", "-p", "요청"])
        self.assertEqual(command[:2], ["claude", "--add-dir"])
        self.assertTrue(command[2].endswith("myway"))
        self.assertNotIn("--permission-mode", command)
        self.assertNotIn("--dangerously-skip-permissions", command)
        self.assertEqual(command[3:], ["-p", "요청"])


class LoadedSkillsTest(unittest.TestCase):
    def test_claude_detects_exact_loaded_skill_only(self):
        seen = activation_check.loaded_skills("claude", claude_log(["writing"]))
        self.assertEqual(seen["skills"], {"writing"})
        self.assertTrue(seen["observable"])

    def test_claude_without_skill_call_reports_none(self):
        seen = activation_check.loaded_skills("claude", claude_log([]))
        self.assertEqual(seen["skills"], set())

    def test_codex_detects_skill_read(self):
        seen = activation_check.loaded_skills("codex", codex_log(["code-review"]))
        self.assertEqual(seen["skills"], {"code-review"})

    def test_empty_log_is_not_observable(self):
        for platform in ("claude", "codex"):
            self.assertFalse(activation_check.loaded_skills(platform, "")["observable"])


class ClassifyTest(unittest.TestCase):
    def obs(self, skills, text="답", observable=True, error=False):
        return {"skills": set(skills), "final_text": text, "observable": observable, "provider_error": error}

    def test_positive_statuses(self):
        c = activation_check.classify_activation
        self.assertEqual(c("writing", self.obs(["writing"])), "ACTIVATED")
        self.assertEqual(c("writing", self.obs(["writing", "evidence-first"])), "ACTIVATED_WITH_EXTRA")
        self.assertEqual(c("writing", self.obs(["code-review"])), "WRONG_SKILL")
        self.assertEqual(c("writing", self.obs([])), "MISSED")

    def test_negative_statuses(self):
        c = activation_check.classify_activation
        self.assertEqual(c(None, self.obs([])), "CORRECT_NONE")
        self.assertEqual(c(None, self.obs(["writing"])), "FALSE_POSITIVE")

    def test_unobservable_or_errored_run_is_unverified_not_missed(self):
        c = activation_check.classify_activation
        self.assertEqual(c("writing", self.obs([], observable=False)), "UNVERIFIED")
        self.assertEqual(c("writing", self.obs([], error=True)), "UNVERIFIED")
        self.assertEqual(c(None, self.obs([], text="")), "UNVERIFIED")


class OutcomeTest(unittest.TestCase):
    def test_pair_classification(self):
        c = activation_check.classify_outcome
        self.assertEqual(c({"auto_pass": True}, {"auto_pass": False}), "DISCRIMINATING")
        self.assertEqual(c({"auto_pass": True}, {"auto_pass": True}), "NON_DISCRIMINATING")
        self.assertEqual(c({"auto_pass": False}, {"auto_pass": True}), "SKILL_HURTS")
        self.assertEqual(c({"auto_pass": False}, {"auto_pass": False}), "BOTH_FAIL")
        self.assertEqual(c({"auto_pass": None}, {"auto_pass": True}), "UNVERIFIED")

    def test_judge_run_ties_activation_and_auto_checks(self):
        case = {"id": "t", "expected_skill": "writing", "request": "요청",
                "required": [["다듬"]], "forbidden": [], "max_chars": 500}
        run = {"status": "completed", "stdout": claude_log(["writing"], "다듬은 결과"),
               "returncode": 0, "seconds": 1.0}
        row = activation_check.judge_run(case, "claude", run, "with")
        self.assertEqual(row["activation"], "ACTIVATED")
        self.assertTrue(row["auto_pass"])

    def test_timeout_is_unverified(self):
        case = {"id": "t", "expected_skill": "writing", "request": "요청", "required": [["a"]]}
        run = {"status": "timeout", "stdout": "", "returncode": None, "seconds": 5}
        row = activation_check.judge_run(case, "claude", run, "with")
        self.assertEqual((row["activation"], row["auto_pass"]), ("UNVERIFIED", None))

    def test_compare_rejects_mismatched_inputs_and_counts(self):
        a = {"rows": [{"id": "x", "expected_skill": "writing", "auto_pass": True, "activation": "ACTIVATED"}]}
        b = {"rows": [{"id": "x", "expected_skill": "writing", "auto_pass": False}]}
        result = activation_check.compare(a, b)
        self.assertEqual(result["counts"]["DISCRIMINATING"], 1)


if __name__ == "__main__":
    unittest.main()

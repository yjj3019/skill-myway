import contextlib
import io
import json
import os
import tempfile
import sys
import unittest
from unittest import mock
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


def tool_use(name, data, call="t1"):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": call, "name": name, "input": data}]}}


def raw_log(events, final="응답", denials=None):
    result = {"type": "result", "is_error": False, "result": final}
    if denials is not None:
        result["permission_denials"] = denials
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events + [result])


def codex_command(command, output="", exit_code=0):
    return {"type": "item.completed", "item": {"type": "command_execution", "command": command, "exit_code": exit_code,
                                               "status": "completed" if exit_code == 0 else "failed",
                                               "aggregated_output": output}}


def codex_raw(events, final="응답"):
    events = [{"type": "turn.started"}] + events + [
        {"type": "item.completed", "item": {"type": "agent_message", "text": final}}, {"type": "turn.completed", "usage": {}}]
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events)


REF = "C:/repo/plugins/myway/skills/writing/references/style.md"


class EntryDiagnosticsTest(unittest.TestCase):
    def claude(self, events, **kwargs):
        return activation_check.loaded_skills("claude", raw_log(events, **kwargs))

    def test_reference_read_without_skill_entry_is_seen_from_the_request_side(self):
        seen = self.claude([tool_use("Read", {"file_path": REF})])
        self.assertEqual(seen["skills"], set())
        self.assertEqual(seen["reference_reads"], {"writing"})

    def test_backslash_paths_and_read_commands_count(self):
        seen = self.claude([tool_use("Bash", {"command": r"cat C:\repo\plugins\myway\skills\writing\references\style.md"})])
        self.assertEqual(seen["reference_reads"], {"writing"})

    def test_listing_and_search_are_not_reads(self):
        seen = self.claude([tool_use("Glob", {"pattern": "plugins/myway/skills/writing/references/*"}, "a"),
                            tool_use("Bash", {"command": "ls plugins/myway/skills/writing/references"}, "b"),
                            tool_use("Grep", {"pattern": "x", "path": "plugins/myway/skills/writing/references"}, "c")])
        self.assertEqual(seen["reference_reads"], set())

    def test_tool_results_and_assistant_text_never_count(self):
        events = [{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "z",
                                                            "content": f"본문 {REF}"}]}},
                  {"type": "assistant", "message": {"content": [{"type": "text", "text": f"읽었다 {REF}"}]}}]
        seen = self.claude(events)
        self.assertEqual((seen["reference_reads"], seen["blocked"], seen["wrong_version"]), (set(), set(), set()))

    def test_successful_skill_call_with_other_body_is_wrong_version(self):
        heading = activation_check._local_heading("writing")
        events = [tool_use("Skill", {"skill": "myway:writing"}, "s1"),
                  {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "s1", "content": "ok"}]}},
                  {"type": "user", "message": {"content": [{"type": "text", "text": heading + "\n예전 본문"}]}}]
        seen = self.claude(events)
        self.assertEqual(seen["skills"], set())
        self.assertEqual(seen["wrong_version"], {"writing"})
        self.assertEqual(seen["call_without_body"], set())

    def test_successful_skill_call_without_any_body_text_is_not_called_a_version_problem(self):
        events = [tool_use("Skill", {"skill": "myway:writing"}, "s1"),
                  {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "s1", "content": "ok"}]}}]
        seen = self.claude(events)
        self.assertEqual((seen["wrong_version"], seen["call_without_body"]), (set(), {"writing"}))

    def test_denial_counts_only_when_the_denied_input_names_the_skill_directory(self):
        denied = [{"tool_name": "Read", "tool_input": {"file_path": REF}}]
        self.assertEqual(self.claude([], denials=denied)["blocked"], {"writing"})
        other = [{"tool_name": "Read", "tool_input": {"file_path": "C:/private/notes.md"}},
                 {"tool_name": "Write", "tool_input": {"file_path": "/srv/data/writing/a.md"}}]
        self.assertEqual(self.claude([], denials=other)["blocked"], set())

    def test_codex_reference_read_denial_and_wrong_version(self):
        read = codex_raw([codex_command("cat .agents/skills/writing/references/style.md", "내용")])
        self.assertEqual(activation_check.loaded_skills("codex", read)["reference_reads"], {"writing"})
        denied = codex_raw([codex_command("cat .agents/skills/writing/SKILL.md",
                                          "PermissionError: [Errno 13]", exit_code=1)])
        self.assertEqual(activation_check.loaded_skills("codex", denied)["blocked"], {"writing"})
        failed = codex_raw([codex_command("cat .agents/skills/writing/SKILL.md", "no such file", exit_code=1)])
        self.assertEqual(activation_check.loaded_skills("codex", failed)["blocked"], set())
        heading = activation_check._local_heading("writing")
        old = codex_raw([codex_command("cat .agents/skills/writing/SKILL.md", heading + "\n예전 본문")])
        self.assertEqual(activation_check.loaded_skills("codex", old)["wrong_version"], {"writing"})


class EntryPrecedenceTest(unittest.TestCase):
    def obs(self, skills=(), **extra):
        base = {"skills": set(skills), "final_text": "답", "observable": True, "provider_error": False}
        base.update({key: set(value) for key, value in extra.items()})
        return base

    def test_loaded_expected_skill_wins_over_every_clue(self):
        c = activation_check.classify_activation
        self.assertEqual(c("writing", self.obs(["writing"], blocked=["writing"], wrong_version=["writing"])), "ACTIVATED")

    def test_precedence_when_not_loaded(self):
        c = activation_check.classify_activation
        everything = dict(blocked=["writing"], wrong_version=["writing"], call_without_body=["writing"],
                          reference_reads=["writing"])
        self.assertEqual(c("writing", self.obs(**everything)), "BLOCKED")
        del everything["blocked"]
        self.assertEqual(c("writing", self.obs(**everything)), "WRONG_VERSION")
        del everything["wrong_version"]
        self.assertEqual(c("writing", self.obs(**everything)), "UNVERIFIED")
        del everything["call_without_body"]
        self.assertEqual(c("writing", self.obs(**everything)), "REFERENCE_ONLY")

    def test_clues_about_other_skills_do_not_change_the_verdict(self):
        c = activation_check.classify_activation
        self.assertEqual(c("writing", self.obs(blocked=["devlog"], reference_reads=["devlog"])), "MISSED")
        self.assertEqual(c("writing", self.obs(["code-review"], reference_reads=["writing"])), "REFERENCE_ONLY")
        self.assertEqual(c("writing", self.obs(["code-review"])), "WRONG_SKILL")

    def test_observation_without_new_keys_still_classifies(self):
        self.assertEqual(activation_check.classify_activation("writing", self.obs()), "MISSED")

    def test_negative_cases_ignore_entry_clues(self):
        c = activation_check.classify_activation
        self.assertEqual(c(None, self.obs(reference_reads=["writing"], blocked=["writing"])), "CORRECT_NONE")


class StrictModeTest(unittest.TestCase):
    def main(self, extra, stdout, strict):
        def fake_run(case, platform, timeout, isolated=False):
            return {"status": "completed", "stdout": stdout, "returncode": 0, "seconds": 0.1}
        env = {key: value for key, value in os.environ.items() if key != "MYWAY_SKILLS_DISABLE"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(activation_check, "run_one", side_effect=fake_run), \
                mock.patch.object(activation_check.run_eval, "cli_identity", return_value={"name": "claude", "available": False}), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            out = Path(tmp) / "out"
            argv = ["--platform", "claude", "--out", str(out)] + extra + (["--strict"] if strict else [])
            code = activation_check.main(argv)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        return code, summary, err.getvalue()

    def test_strict_passes_only_when_every_row_is_ok(self):
        code, summary, _ = self.main(["--only", "act-writing", "--max-calls", "1"], claude_log(["writing"]), True)
        self.assertEqual(code, 0)
        self.assertEqual(summary["schema_version"], 2)

    def test_strict_fails_on_missed_but_default_keeps_returning_zero(self):
        code, _, err = self.main(["--only", "act-writing", "--max-calls", "1"], claude_log([]), True)
        self.assertEqual(code, 1)
        self.assertIn("act-writing: MISSED", err)
        code, summary, _ = self.main(["--only", "act-writing", "--max-calls", "1"], claude_log([]), False)
        self.assertEqual((code, summary["rows"][0]["activation"]), (0, "MISSED"))

    def test_strict_counts_unrun_cases_as_violations(self):
        argv = ["--only", "act-writing", "neg-trivia", "--max-calls", "1"]
        code, summary, err = self.main(argv, claude_log(["writing"]), True)
        self.assertEqual((code, summary["not_run"]), (1, 1))
        self.assertIn("미실행 1건", err)
        self.assertEqual(self.main(argv, claude_log(["writing"]), False)[0], 0)

    def test_strict_fails_on_new_entry_statuses_and_records_notes(self):
        log = raw_log([tool_use("Read", {"file_path": REF})])
        code, summary, _ = self.main(["--only", "act-writing", "--max-calls", "1"], log, True)
        self.assertEqual(code, 1)
        self.assertEqual(summary["rows"][0]["activation"], "REFERENCE_ONLY")
        self.assertEqual(summary["rows"][0]["entry_notes"], {"reference_reads": ["writing"]})

    def test_strict_is_rejected_for_without_arm_and_compare(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for argv in (["--platform", "claude", "--arm", "without", "--out", "x", "--max-calls", "1", "--strict"],
                         ["--compare", "a.json", "b.json", "--strict"]):
                with self.assertRaises(SystemExit) as caught:
                    activation_check.main(argv)
                self.assertEqual(caught.exception.code, 2)

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

SESSION = "12345678-1234-4234-8234-123456789abc"
OTHER = "87654321-1234-4234-8234-123456789abc"


def stream(session, text, load=False):
    events = [{"type": "thread.started", "thread_id": session}]
    if load:
        body = (ROOT / "plugins/myway/skills/rhel-cve/SKILL.md").read_text(encoding="utf-8")
        events.append({"type": "item.completed", "item": {"type": "command_execution", "status": "completed",
                       "exit_code": 0, "command": ".agents/skills/rhel-cve/SKILL.md", "aggregated_output": body}})
    events += [
              {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
              {"type": "turn.completed"}]
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events)


def claude_stream(session, text, load=False):
    events = [{"type": "system", "subtype": "init", "session_id": session}]
    if load:
        body = (ROOT / "plugins/myway/skills/rhel-cve/SKILL.md").read_text(encoding="utf-8").split("---", 2)[-1].strip()
        events.extend([
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "id": "x", "input": {"skill": "myway:rhel-cve"}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "x", "content": "loaded"}, {"type": "text", "text": body}]}}
        ])
    events.append({"type": "result", "result": text})
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events)


class DialogueEvaluation(unittest.TestCase):
    def run_case(self, mock_results, max_calls=2, platform="codex"):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            with mock.patch.object(dialogue_eval.process_control, "run", side_effect=mock_results) as call, \
                 redirect_stdout(io.StringIO()):
                status = dialogue_eval.main(["--platform", platform, "--case", "rhel-cve-audit-missing",
                                             "--out", str(out), "--max-calls", str(max_calls),
                                             "--max-seconds", "60", "--timeout", "20"])
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            for turn in summary["turns"]:
                if turn["status"] == "completed":
                    self.assertTrue((out / turn["output_file"]).exists())
                    self.assertTrue((out / turn["trace_file"]).exists())
            return status, summary, call

    def test_same_session_both_turns_and_budget(self):
        results = [subprocess.CompletedProcess([], 0, stdout=stream(SESSION, "CVE 식별자를 알려주세요.", load=True), stderr=""),
                   subprocess.CompletedProcess([], 0, stdout=stream(SESSION, "CVE-2099-00001은 판단할 수 없습니다."), stderr="")]
        status, summary, call = self.run_case(results)
        self.assertEqual(status, 0)
        self.assertEqual(summary["attempted_calls"], 2)
        self.assertEqual(summary["followup_status"], "AUTO PASS")
        self.assertEqual(summary["semantic_quality"], "NOT VERIFIED")
        self.assertEqual(summary["turns"][1]["session_status"], "matched")
        command = call.call_args_list[1].args[0]
        self.assertIn("resume", command)
        self.assertIn(SESSION, command)
        self.assertEqual(call.call_args_list[0].kwargs["cwd"], call.call_args_list[1].kwargs["cwd"])

    def test_unobserved_skill_load_does_not_pass(self):
        results = [subprocess.CompletedProcess([], 0, stdout=stream(SESSION, "CVE 식별자를 알려주세요."), stderr=""),
                   subprocess.CompletedProcess([], 0, stdout=stream(SESSION, "CVE-2099-00001은 판단할 수 없습니다."), stderr="")]
        status, summary, call = self.run_case(results)
        self.assertEqual(status, 1)
        self.assertEqual(summary["followup_status"], "NOT VERIFIED")
        self.assertEqual(call.call_count, 1)

    def test_claude_same_session_and_skill_trace(self):
        results = [subprocess.CompletedProcess([], 0, stdout=claude_stream(SESSION, "CVE 식별자를 알려주세요.", load=True), stderr=""),
                   subprocess.CompletedProcess([], 0, stdout=claude_stream(SESSION, "CVE-2099-00001은 판단할 수 없습니다."), stderr="")]
        status, summary, call = self.run_case(results, platform="claude")
        self.assertEqual(status, 0)
        self.assertEqual(summary["followup_status"], "AUTO PASS")
        self.assertIn("--resume", call.call_args_list[1].args[0])

    def test_one_call_budget_preserves_unrun_followup(self):
        result = subprocess.CompletedProcess([], 0, stdout=stream(SESSION, "CVE 식별자를 알려주세요.", load=True), stderr="")
        status, summary, call = self.run_case([result], max_calls=1)
        self.assertEqual(status, 1)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(summary["followup_status"], "NOT VERIFIED")
        self.assertEqual(summary["turns"][1]["status"], "not_run")

    def test_mismatched_session_cannot_pass(self):
        results = [subprocess.CompletedProcess([], 0, stdout=stream(SESSION, "CVE 식별자를 알려주세요.", load=True), stderr=""),
                   subprocess.CompletedProcess([], 0, stdout=stream(OTHER, "CVE-2099-00001은 판단할 수 없습니다."), stderr="")]
        status, summary, _ = self.run_case(results)
        self.assertEqual(status, 1)
        self.assertEqual(summary["followup_status"], "NOT VERIFIED")

    def test_followup_timeout_is_not_success(self):
        first = subprocess.CompletedProcess([], 0, stdout=stream(SESSION, "CVE 식별자를 알려주세요.", load=True), stderr="")
        status, summary, _ = self.run_case([first, subprocess.TimeoutExpired("codex", 1)])
        self.assertEqual(status, 1)
        self.assertEqual(summary["turns"][1]["status"], "timeout")
        self.assertEqual(summary["followup_status"], "NOT VERIFIED")

    def test_local_artifact_blocks_followup(self):
        def invoke(command, **kwargs):
            (Path(kwargs["cwd"]) / "unrequested.txt").write_text("unexpected", encoding="utf-8")
            return subprocess.CompletedProcess([], 0, stdout=stream(SESSION, "CVE 식별자를 알려주세요."), stderr="")
        status, summary, call = self.run_case(invoke)
        self.assertEqual(status, 1)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(summary["followup_status"], "AUTO FAIL")

    def test_modifying_installed_skill_blocks_followup(self):
        def invoke(command, **kwargs):
            target = Path(kwargs["cwd"]) / ".agents/skills/rhel-cve/SKILL.md"
            target.write_text("changed", encoding="utf-8")
            return subprocess.CompletedProcess([], 0, stdout=stream(SESSION, "CVE 식별자를 알려주세요."), stderr="")
        status, summary, call = self.run_case(invoke)
        self.assertEqual(status, 1)
        self.assertEqual(call.call_count, 1)
        self.assertTrue(summary["turns"][0]["skill_tree_changed"])
        self.assertEqual(summary["followup_status"], "AUTO FAIL")


if __name__ == "__main__":
    unittest.main()

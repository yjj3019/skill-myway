import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins/myway/skills/evidence-first/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("build_evidence_ledger")
checker = load("check_evidence_answer")


def call(call_id, name, **data):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": call_id, "name": name, "input": data}]}})


def result(call_id, text, error=False):
    return json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": text, "is_error": error}]}})


LOG = [
    call("t1", "Bash", command="python -m unittest"),
    result("t1", "Ran 12 tests in 0.1s\nOK"),
    call("t2", "Bash", command="python -m unittest tests.empty"),
    result("t2", "Exit code 5\nNO TESTS RAN", error=True),
    call("t3", "Read", file_path="/srv/data/a.md"),
    result("t3", [{"type": "text", "text": "내용"}]),
]
FLAGS = {"tests_ran": "Ran [1-9][0-9]* tests?", "none_ran": "NO TESTS RAN"}


def ledger_of(lines=LOG, flags=FLAGS):
    return builder.build_ledger(lines, builder.parse_flags([f"{k}={v}" for k, v in flags.items()]))


def by_id(ledger):
    return checker.validate_ledger(ledger)


FIXTURE = {"claims": {
    "tests": {"expected_status": "VERIFIED", "required_conditions": [
        {"tool": "Bash", "command_regex": "unittest", "exit_code": 0, "output_flags": ["tests_ran"]}]},
    "empty": {"expected_status": "CONTRADICTED", "required_conditions": [
        {"tool": "Bash", "exit_code": 5, "output_flags": ["none_ran"]}]},
    "docs": {"expected_status": "NOT_VERIFIED", "required_conditions": []},
}}


def answer(tests=("VERIFIED", ["call:1"]), empty=("CONTRADICTED", ["call:2"]), docs=("NOT_VERIFIED", [])):
    return {"EVIDENCE_STATUS": "CONTRADICTED",
            "CLAIMS": [{"id": cid, "status": s, "evidence_ids": refs}
                       for cid, (s, refs) in (("tests", tests), ("empty", empty), ("docs", docs))],
            "REQUIRED_EVIDENCE": ["문서 변경 diff"]}


def codes(problems):
    return sorted({p.split(":", 1)[0] for p in problems})


class LedgerBuild(unittest.TestCase):
    def test_entries_follow_call_order_and_record_exit_codes_and_flags(self):
        ledger = ledger_of()
        self.assertEqual([e["id"] for e in ledger["entries"]], ["call:1", "call:2", "call:3"])
        first, second, third = ledger["entries"]
        self.assertEqual((first["tool"], first["exit_code"], first["flags"]), ("Bash", 0, {"tests_ran": True, "none_ran": False}))
        self.assertEqual((second["exit_code"], second["is_error"], second["flags"]["none_ran"]), (5, True, True))
        self.assertEqual((third["tool"], third["exit_code"], third["command"]), ("Read", None, "/srv/data/a.md"))

    def test_raw_output_is_never_stored(self):
        text = json.dumps(ledger_of(), ensure_ascii=False)
        for secret in ("Ran 12 tests", "NO TESTS RAN", "내용"):
            self.assertNotIn(secret, text)
        self.assertEqual(len(ledger_of()["entries"][0]["output_sha256"]), 64)

    def test_call_without_result_is_counted_not_listed(self):
        ledger = builder.build_ledger(LOG + [call("t9", "Bash", command="sleep 1")])
        self.assertEqual((len(ledger["entries"]), ledger["unmatched"]), (3, 1))

    def test_unusable_logs_are_errors(self):
        with self.assertRaises(builder.LedgerError):
            builder.build_ledger(["not json", "{}"])
        with self.assertRaises(builder.LedgerError):
            builder.build_ledger([call("t1", "Bash", command="a"), call("t1", "Bash", command="b")])
        with self.assertRaises(builder.LedgerError):
            builder.parse_flags(["bad"])
        with self.assertRaises(builder.LedgerError):
            builder.parse_flags(["x=("])
        with self.assertRaises(builder.LedgerError):
            builder.parse_flags(["x=a", "x=b"])


def codex_event(kind, item_id, command, output="", code=None, status="in_progress"):
    return json.dumps({"type": kind, "item": {"id": item_id, "type": "command_execution", "command": command,
                                              "aggregated_output": output, "exit_code": code, "status": status}})


def grok_call(call_id, command):
    return json.dumps({"type": "tool_call", "toolCallId": call_id, "toolName": "run_terminal_command",
                       "status": "pending", "rawInput": {"command": command}})


def grok_update(call_id, raw):
    return json.dumps({"type": "tool_call_update", "toolCallId": call_id, "status": None, "rawOutput": raw})


class HostFormats(unittest.TestCase):
    """Codex·Grok 이벤트 모양은 실제 로그에서 옮긴 구조이며, 값은 가상이다."""

    def test_codex_completed_items_become_entries_with_failures_kept_as_errors(self):
        log = [codex_event("item.started", "i0", "echo ledger-probe"),
               codex_event("item.completed", "i0", "echo ledger-probe", "Failed to create process", -1, "failed"),
               codex_event("item.started", "i1", "echo ok"),
               codex_event("item.completed", "i1", "echo ok", "ledger-probe", 0, "completed"),
               codex_event("item.started", "i2", "sleep 9")]
        ledger = builder.build_ledger(log, builder.parse_flags(["p=ledger-probe"]))
        self.assertEqual(ledger["source"], "codex-exec-jsonl")
        first, second = ledger["entries"]
        self.assertEqual((first["id"], first["exit_code"], first["is_error"], first["flags"]["p"]), ("call:1", -1, True, False))
        self.assertEqual((second["exit_code"], second["is_error"], second["flags"]["p"]), (0, False, True))
        self.assertEqual(ledger["unmatched"], 1)

    def test_grok_calls_pair_with_the_last_update_that_has_raw_output(self):
        log = [grok_call("g1", "echo ledger-probe"),
               json.dumps({"type": "tool_call_update", "toolCallId": "g1", "status": None, "rawOutput": None}),
               grok_update("g1", {"type": "Bash", "output_for_prompt": "ledger-probe", "exit_code": 0, "command": "echo ledger-probe"}),
               grok_call("g2", "false"),
               grok_update("g2", {"type": "Bash", "output_for_prompt": "", "exit_code": 1}),
               grok_call("g3", "never finishes")]
        ledger = builder.build_ledger(log, builder.parse_flags(["p=ledger-probe"]))
        self.assertEqual(ledger["source"], "grok-streaming-json")
        first, second = ledger["entries"]
        self.assertEqual((first["tool"], first["command"], first["exit_code"], first["flags"]["p"]),
                         ("run_terminal_command", "echo ledger-probe", 0, True))
        self.assertEqual((second["exit_code"], second["is_error"]), (1, True))
        self.assertEqual(ledger["unmatched"], 1)

    def test_mixed_hosts_and_duplicate_ids_are_errors(self):
        with self.assertRaises(builder.LedgerError):
            builder.build_ledger(LOG + [codex_event("item.completed", "i0", "x", "", 0, "completed")])
        with self.assertRaises(builder.LedgerError):
            builder.build_ledger([codex_event("item.completed", "i0", "x", "", 0, "completed")] * 2)
        with self.assertRaises(builder.LedgerError):
            builder.build_ledger([grok_call("g1", "a"), grok_call("g1", "b")])

    def test_checker_accepts_a_codex_ledger_the_same_way(self):
        log = [codex_event("item.completed", "i0", "python -m unittest", "Ran 3 tests\nOK", 0, "completed")]
        ledger = checker.validate_ledger(builder.build_ledger(log, builder.parse_flags(["tests_ran=Ran [1-9][0-9]* tests?"])))
        fixture = {"claims": {"tests": {"expected_status": "VERIFIED", "required_conditions": [
            {"tool": "command_execution", "command_regex": "unittest", "exit_code": 0, "output_flags": ["tests_ran"]}]}}}
        ans = {"EVIDENCE_STATUS": "VERIFIED", "REQUIRED_EVIDENCE": [],
               "CLAIMS": [{"id": "tests", "status": "VERIFIED", "evidence_ids": ["call:1"]}]}
        self.assertEqual(checker.check(ans, fixture, ledger), [])


class LedgerCheck(unittest.TestCase):
    def setUp(self):
        self.ledger = by_id(ledger_of())

    def run_check(self, ans, fixture=FIXTURE, ledger=None):
        return codes(checker.check(ans, fixture, ledger or self.ledger))

    def test_answer_backed_by_the_ledger_passes(self):
        self.assertEqual(self.run_check(answer()), [])

    def test_forged_or_missing_ledger_id_is_rejected(self):
        self.assertIn("UNKNOWN_EVIDENCE", self.run_check(answer(tests=("VERIFIED", ["call:1", "call:99"]))))
        self.assertIn("UNKNOWN_EVIDENCE", self.run_check(answer(tests=("VERIFIED", ["E1"]))))

    def test_real_call_that_does_not_meet_the_condition_does_not_support_the_verdict(self):
        self.assertIn("UNSUPPORTED_VERDICT", self.run_check(answer(tests=("VERIFIED", ["call:3"]))))   # 읽기 도구
        self.assertIn("UNSUPPORTED_VERDICT", self.run_check(answer(tests=("VERIFIED", ["call:2"]))))   # 종료 코드 5
        self.assertIn("UNSUPPORTED_VERDICT", self.run_check(answer(tests=("VERIFIED", []))))

    def test_trivial_command_does_not_satisfy_a_tight_condition(self):
        log = [call("t1", "Bash", command="echo Ran 12 tests"), result("t1", "Ran 12 tests")]
        ledger = by_id(ledger_of(log))
        only = {"claims": {"tests": FIXTURE["claims"]["tests"]}}
        ans = {"EVIDENCE_STATUS": "VERIFIED",
               "CLAIMS": [{"id": "tests", "status": "VERIFIED", "evidence_ids": ["call:1"]}],
               "REQUIRED_EVIDENCE": []}
        # 명령 정규식이 'unittest'를 요구하므로 echo는 통과하지 못한다.
        self.assertIn("UNSUPPORTED_VERDICT", codes(checker.check(ans, only, ledger)))

    def test_without_a_ledger_the_old_mode_is_unchanged(self):
        old = {"claims": {"c": {"expected_status": "NOT_VERIFIED", "allowed_evidence": [], "required_evidence": []}}}
        ans = {"EVIDENCE_STATUS": "NOT_VERIFIED", "REQUIRED_EVIDENCE": ["x"],
               "CLAIMS": [{"id": "c", "status": "NOT_VERIFIED", "evidence_ids": []}]}
        self.assertEqual(checker.check(ans, old), [])


class LedgerSchemas(unittest.TestCase):
    def test_ledger_fixture_rejections(self):
        def rejects(rule):
            with self.assertRaises(checker.FixtureError):
                checker.validate_fixture({"claims": {"c": rule}}, ledger_mode=True)
        rejects({"expected_status": "VERIFIED", "required_conditions": []})
        rejects({"expected_status": "NOT_VERIFIED", "allowed_evidence": [], "required_evidence": []})
        rejects({"expected_status": "VERIFIED", "required_conditions": [{}]})
        rejects({"expected_status": "VERIFIED", "required_conditions": [{"bogus": 1}]})
        rejects({"expected_status": "VERIFIED", "required_conditions": [{"command_regex": "("}]})
        rejects({"expected_status": "VERIFIED", "required_conditions": [{"exit_code": True}]})
        rejects({"expected_status": "VERIFIED", "required_conditions": [{"output_flags": []}]})
        checker.validate_fixture(FIXTURE, ledger_mode=True)

    def test_ledger_rejections(self):
        good = ledger_of()
        for bad in ([], {"schema_version": 2, "entries": []}, {"schema_version": 1, "entries": {}}):
            with self.assertRaises(checker.FixtureError):
                checker.validate_ledger(bad)
        dup = copy.deepcopy(good)
        dup["entries"].append(dict(dup["entries"][0]))
        with self.assertRaises(checker.FixtureError):
            checker.validate_ledger(dup)
        flagged = copy.deepcopy(good)
        flagged["entries"][0]["flags"] = {"x": "yes"}
        with self.assertRaises(checker.FixtureError):
            checker.validate_ledger(flagged)


class CommandLine(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, "-B", *map(str, args)], capture_output=True, text=True,
                              encoding="utf-8", env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})

    def test_build_then_check_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "run.jsonl").write_text("\n".join(LOG) + "\n", encoding="utf-8")
            built = self.run_script(SCRIPTS / "build_evidence_ledger.py", tmp / "run.jsonl", "--out", tmp / "l.json",
                                    "--flag", "tests_ran=Ran [1-9][0-9]* tests?", "--flag", "none_ran=NO TESTS RAN")
            self.assertEqual(built.returncode, 0, built.stderr)
            (tmp / "a.json").write_text(json.dumps(answer()), encoding="utf-8")
            (tmp / "f.json").write_text(json.dumps(FIXTURE), encoding="utf-8")
            ok = self.run_script(SCRIPTS / "check_evidence_answer.py", tmp / "a.json", tmp / "f.json", "--ledger", tmp / "l.json")
            self.assertEqual((ok.returncode, ok.stdout.strip().splitlines()[-1]), (0, "EVIDENCE-ANSWER: PASS (0)"))
            (tmp / "a.json").write_text(json.dumps(answer(tests=("VERIFIED", ["call:3"]))), encoding="utf-8")
            bad = self.run_script(SCRIPTS / "check_evidence_answer.py", tmp / "a.json", tmp / "f.json", "--ledger", tmp / "l.json")
            self.assertEqual(bad.returncode, 1)
            self.assertIn("UNSUPPORTED_VERDICT", bad.stdout)

    def test_builder_errors_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "run.jsonl").write_text("garbage\n", encoding="utf-8")
            self.assertEqual(self.run_script(SCRIPTS / "build_evidence_ledger.py", tmp / "run.jsonl", "--out", tmp / "l.json").returncode, 2)
            self.assertEqual(self.run_script(SCRIPTS / "build_evidence_ledger.py", tmp / "none.jsonl", "--out", tmp / "l.json").returncode, 2)

    def test_checker_rejects_a_broken_ledger_as_checker_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.json").write_text(json.dumps(answer()), encoding="utf-8")
            (tmp / "f.json").write_text(json.dumps(FIXTURE), encoding="utf-8")
            (tmp / "l.json").write_text("[]", encoding="utf-8")
            result = self.run_script(SCRIPTS / "check_evidence_answer.py", tmp / "a.json", tmp / "f.json", "--ledger", tmp / "l.json")
            self.assertEqual(result.returncode, 2)
            self.assertIn("CHECKER_ERROR", result.stderr)


if __name__ == "__main__":
    unittest.main()

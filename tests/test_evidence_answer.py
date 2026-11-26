import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "plugins/myway/skills/evidence-first/scripts/check_evidence_answer.py"
spec = importlib.util.spec_from_file_location("check_evidence_answer", CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

FIXTURE = {"claims": {
    "tests": {"expected_status": "NOT_VERIFIED", "allowed_evidence": [], "required_evidence": []},
    "build": {"expected_status": "VERIFIED", "allowed_evidence": ["log-1", "log-2"], "required_evidence": ["log-1"]},
    "gate": {"expected_status": "CONTRADICTED", "allowed_evidence": ["run-0"], "required_evidence": ["run-0"]},
    "docs": {"expected_status": "BLOCKED", "allowed_evidence": [], "required_evidence": []},
}}

GOOD = {
    "EVIDENCE_STATUS": "CONTRADICTED",
    "CLAIMS": [
        {"id": "tests", "status": "NOT_VERIFIED", "evidence_ids": []},
        {"id": "build", "status": "VERIFIED", "evidence_ids": ["log-1"]},
        {"id": "gate", "status": "CONTRADICTED", "evidence_ids": ["run-0"]},
        {"id": "docs", "status": "BLOCKED", "evidence_ids": []},
    ],
    "REQUIRED_EVIDENCE": ["문서 변경 diff"],
}


def one_claim_fixture(status, allowed=(), required=()):
    return {"claims": {"c": {"expected_status": status, "allowed_evidence": list(allowed),
                             "required_evidence": list(required)}}}


def answer(status, refs=(), overall=None, required=("다음 증거",)):
    return {"EVIDENCE_STATUS": overall or status,
            "CLAIMS": [{"id": "c", "status": status, "evidence_ids": list(refs)}],
            "REQUIRED_EVIDENCE": list(required)}


def codes(problems):
    return sorted({p.split(":", 1)[0] for p in problems})


class StatusCases(unittest.TestCase):
    def test_every_status_passes_when_evidence_matches(self):
        self.assertEqual(checker.check(GOOD, FIXTURE), [])
        cases = [("NOT_VERIFIED", (), ()), ("BLOCKED", (), ()),
                 ("CONTRADICTED", ("run-0",), ("run-0",))]
        for status, allowed, required in cases:
            with self.subTest(status=status):
                self.assertEqual(checker.check(answer(status, required), one_claim_fixture(status, allowed, required)), [])
        verified = answer("VERIFIED", ["log-1"], required=[])
        self.assertEqual(checker.check(verified, one_claim_fixture("VERIFIED", ["log-1"], ["log-1"])), [])

    def test_overall_precedence_is_contradicted_blocked_not_verified_verified(self):
        f = checker.overall_status
        self.assertEqual(f(["VERIFIED", "NOT_VERIFIED", "BLOCKED", "CONTRADICTED"]), "CONTRADICTED")
        self.assertEqual(f(["VERIFIED", "NOT_VERIFIED", "BLOCKED"]), "BLOCKED")
        self.assertEqual(f(["VERIFIED", "NOT_VERIFIED"]), "NOT_VERIFIED")
        self.assertEqual(f(["VERIFIED", "VERIFIED"]), "VERIFIED")

    def test_unverified_overall_requires_next_evidence(self):
        bad = answer("NOT_VERIFIED", required=[])
        self.assertIn("MISSING_NEXT_EVIDENCE", codes(checker.check(bad, one_claim_fixture("NOT_VERIFIED"))))
        blank = answer("NOT_VERIFIED", required=["  "])
        self.assertIn("INVALID_REQUIRED_EVIDENCE", codes(checker.check(blank, one_claim_fixture("NOT_VERIFIED"))))


class Mutations(unittest.TestCase):
    def mutate(self, edit):
        data = copy.deepcopy(GOOD)
        edit(data)
        return codes(checker.check(data, FIXTURE))

    def test_removed_required_field(self):
        self.assertEqual(self.mutate(lambda d: d.pop("REQUIRED_EVIDENCE")), ["INVALID_FIELDS"])
        self.assertEqual(self.mutate(lambda d: d.update(EXTRA=1)), ["INVALID_FIELDS"])

    def test_verified_without_its_required_evidence(self):
        self.assertIn("UNSUPPORTED_VERDICT", self.mutate(lambda d: d["CLAIMS"][1].update(evidence_ids=["log-2"])))
        self.assertIn("UNSUPPORTED_VERDICT", self.mutate(lambda d: d["CLAIMS"][1].update(evidence_ids=[])))

    def test_invented_evidence_id(self):
        self.assertIn("UNKNOWN_EVIDENCE", self.mutate(lambda d: d["CLAIMS"][1].update(evidence_ids=["log-1", "fake"])))

    def test_missing_unknown_and_duplicate_claims(self):
        self.assertIn("MISSING_CLAIMS", self.mutate(lambda d: d["CLAIMS"].pop()))
        self.assertIn("UNKNOWN_CLAIM", self.mutate(lambda d: d["CLAIMS"][0].update(id="ghost")))
        self.assertIn("DUPLICATE_CLAIM", self.mutate(lambda d: d["CLAIMS"].append(dict(d["CLAIMS"][0]))))
        self.assertIn("MISSING_CLAIMS", self.mutate(lambda d: d.update(CLAIMS=[])))

    def test_overall_conflicting_with_individual_verdicts(self):
        self.assertIn("INCONSISTENT_OVERALL_STATUS", self.mutate(lambda d: d.update(EVIDENCE_STATUS="VERIFIED")))
        self.assertIn("INCONSISTENT_OVERALL_STATUS", self.mutate(lambda d: d.update(EVIDENCE_STATUS="NOT_VERIFIED")))
        self.assertIn("INVALID_OVERALL_STATUS", self.mutate(lambda d: d.update(EVIDENCE_STATUS="MAYBE")))

    def test_duplicate_evidence_and_wrong_verdict(self):
        self.assertIn("DUPLICATE_EVIDENCE", self.mutate(lambda d: d["CLAIMS"][1].update(evidence_ids=["log-1", "log-1"])))
        self.assertIn("WRONG_VERDICT", self.mutate(lambda d: d["CLAIMS"][0].update(status="VERIFIED", evidence_ids=[])))

    def test_one_malformed_claim_does_not_cascade_into_an_overall_mismatch(self):
        def edit(d):
            d["CLAIMS"][2] = {"id": "gate", "status": "MAYBE", "evidence_ids": []}
        found = self.mutate(edit)
        self.assertIn("INVALID_STATUS", found)
        self.assertNotIn("INCONSISTENT_OVERALL_STATUS", found)

    def test_malformed_types_are_rejected_not_crashed(self):
        self.assertEqual(checker.check([], FIXTURE), ["INVALID_ANSWER: 답변이 JSON 객체가 아니다"])
        self.assertIn("INVALID_CLAIM", self.mutate(lambda d: d["CLAIMS"].__setitem__(0, "x")))
        self.assertIn("INVALID_CLAIM_ID", self.mutate(lambda d: d["CLAIMS"][0].update(id=["tests"])))
        self.assertIn("INVALID_STATUS", self.mutate(lambda d: d["CLAIMS"][0].update(status=["NOT_VERIFIED"])))
        self.assertIn("INVALID_EVIDENCE_IDS", self.mutate(lambda d: d["CLAIMS"][1].update(evidence_ids="log-1")))
        self.assertIn("INVALID_REQUIRED_EVIDENCE", self.mutate(lambda d: d.update(REQUIRED_EVIDENCE="x")))


class FixtureSchema(unittest.TestCase):
    def rejects(self, fixture):
        with self.assertRaises(checker.FixtureError):
            checker.validate_fixture(fixture)

    def test_valid_fixture_is_accepted(self):
        checker.validate_fixture(FIXTURE)

    def test_invalid_fixtures(self):
        self.rejects([])
        self.rejects({"claims": {}})
        self.rejects({"claims": {"c": {"expected_status": "VERIFIED"}}})
        self.rejects(one_claim_fixture("MAYBE"))
        self.rejects(one_claim_fixture("VERIFIED", ["a"], []))      # VERIFIED는 필요 증거가 있어야 한다
        self.rejects(one_claim_fixture("CONTRADICTED", ["a"], []))
        self.rejects(one_claim_fixture("NOT_VERIFIED", ["a"], ["b"]))  # required는 allowed의 부분집합
        self.rejects(one_claim_fixture("NOT_VERIFIED", ["a", "a"], []))
        self.rejects({"claims": {"c": {"expected_status": "NOT_VERIFIED", "allowed_evidence": "a",
                                       "required_evidence": []}}})


class CommandLine(unittest.TestCase):
    def run_cli(self, answer_text, fixture_text=None):
        with tempfile.TemporaryDirectory() as tmp:
            a, f = Path(tmp) / "a.json", Path(tmp) / "f.json"
            a.write_text(answer_text, encoding="utf-8")
            f.write_text(fixture_text if fixture_text is not None else json.dumps(FIXTURE), encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(CHECKER), str(a), str(f)],
                                    capture_output=True, text=True, encoding="utf-8",
                                    env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return result.returncode, result.stdout, result.stderr

    def test_exit_codes(self):
        code, out, _ = self.run_cli(json.dumps(GOOD))
        self.assertEqual((code, out.strip().splitlines()[-1]), (0, "EVIDENCE-ANSWER: PASS (0)"))
        bad = copy.deepcopy(GOOD)
        bad["CLAIMS"][1]["evidence_ids"] = []
        code, out, _ = self.run_cli(json.dumps(bad))
        self.assertEqual(code, 1)
        self.assertIn("위반 UNSUPPORTED_VERDICT", out)

    def test_broken_answer_json_is_a_contract_failure_not_a_checker_error(self):
        code, out, _ = self.run_cli("{not json")
        self.assertEqual(code, 1)
        self.assertIn("INVALID_JSON", out)

    def test_duplicate_json_keys_in_the_answer_are_rejected(self):
        text = json.dumps(GOOD).replace('"EVIDENCE_STATUS": "CONTRADICTED"',
                                        '"EVIDENCE_STATUS": "VERIFIED", "EVIDENCE_STATUS": "CONTRADICTED"')
        code, out, _ = self.run_cli(text)
        self.assertEqual(code, 1)
        self.assertIn("중복 키", out)

    def test_fixture_problems_and_unreadable_input_are_checker_errors(self):
        code, _, err = self.run_cli(json.dumps(GOOD), "{}")
        self.assertEqual(code, 2)
        self.assertIn("CHECKER_ERROR", err)
        code, _, _ = self.run_cli(json.dumps(GOOD), '{"claims": {}, "claims": {}}')
        self.assertEqual(code, 2)
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, "-B", str(CHECKER), str(Path(tmp) / "missing.json"),
                                     str(Path(tmp) / "none.json")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()

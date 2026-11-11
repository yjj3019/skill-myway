import copy
import json
import tempfile
import subprocess
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import compare_evaluations  # noqa: E402


def fixture():
    context = {"cases": "set-a", "rubric": "rubric-a", "scorer": "scorer-a", "environment": "env-a"}
    trials = [
        {"case": "case-a", "repeat": 1, "baseline": "FAIL", "candidate": "PASS"},
        {"case": "case-b", "repeat": 1, "baseline": "PASS", "candidate": "FAIL"},
        {"case": "case-c", "repeat": 1, "baseline": "PASS", "candidate": "PASS"},
        {"case": "case-d", "repeat": 1, "baseline": "FAIL", "candidate": "FAIL"},
        {"case": "case-e", "repeat": 1, "baseline": "TIMEOUT", "candidate": "NOT_RUN"},
    ]
    return {"schema_version": 1, "judgment_source": "human",
            "context": {"baseline": dict(context), "candidate": dict(context)},
            "planned": [{"case": trial["case"], "repeat": trial["repeat"]} for trial in trials],
            "trials": trials}


class ComparisonTests(unittest.TestCase):
    def test_counts_preserve_every_planned_pair_and_incomplete_sides(self):
        report = compare_evaluations.summarize(fixture())
        self.assertEqual(report["pairs"], {"planned": 5, "judged": 4, "incomplete": 1,
                           "fail_to_pass": 1, "pass_to_fail": 1, "pass_to_pass": 1, "fail_to_fail": 1})
        self.assertEqual(report["status_counts"]["baseline"]["TIMEOUT"], 1)
        self.assertEqual(report["status_counts"]["candidate"]["NOT_RUN"], 1)
        self.assertEqual(report["context_status"], "DECLARED_MATCH")
        self.assertNotIn("case-a", json.dumps(report))

    def test_unknown_and_changed_context_never_imply_comparability(self):
        doc = fixture()
        doc["context"]["candidate"]["environment"] = None
        doc["context"]["candidate"]["scorer"] = "scorer-b"
        report = compare_evaluations.summarize(doc)
        self.assertEqual(report["context_status"], "UNVERIFIED")
        self.assertEqual(report["missing_context"], ["environment"])
        self.assertEqual(report["different_context"], ["scorer"])
        self.assertEqual(report["pairs"]["planned"], 5)

    def test_duplicate_missing_and_invalid_records_are_rejected(self):
        variants = []
        x = fixture(); x["trials"].append(copy.deepcopy(x["trials"][0])); variants.append(x)
        x = fixture(); x["trials"][0]["repeat"] = True; variants.append(x)
        x = fixture(); x["trials"][0]["candidate"] = "SUCCESS"; variants.append(x)
        x = fixture(); del x["context"]["baseline"]["rubric"]; variants.append(x)
        x = fixture(); x["judgment_source"] = "mixed"; variants.append(x)
        x = fixture(); x["trials"] = []; variants.append(x)
        x = fixture(); x["trials"].pop(); variants.append(x)
        x = fixture(); x["planned"].append(dict(x["planned"][0])); variants.append(x)
        x = fixture(); x["trials"][0]["case"] = "unplanned"; variants.append(x)
        x = fixture(); x["context"]["baseline"]["rubric"] = "UNKNOWN"; variants.append(x)
        x = fixture(); x["trials"][0]["extra"] = "unexpected"; variants.append(x)
        for item in variants:
            with self.subTest(item=item):
                self.assertRaises(ValueError, compare_evaluations.summarize, item)

    def test_cli_rejects_duplicate_json_members_and_accepts_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            good = subprocess.run([sys.executable, str(ROOT / "scripts/compare_evaluations.py"), str(path)],
                                  capture_output=True, text=True, timeout=20)
            self.assertEqual(good.returncode, 0, good.stderr)
            report = json.loads(good.stdout)
            self.assertEqual(report["pairs"]["planned"], 5)
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            bad = subprocess.run([sys.executable, str(ROOT / "scripts/compare_evaluations.py"), str(path)],
                                 capture_output=True, text=True, timeout=20)
            self.assertNotEqual(bad.returncode, 0)
            self.assertNotIn(str(path), bad.stderr)
            path.write_text('{"schema_version":1,"schema_\\u0076ersion":1}', encoding="utf-8")
            escaped_duplicate = subprocess.run([sys.executable, str(ROOT / "scripts/compare_evaluations.py"), str(path)],
                                               capture_output=True, text=True, timeout=20)
            self.assertNotEqual(escaped_duplicate.returncode, 0)
            path.write_bytes(b" " * (compare_evaluations.MAX_BYTES + 1))
            oversized = subprocess.run([sys.executable, str(ROOT / "scripts/compare_evaluations.py"), str(path)],
                                       capture_output=True, text=True, timeout=20)
            self.assertNotEqual(oversized.returncode, 0)

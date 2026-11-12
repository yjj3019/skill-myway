import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import review_evaluation as gate


class ReviewEvaluation(unittest.TestCase):
    def setUp(self):
        self.output = "검토할 답변".encode()
        self.rubric = (ROOT / "tests/eval_cases/review-rubric.json").read_bytes()
        self.record = {"schema_version": 1, "output_sha256": gate.sha256(self.output),
                       "rubric_sha256": gate.sha256(self.rubric), "reviewer": "reviewer-1",
                       "independent": True, "criteria": [
                           {"id": c["id"], "status": "PASS", "reason": "확인한 이유",
                            "evidence": ["입력과 출력의 해당 구절"]}
                           for c in json.loads(self.rubric)["criteria"]]}

    def run_review(self):
        return gate.review(self.output, self.rubric, json.dumps(self.record).encode())

    def test_declared_pass_is_bound_to_bytes_and_is_not_authentication(self):
        result = self.run_review()
        self.assertEqual(result["verdict"], "NOT VERIFIED")
        self.assertEqual(result["declared_result"], "PASS")
        self.assertIn("not authenticated", result["note"])
        self.output += b"changed"
        with self.assertRaises(ValueError):
            self.run_review()

    def test_fail_and_unverified_never_pass(self):
        self.record["criteria"][0]["status"] = "FAIL"
        self.assertEqual(self.run_review()["verdict"], "FAIL")
        self.record["criteria"][0]["status"] = "NOT VERIFIED"
        self.assertEqual(self.run_review()["verdict"], "NOT VERIFIED")
        self.record["criteria"][0]["status"] = "PASS"
        self.record["independent"] = False
        self.assertEqual(self.run_review()["verdict"], "NOT VERIFIED")

    def test_fabricated_evidence_and_identity_cannot_promote_review(self):
        self.record["reviewer"] = "fictional"
        self.record["independent"] = True
        for item in self.record["criteria"]:
            item["evidence"] = ["missing-evidence.log"]
        result = self.run_review()
        self.assertEqual(result["declared_result"], "PASS")
        self.assertEqual(result["verdict"], "NOT VERIFIED")

    def test_evidence_files_are_checked_without_authenticating_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "trace.txt"
            artifact.write_bytes(b"observed")
            for item in self.record["criteria"]:
                item["evidence"] = [{"path": "trace.txt", "sha256": gate.sha256(b"observed")}]
            record = json.dumps(self.record).encode()
            result = gate.review(self.output, self.rubric, record, evidence_root=tmp)
            self.assertEqual(result["evidence_file_integrity"], "PASS")
            self.assertEqual(result["verdict"], "NOT VERIFIED")
            out, rubric, review = (Path(tmp) / name for name in ("output.md", "rubric.json", "review.json"))
            out.write_bytes(self.output)
            rubric.write_bytes(self.rubric)
            review.write_bytes(record)
            printed = io.StringIO()
            with redirect_stdout(printed):
                self.assertEqual(gate.main(["--evidence-root", tmp, str(out), str(rubric), str(review)]), 1)
            self.assertEqual(json.loads(printed.getvalue())["evidence_file_integrity"], "PASS")
            artifact.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                gate.review(self.output, self.rubric, record, evidence_root=tmp)
            artifact.unlink()
            with self.assertRaises(OSError):
                gate.review(self.output, self.rubric, record, evidence_root=tmp)

    def test_evidence_paths_cannot_escape_or_be_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("../outside.txt", str(Path(tmp).resolve() / "absolute.txt")):
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        gate.verify_evidence_file(tmp, {"path": name, "sha256": gate.sha256(b"")})
            with self.assertRaises(ValueError):
                gate.verify_evidence_file(tmp, "missing-evidence.log")
            with mock.patch.object(Path, "is_symlink", return_value=True):
                with self.assertRaises(ValueError):
                    gate.verify_evidence_file(tmp, {"path": "linked.txt", "sha256": gate.sha256(b"")})

    def test_incomplete_duplicate_and_unsubstantiated_pass_rejected(self):
        self.record["criteria"][0]["evidence"] = []
        with self.assertRaises(ValueError):
            self.run_review()
        self.record["criteria"][0]["evidence"] = ["some evidence"]
        self.record["criteria"].pop()
        with self.assertRaises(ValueError):
            self.run_review()
        self.record["criteria"].append(self.record["criteria"][0])
        with self.assertRaises(ValueError):
            self.run_review()

    def test_rubric_changes_and_invalid_json_are_rejected(self):
        self.rubric += b" "
        with self.assertRaises(ValueError):
            self.run_review()
        with self.assertRaises(ValueError):
            gate.review(self.output, b'{"schema_version":1,"schema_version":1}', b'{}')

    def test_template_writes_utf8_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output.md"
            rubric = Path(tmp) / "rubric.json"
            target = Path(tmp) / "review.json"
            output.write_bytes(self.output)
            rubric.write_bytes(self.rubric)
            self.assertEqual(gate.main(["--template", str(output), str(rubric), str(target)]), 0)
            record = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(record["output_sha256"], gate.sha256(self.output))
            self.assertFalse(record["independent"])
            self.assertTrue(all(item["status"] == "NOT VERIFIED" for item in record["criteria"]))
            self.assertEqual(gate.main(["--template", str(output), str(rubric), str(target)]), 1)

    def test_cli_reader_rejects_oversized_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "large.bin"
            source.write_bytes(b"x" * (gate.MAX_BYTES + 1))
            with self.assertRaises(ValueError):
                gate.read_bounded(source)


if __name__ == "__main__":
    unittest.main()

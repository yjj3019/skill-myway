import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import blind_review  # noqa: E402

SEED = "0" * 63 + "1"
CASES = {
    "cases": [
        {"id": "c1", "source": "가상 원고 A", "required_claims": ["수치 3", "조건 유지"], "protected_spans": ["`code`"]},
        {"id": "c2", "source": "가상 원고 B", "required_claims": [], "protected_spans": []},
    ]
}
CAND1 = {"c1": "후보 1의 첫 글", "c2": "후보 1의 둘째 글"}
CAND2 = {"c1": "후보 2의 첫 글", "c2": "후보 2의 둘째 글"}


class BlindReview(unittest.TestCase):
    def load(self):
        cases = blind_review.load_cases(CASES)
        ids = [c["id"] for c in cases]
        return cases, blind_review.load_candidates(CAND1, ids), blind_review.load_candidates(CAND2, ids)

    def test_assignment_is_complementary_and_deterministic(self):
        first = blind_review.assignment(SEED, "c1")
        self.assertEqual(first, blind_review.assignment(SEED, "c1"))
        self.assertEqual({first["A"], first["B"]}, {1, 2})
        self.assertNotEqual(first["A"], first["B"])

    def test_build_maps_candidates_and_hides_seed(self):
        cases, cand1, cand2 = self.load()
        packet, key = blind_review.build(cases, cand1, cand2, SEED)
        self.assertEqual(len(packet["cases"]), 2)
        mapping = {a["id"]: a for a in key["assignments"]}
        for case in packet["cases"]:
            order = mapping[case["id"]]
            first, second = (CAND1, CAND2) if order["A"] == 1 else (CAND2, CAND1)
            self.assertEqual(case["candidates"]["A"], first[case["id"]])
            self.assertEqual(case["candidates"]["B"], second[case["id"]])
        self.assertNotIn(SEED, json.dumps(packet))
        self.assertEqual(key["randomization"]["seed"], SEED)

    def test_reproducible_with_same_seed(self):
        cases, cand1, cand2 = self.load()
        packet_a, key_a = blind_review.build(cases, cand1, cand2, SEED)
        packet_b, key_b = blind_review.build(cases, cand1, cand2, SEED)
        self.assertEqual(packet_a, packet_b)
        self.assertEqual(key_a, key_b)

    def test_rejects_bad_cases(self):
        for bad in (
            {"cases": []},
            {"cases": [{"id": "x", "source": "s"}, {"id": "x", "source": "s"}]},
            {"cases": [{"id": "", "source": "s"}]},
            {"cases": [{"id": "x"}]},
        ):
            with self.assertRaises(ValueError):
                blind_review.load_cases(bad)

    def test_rejects_bad_candidates(self):
        ids = ["c1", "c2"]
        for bad in (
            {"c1": "a"},
            {"c1": "a", "c2": "b", "c3": "c"},
            {"c1": "a", "c2": ""},
            {"c1": "a", "c2": 3},
        ):
            with self.assertRaises(ValueError):
                blind_review.load_candidates(bad, ids)

    def test_rejects_bad_seed(self):
        for bad in ("", "abc", "g" * 64, "A" * 64):
            with self.assertRaises(ValueError):
                blind_review.assignment(bad, "c1")

    def test_write_refuses_overwrite(self):
        cases, cand1, cand2 = self.load()
        packet, key = blind_review.build(cases, cand1, cand2, SEED)
        with tempfile.TemporaryDirectory() as d:
            packet_path = Path(d) / "packet.json"
            key_path = Path(d) / "key.json"
            blind_review.write_outputs(packet, key, packet_path, key_path)
            with self.assertRaises(OSError):
                blind_review.write_outputs(packet, key, packet_path, key_path)
            self.assertTrue(packet_path.is_file())
            self.assertTrue(key_path.is_file())

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "cases.json").write_text(json.dumps(CASES, ensure_ascii=False), encoding="utf-8")
            (d / "a.json").write_text(json.dumps(CAND1, ensure_ascii=False), encoding="utf-8")
            (d / "b.json").write_text(json.dumps(CAND2, ensure_ascii=False), encoding="utf-8")
            code = blind_review.main([
                "--cases", str(d / "cases.json"),
                "--candidate-1", str(d / "a.json"),
                "--candidate-2", str(d / "b.json"),
                "--packet", str(d / "packet.json"),
                "--key", str(d / "key.json"),
                "--seed", SEED,
            ])
            self.assertEqual(code, 0)
            packet = json.loads((d / "packet.json").read_text(encoding="utf-8"))
            key = json.loads((d / "key.json").read_text(encoding="utf-8"))
            self.assertEqual(len(packet["cases"]), 2)
            self.assertEqual(len(key["assignments"]), 2)


if __name__ == "__main__":
    unittest.main()

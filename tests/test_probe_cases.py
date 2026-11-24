import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import probe_cases  # noqa: E402

BASELINE = ROOT / "tests" / "probe_baseline.json"


class ProbeCases(unittest.TestCase):
    def test_flags_case_that_echo_passes(self):
        weak = {"id": "w", "request": "가상 요청 alpha", "required": [["alpha"]]}
        strong = {"id": "s", "request": "가상 요청", "required": [["alpha"]]}
        self.assertEqual(probe_cases.weak_probes(weak), ["echo"])
        self.assertEqual(probe_cases.weak_probes(strong), [])

    def test_flags_filler_pass(self):
        case = {"id": "f", "request": "가상 요청", "required": [["없"]]}
        self.assertIn("filler", probe_cases.weak_probes(case))

    def test_no_new_weak_cases_beyond_baseline(self):
        """기준선에 없는 새 케이스는 퇴화 응답으로 통과하면 안 된다. 기준선은 줄이기만 한다."""
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        paths = [ROOT / "tests" / "eval_cases" / name for name in probe_cases.DEFAULT_FILES]
        current = probe_cases.scan(paths)
        added = sorted(key for key in current if key not in baseline)
        fixed = sorted(key for key in baseline if key not in current)
        self.assertEqual(added, [], "변별력이 약한 새 케이스가 있다. required를 요청문에 없는 구체 요건으로 바꾼다")
        self.assertEqual(fixed, [], "개선된 케이스가 있다. probe_baseline.json에서 제거한다")
        for key, probes in current.items():
            self.assertEqual(sorted(set(probes) - set(baseline[key])), [], f"{key}에 새 퇴화 프로브 통과")


if __name__ == "__main__":
    unittest.main()

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import run_eval  # noqa: E402
import simulate_eval  # noqa: E402


def sample_cases():
    skills = simulate_eval.skill_names()
    return {
        "schema_version": 1,
        "cases": [
            {"skill": name, "id": f"{name}-x", "request": f"{name} 가상 요청입니다. 충분히 긴 요청.",
             "required": ["결과"], "forbidden": [], "max_chars": 4000}
            for name in skills
        ],
    }


class SimulateEval(unittest.TestCase):
    def test_coverage_and_schema_pass(self):
        self.assertEqual(simulate_eval.validate(sample_cases()), [])

    def test_missing_coverage_fails(self):
        doc = sample_cases()
        doc["cases"] = doc["cases"][:-1]
        errors = simulate_eval.validate(doc)
        self.assertTrue(any("커버리지" in e for e in errors))

    def test_duplicate_and_unknown_skill_fail(self):
        doc = sample_cases()
        doc["cases"].append(dict(doc["cases"][0]))
        doc["cases"].append({"skill": "nope", "id": "nope-1", "request": "충분히 긴 가상 요청입니다.",
                             "required": [], "forbidden": [], "max_chars": 1000})
        errors = simulate_eval.validate(doc)
        self.assertTrue(any("중복" in e for e in errors))
        self.assertTrue(any("알 수 없는 스킬" in e for e in errors))

    def test_unsafe_request_rejected(self):
        doc = sample_cases()
        # 검증기 자신의 예시 규칙(실제 형식 CVE/이메일 금지)에 걸리지 않도록 조각으로 조립한다.
        unsafe = "연락은 test@" + "example.com 으로, " + "CVE-" + "2024" + "-12345 참고"
        doc["cases"][0]["request"] = unsafe
        errors = simulate_eval.validate(doc)
        self.assertTrue(any("민감 패턴" in e for e in errors))

    def test_manifest_is_deterministic(self):
        doc = sample_cases()
        first = simulate_eval.manifest(doc)
        second = simulate_eval.manifest(doc)
        self.assertEqual(first, second)
        self.assertEqual(len(first["cases"]), len(doc["cases"]))
        for item in first["cases"]:
            self.assertEqual(len(item["request_sha256"]), 64)
            self.assertEqual(len(item["skill_sha256"]), 64)


class RunEval(unittest.TestCase):
    def test_evaluate_output_checks(self):
        case = {"required": ["결론", "근거"], "forbidden": ["혁신"], "max_chars": 100}
        ok = run_eval.evaluate_output("결론과 근거를 적었습니다.", case)
        self.assertEqual(ok["missing_required"], [])
        self.assertEqual(ok["forbidden_found"], [])
        self.assertTrue(ok["within_limit"])
        bad = run_eval.evaluate_output("혁신적인 결론", case)
        self.assertEqual(bad["missing_required"], ["근거"])
        self.assertEqual(bad["forbidden_found"], ["혁신"])

    def test_length_limit(self):
        case = {"required": [], "forbidden": [], "max_chars": 5}
        self.assertFalse(run_eval.evaluate_output("0123456", case)["within_limit"])

    def test_required_alternatives(self):
        case = {"required": [["미검증", "UNVERIFIED"], "skip"], "forbidden": [], "max_chars": 1000}
        ok = run_eval.evaluate_output("상태는 UNVERIFIED이며 skip 1건입니다.", case)
        self.assertEqual(ok["missing_required"], [])
        bad = run_eval.evaluate_output("상태는 확인됨입니다.", case)
        self.assertEqual(len(bad["missing_required"]), 2)

    def test_dry_run_does_not_call_model(self):
        code = run_eval.main(["--dry-run", "--only", "writing"])
        self.assertEqual(code, 0)

    def test_platform_commands(self):
        claude = run_eval.platform_command("claude", "hi")
        self.assertEqual(claude[:2], ["claude", "--plugin-dir"])
        self.assertEqual(run_eval.platform_command("codex", "hi")[:2], ["codex", "exec"])
        self.assertEqual(run_eval.platform_command("grok", "hi")[:2], ["grok", "-p"])
        with self.assertRaises(ValueError):
            run_eval.platform_command("nope", "hi")

    def test_prepare_workdir(self):
        import shutil
        for platform, rel in (("claude", None), ("codex", ".agents/skills"), ("grok", ".grok/skills")):
            workdir = run_eval.prepare_workdir(platform)
            try:
                if rel is None:
                    self.assertEqual(list(workdir.iterdir()), [])
                else:
                    base = workdir / rel
                    self.assertTrue(base.is_dir())
                    names = {p.name for p in base.iterdir() if (p / "SKILL.md").is_file()}
                    self.assertEqual(names, set(simulate_eval.skill_names()))
            finally:
                shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

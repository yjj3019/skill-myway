import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo  # noqa: E402


VER = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


class ValidateRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        shutil.copytree(ROOT, self.tmp / "r", ignore=shutil.ignore_patterns(".git", "__pycache__", "tests"))
        self.r = self.tmp / "r"

    def errs(self, terms=()):
        return validate_repo.validate(self.r, terms)

    def skill(self, name="writing"):
        return self.r / "plugins/myway/skills" / name / "SKILL.md"

    def test_clean_repo_passes(self):
        self.assertEqual(self.errs(), [])

    def test_name_mismatch(self):
        p = self.skill()
        p.write_text(p.read_text(encoding="utf-8").replace("name: writing", "name: other", 1), encoding="utf-8")
        self.assertTrue(any("name" in e for e in self.errs()))

    def test_long_description(self):
        p = self.skill()
        t = p.read_text(encoding="utf-8").splitlines()
        i = next(n for n, l in enumerate(t) if l.startswith("description:"))
        t[i] = "description: " + "가" * 1100
        p.write_text("\n".join(t) + "\n", encoding="utf-8")
        self.assertTrue(any("description" in e for e in self.errs()))

    def test_yaml_unsafe_description(self):
        p = self.skill()
        t = p.read_text(encoding="utf-8").splitlines()
        i = next(n for n, l in enumerate(t) if l.startswith("description:"))
        t[i] = "description: 사용법: 이렇게 쓴다"
        p.write_text("\n".join(t) + "\n", encoding="utf-8")
        self.assertTrue(any("YAML" in e for e in self.errs()))

    def test_crlf_frontmatter_ok(self):
        p = self.skill()
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(self.errs(), [])

    def test_bom_frontmatter_ok(self):
        p = self.skill()
        p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
        self.assertEqual(self.errs(), [])

    def test_source_path_traversal_rejected(self):
        mp = self.r / ".claude-plugin/marketplace.json"
        data = json.loads(mp.read_text(encoding="utf-8"))
        data["plugins"][0]["source"] = "./plugins/../../outside"
        mp.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("'..'" in e for e in self.errs()))

    def test_validation_is_repeatable(self):
        self.assertEqual(self.errs(), self.errs())

    def test_version_mismatch(self):
        (self.r / "VERSION").write_text("9.9.9\n")
        self.assertTrue(any("버전" in e for e in self.errs()))

    def test_root_plugin_version_mismatch(self):
        p = self.r / "plugins/myway/plugin.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["version"] = "0.0.1"
        p.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("plugin.json" in e for e in self.errs()))

    def test_missing_root_plugin(self):
        (self.r / "plugins/myway/plugin.json").unlink()
        self.assertTrue(any("plugin.json 없음" in e for e in self.errs()))

    def test_codex_version_mismatch(self):
        p = self.r / "plugins/myway/.codex-plugin/plugin.json"
        p.write_text(p.read_text(encoding="utf-8").replace(VER, "0.0.1"), encoding="utf-8")
        self.assertTrue(any("codex" in e for e in self.errs()))

    def test_codex_plugin_manifest_missing(self):
        (self.r / "plugins/myway/.codex-plugin/plugin.json").unlink()
        self.assertTrue(any("codex" in e.lower() for e in self.errs()))

    def test_codex_plugin_skills_path_invalid(self):
        p = self.r / "plugins/myway/.codex-plugin/plugin.json"
        meta = json.loads(p.read_text(encoding="utf-8"))
        for skills in (None, "", [], "./missing"):
            with self.subTest(skills=skills):
                meta["skills"] = skills
                p.write_text(json.dumps(meta), encoding="utf-8")
                self.assertTrue(any("skills" in e for e in self.errs()))

    def test_codex_marketplace_bad_path(self):
        p = self.r / ".agents/plugins/marketplace.json"
        p.write_text(p.read_text(encoding="utf-8").replace("./plugins/myway", "./nope"), encoding="utf-8")
        self.assertTrue(any("Codex" in e for e in self.errs()))

    def test_codex_marketplace_missing(self):
        (self.r / ".agents/plugins/marketplace.json").unlink()
        self.assertTrue(any("Codex" in e for e in self.errs()))

    def test_grok_marketplace_version_and_path(self):
        p = self.r / ".grok-plugin/marketplace.json"
        raw = p.read_text(encoding="utf-8")
        p.write_text(raw.replace(VER, "0.0.1"), encoding="utf-8")
        self.assertTrue(any("grok" in e for e in self.errs()))
        p.write_text(raw.replace("./plugins/myway", "./nope"), encoding="utf-8")
        self.assertTrue(any("Grok" in e for e in self.errs()))

    def test_broken_manifest(self):
        (self.r / ".claude-plugin/marketplace.json").write_text("{")
        self.assertTrue(self.errs())

    def test_missing_reference(self):
        p = self.skill()
        p.write_text(p.read_text(encoding="utf-8") + "\n`references/nope-missing.md`\n", encoding="utf-8")
        self.assertTrue(any("nope-missing" in e for e in self.errs()))

    def test_sensitive_patterns(self):
        n = self.r / "docs" / "x.md"
        for bad in ("a" * 32, "me@" + "corp.test", "10.1." + "2.3", "/home" + "/someone/x", "ghp_" + "a" * 20, "CVE-" + "2026-12345", "RHSA-" + "2026:1234"):
            n.write_text(bad)
            self.assertTrue(any("민감" in e for e in self.errs()), bad)

    def test_safe_values_allowed(self):
        (self.r / "docs" / "x.md").write_text("203.0.113.5 and a@example.com and 127.0.0.1")
        self.assertEqual(self.errs(), [])

    def test_banned_terms(self):
        (self.r / "docs" / "x.md").write_text("Secret Corp")
        self.assertTrue(any("금지어" in e for e in self.errs(["secret corp"])))


class RhelCveExample(unittest.TestCase):
    def test_example_passes_checker(self):
        import subprocess
        d = ROOT / "plugins/myway/skills/rhel-cve"
        text = (d / "references/report-example.md").read_text(encoding="utf-8")
        body = text.split("\n<!-- REPORT START -->\n", 1)[1]
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "r.md"
            f.write_text(body, encoding="utf-8")
            r = subprocess.run([sys.executable, str(d / "scripts/check_report.py"), str(f)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_report_checker_rejects_structural_errors(self):
        import importlib.util
        d = ROOT / "plugins/myway/skills/rhel-cve"
        spec = importlib.util.spec_from_file_location("cve_report_check", d / "scripts/check_report.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        example = (d / "references/report-example.md").read_text(encoding="utf-8-sig")
        body = example.split("\n<!-- REPORT START -->\n", 1)[1]
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.md"
            def errors(text):
                report.write_text(text, encoding="utf-8")
                return checker.check(report)
            self.assertEqual(errors(body.replace("CVE-2099-00001 -", "CVE-2099-00001, CVE-2099-00002 -", 1)), [])
            self.assertEqual(errors(body.replace("2099-08-10 기준 )", "99/08/10 기준 )").replace(checker.NOTICE, checker.LEGACY_NOTICE)), [])
            for changed in (
                body.replace("### 3. 완화 방법(Mitigation)", "### 3. 기타"),
                body.replace("Fixed Package | RHSA", "Package | RHSA"),
                body.replace(checker.NOTICE, "주의 문구 없음"),
                body.replace("2099-08-10 기준 )", "YYYY-MM-DD 기준 )"),
                body.replace("| RHEL 9 | 미확인 | examplepkg | 미확인 | 미확인 | 미확인 | 가상 데이터 |", "| RHEL 9 | 미확인 |"),
            ):
                self.assertTrue(errors(changed))


class GradeCalc(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / "plugins/myway/skills/admission-helper/scripts"))
        import grade_calc
        self.g = grade_calc

    def test_safe_eval_arithmetic(self):
        self.assertAlmostEqual(self.g.safe_eval("930+70*x/9.8", 9.8), 1000.0)

    def test_safe_eval_rejects_code(self):
        for bad in ("__import__('os').getcwd()", "x.__class__", "open('f')", "[1]"):
            with self.assertRaises(Exception):
                self.g.safe_eval(bad, 1.0)


class RunTests(unittest.TestCase):
    def test_zero_tests_fail(self):
        import run_tests
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run_tests.run(d), 1)

    def test_skip_fails(self):
        import run_tests
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "test_x.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n"
                "    @unittest.skip('x')\n    def test_a(self): pass\n", encoding="utf-8")
            self.assertEqual(run_tests.run(d), 1)


class InstallCodex(unittest.TestCase):
    def test_copy_and_skip(self):
        import install_skills
        expected = len([p for p in (ROOT / "plugins/myway/skills").iterdir() if (p / "SKILL.md").is_file()])
        with tempfile.TemporaryDirectory() as d:
            done, skipped = install_skills.install(d)
            self.assertEqual(len(done), expected)
            self.assertTrue((Path(d) / "writing" / "SKILL.md").is_file())
            done2, skipped2 = install_skills.install(d)
            self.assertEqual((done2, len(skipped2)), ([], expected))
            done3, _ = install_skills.install(d, force=True)
            self.assertEqual(len(done3), expected)

    def test_main_target_grok_uses_dest(self):
        import install_skills
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install_skills.main(["--dest", d]), 0)
            self.assertTrue((Path(d) / "devlog" / "SKILL.md").is_file())

    def test_targets_include_claude(self):
        import install_skills
        self.assertEqual(install_skills.TARGETS["claude"], "~/.claude/skills")
        self.assertEqual(install_skills.TARGETS["codex"], "~/.agents/skills")
        self.assertEqual(install_skills.TARGETS["grok"], "~/.grok/skills")


class PackageSkill(unittest.TestCase):
    def build(self, out):
        import package_skill
        src = ROOT / "plugins/myway/skills/writing"
        return package_skill.build(src, Path(out), "0.0.0")

    def test_zip_contains_skill_and_references(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            dest, count, digest = self.build(d)
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.name, "myway-writing-0.0.0.zip")
            with zipfile.ZipFile(dest) as archive:
                names = archive.namelist()
            self.assertIn("writing/SKILL.md", names)
            self.assertIn("writing/references/blog-post.md", names)
            self.assertFalse(any("__pycache__" in name for name in names))
            self.assertEqual(len(digest), 64)
            self.assertEqual(count, len(names))

    def test_output_is_reproducible(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _, _, first = self.build(a)
            _, _, second = self.build(b)
            self.assertEqual(first, second)

    def test_unknown_skill_fails(self):
        import package_skill
        with self.assertRaises(SystemExit):
            package_skill.skill_dirs(["no-such-skill"])


if __name__ == "__main__":
    unittest.main()

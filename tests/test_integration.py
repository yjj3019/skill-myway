import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import install_skills  # noqa: E402
import package_skill  # noqa: E402
import validate_repo  # noqa: E402

VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
SKILLS_DIR = ROOT / "plugins/myway/skills"


def skills():
    return sorted(p for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file())


class PackageAllSkills(unittest.TestCase):
    def test_every_skill_builds_with_frontmatter(self):
        self.assertGreaterEqual(len(skills()), 6)
        with tempfile.TemporaryDirectory() as d:
            for skill in skills():
                dest, count, digest = package_skill.build(skill, Path(d), VERSION)
                self.assertTrue(dest.is_file())
                self.assertEqual(len(digest), 64)
                with zipfile.ZipFile(dest) as archive:
                    names = archive.namelist()
                    body = archive.read(f"{skill.name}/SKILL.md").decode("utf-8")
                self.assertIn(f"{skill.name}/SKILL.md", names)
                self.assertEqual(count, len(names))
                front = validate_repo.frontmatter(body)
                self.assertIsNotNone(front)
                self.assertEqual(front.get("name"), skill.name)
                self.assertLessEqual(len(front.get("description", "")), 1024)
                self.assertLessEqual(body.count("\n") + 1, 500)
                for ref in re.findall(r"`((?:references|scripts)/[^`\s*]+\.\w+)`", body):
                    self.assertIn(f"{skill.name}/{ref}", names)

    def test_zip_excludes_junk(self):
        with tempfile.TemporaryDirectory() as d:
            for skill in skills():
                dest, _, _ = package_skill.build(skill, Path(d), VERSION)
                with zipfile.ZipFile(dest) as archive:
                    for name in archive.namelist():
                        self.assertNotIn("__pycache__", name)
                        self.assertFalse(Path(name).name.startswith("."), name)

    def test_build_is_reproducible(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            for skill in skills():
                _, _, first = package_skill.build(skill, Path(a), VERSION)
                _, _, second = package_skill.build(skill, Path(b), VERSION)
                self.assertEqual(first, second, skill.name)

    def test_zip_entries_are_safe(self):
        with tempfile.TemporaryDirectory() as d:
            for skill in skills():
                dest, _, _ = package_skill.build(skill, Path(d), VERSION)
                with zipfile.ZipFile(dest) as archive:
                    for info in archive.infolist():
                        name = info.filename
                        posix = PurePosixPath(name)
                        self.assertFalse(posix.is_absolute(), name)
                        self.assertNotIn("..", posix.parts, name)
                        self.assertEqual(posix.parts[0], skill.name, name)
                        self.assertFalse(name.endswith("/"), name)
                        mode = (info.external_attr >> 16) & 0o170000
                        self.assertNotEqual(mode, 0o120000, name)

    def test_zip_extracts_to_loadable_skill(self):
        # 플랫폼이 ZIP을 풀어 쓰는 상황을 모든 스킬에 대해 흉내 낸다.
        with tempfile.TemporaryDirectory() as d:
            for skill in skills():
                dest, _, _ = package_skill.build(skill, Path(d), VERSION)
                extract = Path(d) / "unpacked" / skill.name
                with zipfile.ZipFile(dest) as archive:
                    archive.extractall(extract)
                base = extract / skill.name
                body = (base / "SKILL.md").read_text(encoding="utf-8")
                front = validate_repo.frontmatter(body)
                self.assertIsNotNone(front)
                self.assertEqual(front.get("name"), skill.name)
                for ref in re.findall(r"`((?:references|scripts)/[^`\s*]+\.\w+)`", body):
                    self.assertTrue((base / ref).is_file(), f"{skill.name}: {ref}")


class InstallTargets(unittest.TestCase):
    def test_each_target_installs_all_skills(self):
        expected = len(skills())
        for target in ("claude", "codex", "grok"):
            with tempfile.TemporaryDirectory() as d:
                dest = Path(d) / target
                done, skipped = install_skills.install(dest)
                self.assertEqual(len(done), expected, target)
                self.assertEqual(skipped, [], target)
                for skill in skills():
                    self.assertTrue((dest / skill.name / "SKILL.md").is_file(), skill.name)

    def test_reinstall_skips_and_force_replaces(self):
        expected = len(skills())
        with tempfile.TemporaryDirectory() as d:
            install_skills.install(d)
            again, skipped = install_skills.install(d)
            self.assertEqual(again, [])
            self.assertEqual(len(skipped), expected)
            forced, _ = install_skills.install(d, force=True)
            self.assertEqual(len(forced), expected)


class Manifests(unittest.TestCase):
    def test_versions_are_synchronized(self):
        self.assertRegex(VERSION, r"^\d+\.\d+\.\d+$")
        files = {
            "marketplace": ROOT / ".claude-plugin/marketplace.json",
            "claude-plugin": ROOT / "plugins/myway/.claude-plugin/plugin.json",
            "codex-plugin": ROOT / "plugins/myway/.codex-plugin/plugin.json",
            "portable": ROOT / "plugins/myway/plugin.json",
            "grok": ROOT / ".grok-plugin/marketplace.json",
        }
        for label, path in files.items():
            data = json.loads(path.read_text(encoding="utf-8"))
            if label == "marketplace":
                got = data["metadata"]["version"]
                self.assertEqual(data["plugins"][0]["version"], VERSION)
            elif label == "grok":
                got = data["plugins"][0]["version"]
            else:
                got = data["version"]
            self.assertEqual(got, VERSION, label)

    def test_codex_submission_limits(self):
        codex = json.loads((ROOT / "plugins/myway/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
        interface = codex["interface"]
        self.assertLessEqual(len(interface["displayName"]), 30)
        self.assertLessEqual(len(interface["shortDescription"]), 30)
        self.assertLessEqual(len(interface["longDescription"]), 4000)
        self.assertLessEqual(len(interface["defaultPrompt"]), 3)
        for prompt in interface["defaultPrompt"]:
            self.assertLessEqual(len(prompt), 128)
        portable = json.loads((ROOT / "plugins/myway/plugin.json").read_text(encoding="utf-8"))
        openai = portable["extensions"]["com.openai"]["interface"]
        self.assertLessEqual(len(openai["shortDescription"]), 30)
        self.assertLessEqual(len(openai["displayName"]), 30)

    def test_marketplace_entries_resolve(self):
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        for entry in market["plugins"]:
            source = entry["source"]
            self.assertTrue(source.startswith("./"))
            self.assertTrue((ROOT / source[2:]).is_dir(), source)
        codex = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        for entry in codex["plugins"]:
            self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
            self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")
            self.assertTrue((ROOT / entry["source"]["path"][2:]).is_dir())
        grok = json.loads((ROOT / ".grok-plugin/marketplace.json").read_text(encoding="utf-8"))
        for entry in grok["plugins"]:
            self.assertEqual(entry["source"]["type"], "local")
            self.assertTrue((ROOT / entry["source"]["path"][2:]).is_dir())


class SkillAssets(unittest.TestCase):
    def test_every_skill_has_openai_yaml(self):
        for skill in skills():
            meta = skill / "agents/openai.yaml"
            self.assertTrue(meta.is_file(), skill.name)
            text = meta.read_text(encoding="utf-8")
            self.assertIn("display_name:", text)
            self.assertIn("short_description:", text)

    def test_readme_lists_every_skill(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        listed = set(re.findall(r"^\| `([a-z0-9-]+)` \|", text, re.M))
        self.assertEqual(listed, {s.name for s in skills()})

    def test_claude_md_lists_all_version_files(self):
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        for rel in ("VERSION", ".claude-plugin/marketplace.json",
                    "plugins/myway/.claude-plugin/plugin.json",
                    "plugins/myway/.codex-plugin/plugin.json",
                    "plugins/myway/plugin.json", ".grok-plugin/marketplace.json"):
            self.assertIn(rel, text)

    def test_docs_have_no_local_absolute_paths(self):
        docs = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
        for path in docs:
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"[A-Za-z]:\\\\", text), path.name)
            self.assertIsNone(re.search(r"/home/[a-z][\w.-]*/", text), path.name)

    def test_gitattributes_forces_lf(self):
        text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("eol=lf", text)


class DocumentLinks(unittest.TestCase):
    def test_readme_relative_links_exist(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)\s#]+)\)", text):
            if target.startswith(("http://", "https://", "#")):
                continue
            self.assertTrue((ROOT / target).exists(), target)

    def test_platform_docs_reference_files_exist(self):
        text = (ROOT / "docs/PLATFORMS.md").read_text(encoding="utf-8")
        for rel in (".claude-plugin/marketplace.json",
                    ".agents/plugins/marketplace.json",
                    ".grok-plugin/marketplace.json"):
            self.assertIn(rel, text)
            self.assertTrue((ROOT / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""스킬 폴더를 업로드용 ZIP으로 묶는다. Claude 앱·ChatGPT Skills 업로드에 쓴다.

사용: python3 scripts/package_skill.py [--skill NAME [NAME ...]] [--out DIR]
  기본은 myway 플러그인의 모든 스킬을 dist/ 아래에 하나씩 묶는다.
  ZIP 내부 경로는 `<스킬이름>/SKILL.md` 형태이며 라이선스 본문을 포함한다.
  __pycache__와 숨김 파일은 넣지 않는다.
  같은 입력이면 파일 시간을 고정해 같은 ZIP 바이트가 나온다.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path
from validate_repo import frontmatter

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins" / "myway" / "skills"
LICENSE = ROOT / "LICENSE"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
# Canonical MIT permission and disclaimer, with whitespace normalized.
MIT_BODY_SHA256 = "fe2a9817987f862eaced948f0468c7f51d2fedfc48c5c505b246a49a3870e9a5"


def validate_mit_text(content):
    try:
        lines = [line.strip() for line in content.decode("utf-8-sig").splitlines() if line.strip()]
    except UnicodeError as exc:
        raise ValueError("declared MIT license is not UTF-8") from exc
    copyright_line = r"Copyright\s+\(c\)\s+\d{4}(?:-\d{4})?\s+\S(?:.*\S)?"
    if len(lines) < 3 or lines[0] != "MIT License" or not re.fullmatch(copyright_line, lines[1]):
        raise ValueError("declared MIT license requires a copyright line and complete text")
    body = " ".join(" ".join(lines[2:]).split()).encode("utf-8")
    if hashlib.sha256(body).hexdigest() != MIT_BODY_SHA256:
        raise ValueError("declared MIT license does not match the supported standard text")


def local_skill_directories(root):
    if not root.is_dir():
        raise SystemExit(f"스킬 디렉터리 없음: {root}")
    resolved_root = root.resolve()
    found = []
    for path in sorted(root.iterdir()):
        if path.is_dir() and (path / "SKILL.md").is_file():
            if path.is_symlink() or path.resolve().parent != resolved_root:
                raise ValueError("linked skill directory is not supported")
            found.append(path)
    return found


def skill_dirs(names):
    found = local_skill_directories(SKILLS)
    if names == ["all"]:
        return found
    available = {path.name: path for path in found}
    selected = []
    for name in names:
        if name not in available:
            raise SystemExit(f"스킬 없음: {name}")
        selected.append(available[name])
    return selected


def skill_files(skill_dir):
    root = skill_dir.resolve()
    files = []
    for path in skill_dir.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("linked or out-of-tree skill path is not supported")
        if path.is_file() and "__pycache__" not in path.parts and not path.name.startswith("."):
            files.append(path)
    return sorted(files)


def skill_license(skill_dir, fallback):
    """Resolve declared licenses without substituting an unrelated license."""
    skill_body = (skill_dir / "SKILL.md").read_bytes()
    skill_text = skill_body.decode("utf-8")
    header = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", skill_text.lstrip("\ufeff"), re.DOTALL)
    if header and len(re.findall(r"(?m)^[ \t]*license[ \t]*:", header.group(1))) > 1:
        raise ValueError("duplicate skill license declarations")
    metadata = frontmatter(skill_text) or {}
    raw = metadata.get("_raw_license", "").strip()
    match = re.fullmatch(r"(?:\"([^\"]*)\"|'([^']*)'|([^\s#]+))(?:\s+#.*)?", raw) if raw else None
    if raw and not match:
        raise ValueError("unsupported skill license declaration")
    declared = next((part for part in match.groups() if part is not None), "") if match else ""
    if "license" in metadata and (not declared or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]*", declared)):
        raise ValueError("unsupported skill license declaration")
    own = skill_dir / "LICENSE"
    has_license = own.is_file()
    if not has_license and (own.exists() or own.is_symlink()):
        raise ValueError("skill license path is not a regular file")
    if declared and not has_license:
        raise ValueError("declared skill license has no license file")
    content = own.read_bytes() if has_license else fallback.read_bytes()
    if not content.strip():
        raise ValueError("skill license is empty")
    if declared == "MIT":
        validate_mit_text(content)
    return has_license, content, skill_body


def build(skill_dir, out_dir, version):
    files = skill_files(skill_dir)
    if not files:
        raise SystemExit(f"묶을 파일 없음: {skill_dir}")
    _, content, skill_body = skill_license(skill_dir, LICENSE)
    files = [path for path in files if path not in (skill_dir / "LICENSE", skill_dir / "SKILL.md")]
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"myway-{skill_dir.name}-{version}.zip"
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        entries = [(path.relative_to(skill_dir).as_posix(), path) for path in files]
        entries.extend((("LICENSE", None), ("SKILL.md", None)))
        for relative, path in sorted(entries):
            arcname = Path(skill_dir.name) / relative
            info = zipfile.ZipInfo(arcname.as_posix(), date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            data = content if relative == "LICENSE" else skill_body if relative == "SKILL.md" else path.read_bytes()
            archive.writestr(info, data)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    return dest, len(entries), digest


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    parser = argparse.ArgumentParser(description="스킬 폴더를 업로드용 ZIP으로 묶는다")
    parser.add_argument("--skill", nargs="+", default=["all"], help="스킬 이름 또는 all")
    parser.add_argument("--out", default=str(ROOT / "dist"), help="출력 디렉터리")
    args = parser.parse_args(argv)
    for skill_dir in skill_dirs(args.skill):
        dest, count, digest = build(skill_dir, Path(args.out), version)
        try:
            shown = dest.relative_to(ROOT)
        except ValueError:
            shown = dest
        print(f"{shown} ({count}개 파일, sha256 {digest})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

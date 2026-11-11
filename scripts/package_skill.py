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
import sys
import zipfile
from pathlib import Path
from validate_repo import frontmatter

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins" / "myway" / "skills"
LICENSE = ROOT / "LICENSE"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def skill_dirs(names):
    if not SKILLS.is_dir():
        raise SystemExit(f"스킬 디렉터리 없음: {SKILLS}")
    found = sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())
    if names == ["all"]:
        return found
    selected = []
    for name in names:
        path = SKILLS / name
        if not (path / "SKILL.md").is_file():
            raise SystemExit(f"스킬 없음: {name}")
        selected.append(path)
    return selected


def skill_files(skill_dir):
    return sorted(
        p
        for p in skill_dir.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith(".")
    )


def skill_license(skill_dir, fallback):
    """Resolve declared licenses without substituting an unrelated license."""
    metadata = frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8")) or {}
    declared = metadata.get("license", "").strip()
    own = skill_dir / "LICENSE"
    if declared and not own.is_file():
        raise ValueError("declared skill license has no license file")
    content = own.read_bytes() if own.is_file() else fallback.read_bytes()
    if not content.strip():
        raise ValueError("skill license is empty")
    if declared == "MIT" and not content.startswith(b"MIT License"):
        raise ValueError("declared MIT license does not match license file")
    return own.is_file(), content


def build(skill_dir, out_dir, version):
    files = skill_files(skill_dir)
    if not files:
        raise SystemExit(f"묶을 파일 없음: {skill_dir}")
    has_license, content = skill_license(skill_dir, LICENSE)
    license_bytes = None if has_license else content
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"myway-{skill_dir.name}-{version}.zip"
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            arcname = Path(skill_dir.name) / path.relative_to(skill_dir)
            info = zipfile.ZipInfo(arcname.as_posix(), date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
        if license_bytes is not None:
            info = zipfile.ZipInfo(f"{skill_dir.name}/LICENSE", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, license_bytes)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    return dest, len(files) + (license_bytes is not None), digest


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

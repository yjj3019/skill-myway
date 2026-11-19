#!/usr/bin/env python3
"""myway 스킬을 Claude Code·Codex·Grok Build용 사용자 스킬 디렉터리에 복사한다.

사용: python3 scripts/install_skills.py [--target claude|codex|grok|all] [--dest DIR] [--link]
  claude: ~/.claude/skills, codex: ~/.agents/skills, grok: ~/.grok/skills
  프로젝트 한정은 --dest <저장소>/.claude/skills 또는 <저장소>/.agents/skills를 쓴다.
  --link: 복사 대신 심볼릭 링크(저장소를 pull하면 바로 반영, Windows는 권한 필요)
같은 이름의 기존 스킬이 있으면 건드리지 않고 건너뛴다. 덮어쓰려면 --force.
"""
import argparse
import ctypes
import errno
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from package_skill import local_skill_directories, skill_files, skill_license

TARGETS = {"claude": "~/.claude/skills", "codex": "~/.agents/skills", "grok": "~/.grok/skills"}
SRC = Path(__file__).resolve().parent.parent / "plugins" / "myway" / "skills"
LICENSE = Path(__file__).resolve().parent.parent / "LICENSE"


def publish_without_replacing(staged, target):
    """Atomically publish a directory only if the target name is still free."""
    if os.name == "nt":
        for attempt in range(3):
            try:
                staged.rename(target)
                return
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.2 * (attempt + 1))
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux"):
        rename = getattr(libc, "renameat2", None)
        args = (-100, os.fsencode(staged), -100, os.fsencode(target), 1)
    elif sys.platform == "darwin":
        rename = getattr(libc, "renamex_np", None)
        args = (os.fsencode(staged), os.fsencode(target), 4)
    else:
        rename = None
    if rename is None:
        raise OSError(errno.ENOTSUP, "exclusive directory rename unavailable")
    rename.restype = ctypes.c_int
    if rename(*args) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))


def install_one(skill, target, link, force, checked_files):
    if not force and (target.exists() or target.is_symlink()):
        return False
    work = Path(tempfile.mkdtemp(prefix=".myway-install-", dir=target.parent))
    staged = work / "new"
    backup = work / "previous"
    keep_backup = False
    try:
        if link:
            staged.symlink_to(skill, target_is_directory=True)
        else:
            shutil.copytree(skill, staged, ignore=shutil.ignore_patterns("__pycache__", ".*"))
            license_content, skill_body = checked_files
            (staged / "LICENSE").write_bytes(license_content)
            (staged / "SKILL.md").write_bytes(skill_body)
        if target.exists() or target.is_symlink():
            if not force:
                return False
            target.rename(backup)
        try:
            if force:
                staged.rename(target)
            else:
                try:
                    publish_without_replacing(staged, target)
                except FileExistsError:
                    return False
        except BaseException:
            if backup.exists() or backup.is_symlink():
                try:
                    if target.exists() or target.is_symlink():
                        raise FileExistsError(target)
                    backup.rename(target)
                except OSError as exc:
                    keep_backup = True
                    raise OSError(f"기존 설치 복구 필요: {backup}") from exc
            raise
        return True
    finally:
        if not keep_backup:
            shutil.rmtree(work)


def install(dest, link=False, force=False):
    dest = Path(dest).expanduser()
    skills = local_skill_directories(SRC)
    destination = dest.resolve()
    source = SRC.resolve()
    if destination.is_relative_to(source):
        raise ValueError("설치 대상과 스킬 원본 경로가 겹침")
    license_contents = {}
    already_present = set()
    # Validate every selected license before changing any destination.
    for skill in skills:
        target = dest / skill.name
        if not force and (target.exists() or target.is_symlink()):
            already_present.add(skill.name)
            continue
        if source.is_relative_to(destination / skill.name):
            raise ValueError("설치 대상과 스킬 원본 경로가 겹침")
        skill_files(skill)
        if not link:
            _, license_content, skill_body = skill_license(skill, LICENSE)
            license_contents[skill.name] = (license_content, skill_body)
    dest.mkdir(parents=True, exist_ok=True)
    done, skipped = [], []
    for skill in skills:
        target = dest / skill.name
        if skill.name in already_present:
            skipped.append(skill.name)
            continue
        if install_one(skill, target, link, force, license_contents.get(skill.name)):
            done.append(skill.name)
        else:
            skipped.append(skill.name)
    return done, skipped


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=[*TARGETS, "all"], default="codex")
    ap.add_argument("--dest", help="대상 디렉터리(지정하면 --target 무시)")
    ap.add_argument("--link", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    dests = [a.dest] if a.dest else (list(TARGETS.values()) if a.target == "all" else [TARGETS[a.target]])
    for d in dests:
        done, skipped = install(d, a.link, a.force)
        print(f"[{d}] 설치:", ", ".join(done) or "없음")
        if skipped:
            print("  건너뜀(이미 존재, --force로 덮어쓰기):", ", ".join(skipped))
    print("에이전트를 재시작하면 목록에 나타납니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

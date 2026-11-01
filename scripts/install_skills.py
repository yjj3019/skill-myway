#!/usr/bin/env python3
"""myway 스킬을 Claude Code·Codex·Grok Build용 사용자 스킬 디렉터리에 복사한다.

사용: python3 scripts/install_skills.py [--target claude|codex|grok|all] [--dest DIR] [--link]
  claude: ~/.claude/skills, codex: ~/.agents/skills, grok: ~/.grok/skills
  프로젝트 한정은 --dest <저장소>/.claude/skills 또는 <저장소>/.agents/skills를 쓴다.
  --link: 복사 대신 심볼릭 링크(저장소를 pull하면 바로 반영, Windows는 권한 필요)
같은 이름의 기존 스킬이 있으면 건드리지 않고 건너뛴다. 덮어쓰려면 --force.
"""
import argparse
import shutil
import sys
from pathlib import Path

TARGETS = {"claude": "~/.claude/skills", "codex": "~/.agents/skills", "grok": "~/.grok/skills"}
SRC = Path(__file__).resolve().parent.parent / "plugins" / "myway" / "skills"


def install(dest, link=False, force=False):
    dest = Path(dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    done, skipped = [], []
    for skill in sorted(p for p in SRC.iterdir() if (p / "SKILL.md").is_file()):
        target = dest / skill.name
        if target.exists() or target.is_symlink():
            if not force:
                skipped.append(skill.name)
                continue
            shutil.rmtree(target) if target.is_dir() and not target.is_symlink() else target.unlink()
        if link:
            target.symlink_to(skill, target_is_directory=True)
        else:
            shutil.copytree(skill, target, ignore=shutil.ignore_patterns("__pycache__"))
        done.append(skill.name)
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

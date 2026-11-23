#!/usr/bin/env python3
"""플랫폼(Claude Code·Codex·Grok Build) 설치 상태를 진단한다.

항목마다 발견 여부(found), 필요한 것(need), 해결 안내(hint)를 출력한다.
필수 항목이 하나라도 없으면 1로 종료한다.

사용: python3 scripts/doctor.py [--platform claude|codex|grok|all]
"""
import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

TARGETS = {"claude": "~/.claude/skills", "codex": "~/.agents/skills", "grok": "~/.grok/skills"}


@dataclass
class Check:
    name: str
    found: bool
    need: str
    hint: str


def checks_for(platform, home=None, env=None):
    base = Path(home) if home else Path.home()
    commands = {"claude": "claude", "codex": "codex", "grok": "grok"}
    executable = shutil.which(commands[platform], path=(env or {}).get("PATH"))
    installed = (base / "skills" / "myway").exists()
    return [
        Check(
            name=f"{platform} 실행 파일",
            found=executable is not None,
            need=f"{platform} CLI가 PATH에 있어야 합니다",
            hint=f"{platform} 설치 안내에 따라 설치하고 PATH를 확인합니다",
        ),
        Check(
            name=f"{platform} 스킬 설치",
            found=installed,
            need=f"{platform} 사용자 스킬 디렉터리에 myway 스킬이 있어야 합니다 ({TARGETS[platform]})",
            hint="scripts/install_skills.py --target {0}로 설치합니다".format(platform),
        ),
    ]


def run(platforms, home=None, env=None):
    missing = []
    for name in platforms:
        for check in checks_for(name, home, env):
            state = "발견" if check.found else "없음"
            print(f"[{state}] {check.name}")
            if not check.found:
                print(f"  필요: {check.need}")
                print(f"  해결: {check.hint}")
                missing.append(check.name)
    if missing:
        print("진단 실패:", ", ".join(missing))
        return 1
    print("진단 통과: 필수 항목 모두 발견")
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=[*TARGETS, "all"], default="all")
    a = ap.parse_args(argv)
    platforms = list(TARGETS) if a.platform == "all" else [a.platform]
    return run(platforms)


if __name__ == "__main__":
    sys.exit(main())

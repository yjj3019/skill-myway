#!/usr/bin/env python3
"""스킬의 동작 이동(기록 위치·모드 전환)을 로컬 상태 파일에 JSONL로 누적한다.

기록 한 줄: {"ts": "...", "skill": "...", "kind": "...", "note": "..."}
- Windows: %LOCALAPPDATA%\\myway\\moves.jsonl
- 그 외: $XDG_STATE_HOME/myway/moves.jsonl (없으면 ~/.local/state/myway/moves.jsonl)
- --no-log: 이번 실행은 기록하지 않는다. 기록 실패는 보고만 하고 본 작업을 막지 않는다.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def log_path(environ=None):
    env = environ if environ is not None else os.environ
    home = env.get("HOME")
    if os.name == "nt":
        base = env.get("LOCALAPPDATA")
        if not base:
            raise OSError("LOCALAPPDATA가 설정되지 않아 이동 기록 경로를 정할 수 없습니다")
    else:
        base = env.get("XDG_STATE_HOME") or (home and os.path.join(home, ".local", "state"))
        if not base:
            raise OSError("XDG_STATE_HOME과 HOME이 없어 이동 기록 경로를 정할 수 없습니다")
    return Path(os.path.join(base, "myway", "moves.jsonl"))


def append(line, environ=None, now=None):
    path = log_path(environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": now or datetime.now().astimezone().isoformat(timespec="seconds")}
    record.update(line)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def run(argv, environ=None):
    parser = argparse.ArgumentParser(description="스킬 동작 이동을 로컬 상태 파일에 기록한다.")
    parser.add_argument("--skill", required=True, help="동작 주체 스킬 이름")
    parser.add_argument("--kind", required=True, help="동작 유형(notion|fallback|session_log 등)")
    parser.add_argument("--note", default="", help="한 줄 설명")
    parser.add_argument("--no-log", action="store_true", help="이번 실행은 기록하지 않는다")
    args = parser.parse_args(argv)
    if args.no_log:
        print("moves 로그 생략(--no-log)")
        return 0
    try:
        path = append({"skill": args.skill, "kind": args.kind, "note": args.note}, environ)
    except OSError as error:
        print(f"moves 로그 기록 실패: {error}")
        return 1
    print(f"moves 로그 추가: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))

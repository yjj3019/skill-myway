#!/usr/bin/env python3
"""Claude Code stream-json 실행 로그에서 증거 장부를 만든다(모델이 아니라 호스트 로그가 근거다).

장부의 항목은 도구 호출 하나당 하나이며 호출 순서대로 `call:1`, `call:2`, ... 형식의 ID를 가진다.
도구 결과 원문은 저장하지 않는다. 도구 이름, 명령 요약, 종료 코드, 출력 SHA-256과 길이, 그리고
사람이 `--flag 이름=정규식`으로 미리 정한 패턴의 일치 여부만 남긴다. 정규식은 메모리에서만 쓴다.

한계(검증되지 않은 가정 포함):
  - 종료 코드는 셸 도구(Bash·PowerShell) 결과에서만 얻는다. 오류 결과의 "Exit code N" 머리말을 읽고,
    오류가 아니면 0으로 본다. 이 규칙은 합성 로그로만 시험했고 실제 로그 형식은 별도 실측이 필요하다.
  - 로그 파일 자체가 변조되지 않았다고 가정한다. 장부는 모델이 아니라 하네스가 만들어야 한다.
  - 대응하는 결과가 없는 도구 호출은 장부에서 빠지고 `unmatched` 수에만 잡힌다.

종료 코드: 0 성공, 2 오류(입력을 읽지 못함·형식을 해석할 수 없음·잘못된 --flag).
사용: python build_evidence_ledger.py RUN.jsonl --out LEDGER.json [--flag NAME=REGEX ...]
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = 1
SHELL_TOOLS = ("Bash", "PowerShell")
EXIT_HEAD = re.compile(r"^\s*Exit code\s+(\d+)")
MAX_BYTES = 64 * 1024 * 1024
MAX_MATCH_CHARS = 1024 * 1024  # 정규식은 이 길이까지만 본다
COMMAND_LIMIT = 300


class LedgerError(ValueError):
    """장부를 만들 수 없다(검사 불능)."""


def parse_flags(specs):
    flags = {}
    for spec in specs:
        name, sep, pattern = spec.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z0-9_]+", name) or not pattern:
            raise LedgerError(f"--flag는 이름=정규식 형식이어야 한다: {spec!r}")
        if name in flags:
            raise LedgerError(f"--flag 이름이 중복됐다: {name}")
        try:
            flags[name] = re.compile(pattern)
        except re.error as exc:
            raise LedgerError(f"--flag 정규식이 올바르지 않다({name}): {exc}") from exc
    return flags


def _result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part["text"] for part in content
                         if isinstance(part, dict) and isinstance(part.get("text"), str))
    return ""


def _summary(tool, data):
    if tool in SHELL_TOOLS:
        return str(data.get("command", ""))[:COMMAND_LIMIT]
    for key in ("file_path", "path", "pattern", "url"):
        if isinstance(data.get(key), str):
            return data[key][:COMMAND_LIMIT]
    return ""


def _exit_code(tool, is_error, text):
    if tool not in SHELL_TOOLS:
        return None
    if not is_error:
        return 0
    match = EXIT_HEAD.match(text)
    return int(match.group(1)) if match else None


def build_ledger(lines, flags=None):
    """stream-json 줄 목록에서 장부를 만든다."""
    flags = flags or {}
    calls, order, results, events = {}, [], {}, 0
    for line in lines:
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        message = event.get("message") if isinstance(event, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        events += 1
        for item in content:
            if not isinstance(item, dict):
                continue
            call_id = item.get("id") if item.get("type") == "tool_use" else item.get("tool_use_id")
            if item.get("type") == "tool_use" and event.get("type") == "assistant":
                if not isinstance(call_id, str) or not call_id:
                    raise LedgerError("도구 호출에 id가 없다")
                if call_id in calls:
                    raise LedgerError(f"도구 호출 id가 중복됐다: {call_id}")
                data = item.get("input") if isinstance(item.get("input"), dict) else {}
                calls[call_id] = (item.get("name"), data)
                order.append(call_id)
            elif item.get("type") == "tool_result" and event.get("type") == "user" and isinstance(call_id, str):
                results.setdefault(call_id, item)
    if events == 0:
        raise LedgerError("해석할 수 있는 stream-json 이벤트가 없다")

    entries, unmatched = [], 0
    for call_id in order:
        result = results.get(call_id)
        if result is None:
            unmatched += 1
            continue
        tool, data = calls[call_id]
        text = _result_text(result.get("content"))
        raw = text.encode("utf-8")
        is_error = bool(result.get("is_error"))
        entries.append({
            "id": f"call:{len(entries) + 1}",
            "tool": tool if isinstance(tool, str) else "",
            "command": _summary(tool, data),
            "exit_code": _exit_code(tool, is_error, text),
            "is_error": is_error,
            "output_sha256": hashlib.sha256(raw).hexdigest(),
            "output_bytes": len(raw),
            "flags": {name: bool(rx.search(text[:MAX_MATCH_CHARS])) for name, rx in flags.items()},
        })
    return {"schema_version": SCHEMA_VERSION, "source": "claude-stream-json",
            "unmatched": unmatched, "entries": entries}


def main(argv=None):
    cli = argparse.ArgumentParser(description="stream-json 실행 로그에서 증거 장부를 만든다(원문은 저장하지 않는다).")
    cli.add_argument("run_log", type=Path, help="Claude --output-format stream-json 로그")
    cli.add_argument("--out", type=Path, required=True, help="장부 JSON 출력 경로")
    cli.add_argument("--flag", action="append", default=[], metavar="이름=정규식",
                     help="출력에 대해 일치 여부만 기록할 패턴(여러 번 지정 가능)")
    args = cli.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # 콘솔 인코딩이 한국어를 못 담아도 출력이 죽지 않게 한다
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    try:
        if args.run_log.stat().st_size > MAX_BYTES:
            raise LedgerError("로그가 너무 크다")
        flags = parse_flags(args.flag)
        ledger = build_ledger(args.run_log.read_text(encoding="utf-8-sig").splitlines(), flags)
        args.out.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"LEDGER_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"EVIDENCE-LEDGER: {len(ledger['entries'])} 항목, 결과 없는 호출 {ledger['unmatched']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

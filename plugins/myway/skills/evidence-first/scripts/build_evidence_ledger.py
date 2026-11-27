#!/usr/bin/env python3
"""실행 로그에서 증거 장부를 만든다(모델이 아니라 호스트 로그가 근거다).

지원 로그: Claude Code `--output-format stream-json`, Codex `exec --json`, Grok `--output-format streaming-json`.
호스트는 이벤트 모양으로 자동 판별하며 여러 호스트가 섞이면 오류다.

장부의 항목은 도구 호출 하나당 하나이며 호출 순서대로 `call:1`, `call:2`, ... 형식의 ID를 가진다.
도구 결과 원문은 저장하지 않는다. 도구 이름, 명령 요약, 종료 코드, 출력 SHA-256과 길이, 그리고
사람이 `--flag 이름=정규식`으로 미리 정한 패턴의 일치 여부만 남긴다. 정규식은 메모리에서만 쓴다.

호스트별 근거와 한계:
  - Claude Code: 종료 코드는 셸 도구(Bash·PowerShell) 결과에서만 얻는다. 오류 결과의 "Exit code N" 머리말을 읽고
    오류가 아니면 0으로 본다. 실제 로그로 확인했다(Windows, Bash 도구, 성공과 종료 코드 1).
  - Codex: `item.completed`의 command_execution만 센다. `exit_code`와 `aggregated_output`을 그대로 쓰고 status가
    completed가 아니면 오류다. 실제 로그에서 구조, 실패 사례(exit_code -1, status failed), 성공 사례(exit_code 0,
    status completed)를 확인했다. 명령은 호스트가 셸(예: Windows의 powershell.exe -Command ...)로 감싼 문자열로
    기록되므로 command_regex는 감싼 전체 문자열에 맞춘다.
  - Grok: `tool_call`과 rawOutput이 있는 마지막 `tool_call_update`를 짝짓고 `exit_code`와 `output_for_prompt`를 쓴다.
    실제 로그의 성공 사례(exit_code 0)만 확인했다.
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


def _claude_calls(events):
    """Claude Code stream-json: assistant의 tool_use와 user의 tool_result를 짝짓는다."""
    calls, order, results = {}, [], {}
    for event in events:
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for item in content if isinstance(content, list) else []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use" and event.get("type") == "assistant":
                call_id = item.get("id")
                if not isinstance(call_id, str) or not call_id:
                    raise LedgerError("도구 호출에 id가 없다")
                if call_id in calls:
                    raise LedgerError(f"도구 호출 id가 중복됐다: {call_id}")
                calls[call_id] = (item.get("name"), item["input"] if isinstance(item.get("input"), dict) else {})
                order.append(call_id)
            elif item.get("type") == "tool_result" and event.get("type") == "user" \
                    and isinstance(item.get("tool_use_id"), str):
                results.setdefault(item["tool_use_id"], item)
    found, unmatched = [], 0
    for call_id in order:
        result = results.get(call_id)
        if result is None:
            unmatched += 1
            continue
        tool, data = calls[call_id]
        text = _result_text(result.get("content"))
        is_error = bool(result.get("is_error"))
        found.append((tool, _summary(tool, data), _exit_code(tool, is_error, text), is_error, text))
    return found, unmatched


def _codex_calls(events):
    """Codex exec --json: item.completed의 command_execution만 호출로 센다(시작만 있고 끝이 없으면 결과 없음)."""
    started, done, found = set(), set(), []
    for event in events:
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        item_id = item.get("id")
        if event.get("type") == "item.started":
            started.add(item_id)
        elif event.get("type") == "item.completed":
            if item_id in done:
                raise LedgerError(f"Codex 항목 id가 중복됐다: {item_id}")
            done.add(item_id)
            code = item.get("exit_code")
            code = code if isinstance(code, int) and not isinstance(code, bool) else None
            text = item.get("aggregated_output")
            found.append(("command_execution", str(item.get("command", ""))[:COMMAND_LIMIT], code,
                          item.get("status") != "completed", text if isinstance(text, str) else ""))
    return found, len(started - done)


def _grok_calls(events):
    """Grok --output-format streaming-json: tool_call과 rawOutput이 있는 마지막 tool_call_update를 짝짓는다."""
    calls, order, outputs = {}, [], {}
    for event in events:
        call_id = event.get("toolCallId")
        if not isinstance(call_id, str):
            continue
        if event.get("type") == "tool_call":
            if call_id in calls:
                raise LedgerError(f"도구 호출 id가 중복됐다: {call_id}")
            raw = event.get("rawInput")
            calls[call_id] = (event.get("toolName"), raw if isinstance(raw, dict) else {})
            order.append(call_id)
        elif event.get("type") == "tool_call_update" and isinstance(event.get("rawOutput"), dict):
            outputs[call_id] = event["rawOutput"]
    found, unmatched = [], 0
    for call_id in order:
        raw = outputs.get(call_id)
        if raw is None:
            unmatched += 1
            continue
        tool, data = calls[call_id]
        code = raw.get("exit_code")
        code = code if isinstance(code, int) and not isinstance(code, bool) else None
        text = raw.get("output_for_prompt")
        summary = str(data.get("command", ""))[:COMMAND_LIMIT] if "command" in data else _summary(tool, data)
        found.append((tool if isinstance(tool, str) else "", summary, code, code not in (None, 0),
                      text if isinstance(text, str) else ""))
    return found, unmatched


def _detect_host(events):
    hosts = set()
    for event in events:
        kind = event.get("type")
        if isinstance(event.get("message"), dict) and kind in ("assistant", "user"):
            hosts.add("claude")
        elif isinstance(kind, str) and kind.startswith("item.") and isinstance(event.get("item"), dict):
            hosts.add("codex")
        elif kind in ("tool_call", "tool_call_update"):
            hosts.add("grok")
    if len(hosts) != 1:
        raise LedgerError("해석할 수 있는 실행 로그가 아니거나 여러 호스트의 이벤트가 섞여 있다" if hosts
                          else "해석할 수 있는 stream-json 이벤트가 없다")
    return hosts.pop()


ADAPTERS = {"claude": (_claude_calls, "claude-stream-json"), "codex": (_codex_calls, "codex-exec-jsonl"),
            "grok": (_grok_calls, "grok-streaming-json")}


def build_ledger(lines, flags=None):
    """실행 로그 줄 목록에서 장부를 만든다. 호스트(Claude Code·Codex·Grok)는 이벤트 모양으로 판별한다."""
    flags = flags or {}
    events = []
    for line in lines:
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict):
            events.append(event)
    host = _detect_host(events)
    adapter, source = ADAPTERS[host]
    found, unmatched = adapter(events)
    entries = []
    for tool, command, code, is_error, text in found:
        raw = text.encode("utf-8")
        entries.append({
            "id": f"call:{len(entries) + 1}",
            "tool": tool if isinstance(tool, str) else "",
            "command": command,
            "exit_code": code,
            "is_error": is_error,
            "output_sha256": hashlib.sha256(raw).hexdigest(),
            "output_bytes": len(raw),
            "flags": {name: bool(rx.search(text[:MAX_MATCH_CHARS])) for name, rx in flags.items()},
        })
    return {"schema_version": SCHEMA_VERSION, "source": source, "unmatched": unmatched, "entries": entries}


def main(argv=None):
    cli = argparse.ArgumentParser(description="실행 로그(Claude Code·Codex·Grok)에서 증거 장부를 만든다(원문은 저장하지 않는다).")
    cli.add_argument("run_log", type=Path, help="호스트의 JSON 실행 로그")
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

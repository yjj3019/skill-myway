#!/usr/bin/env python3
"""Run and record a bounded, same-session two-turn skill evaluation."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import process_control
import run_eval
import simulate_eval

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIALOGUES = ROOT / "tests" / "eval_cases" / "dialogue_cases.json"


def session_id(raw, platform):
    found = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        if platform == "codex" and event.get("type") == "thread.started":
            found.append(event.get("thread_id"))
        if platform == "claude" and event.get("type") == "system" and event.get("subtype") == "init":
            found.append(event.get("session_id"))
    if len(found) != 1 or not isinstance(found[0], str):
        return None
    try:
        return str(uuid.UUID(found[0]))
    except ValueError:
        return None


def resume_command(platform, session, prompt):
    if platform == "codex":
        return ["codex", "exec", "--sandbox", "workspace-write", "--skip-git-repo-check",
                "resume", "--json", session, prompt]
    if platform == "claude":
        return ["claude", "--plugin-dir", str(ROOT / "plugins" / "myway"),
                "--resume", session, "-p", prompt, "--output-format", "stream-json", "--verbose"]
    raise ValueError("unsupported platform")


def artifacts(workdir):
    found = []
    for current, dirs, files in os.walk(workdir, followlinks=False):
        current = Path(current)
        if current == workdir:
            dirs[:] = [name for name in dirs if name not in {".agents", ".grok"}]
        for name in list(dirs) + files:
            path = current / name
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                found.append(path.relative_to(workdir).as_posix())
                if name in dirs:
                    dirs.remove(name)
            elif path.is_file():
                found.append(path.relative_to(workdir).as_posix())
    return sorted(found)


def skill_snapshot(workdir):
    """Hash the installed skill trees so modifications cannot be mistaken for no artifacts."""
    result = {}
    for directory in (workdir / ".agents", workdir / ".grok"):
        if directory.is_symlink() or (hasattr(directory, "is_junction") and directory.is_junction()):
            result[directory.name] = "linked-root"
            continue
        if not directory.exists():
            continue
        for current, dirs, files in os.walk(directory, followlinks=False):
            current = Path(current)
            for name in sorted(dirs + files):
                path = current / name
                key = path.relative_to(workdir).as_posix()
                if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                    result[key] = "link:" + os.readlink(path)
                    if name in dirs:
                        dirs.remove(name)
                elif path.is_file():
                    digest = hashlib.sha256()
                    with path.open("rb") as source:
                        for block in iter(lambda: source.read(65536), b""):
                            digest.update(block)
                    result[key] = digest.hexdigest()
                elif path.is_dir():
                    result[key] = "directory"
    return result


def validate_dialogue(doc, cases):
    if type(doc) is not dict or set(doc) != {"schema_version", "cases"} or type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
        raise ValueError("invalid dialogue schema")
    if type(doc["cases"]) is not list or not doc["cases"]:
        raise ValueError("missing dialogue cases")
    known = {case["id"]: case for case in cases}
    result = {}
    for item in doc["cases"]:
        if type(item) is not dict or set(item) != {"id", "followup", "artifact_policy"}:
            raise ValueError("invalid dialogue case")
        ident, followup = item["id"], item["followup"]
        if not isinstance(ident, str) or ident not in known or ident in result or not known[ident].get("requires_followup"):
            raise ValueError("invalid dialogue id")
        if item["artifact_policy"] != "forbidden" or type(followup) is not dict:
            raise ValueError("invalid dialogue policy")
        allowed = {"request", "required", "forbidden", "max_chars", "forbid_unprovided_advisories"}
        if set(followup) != allowed or type(followup["request"]) is not str or len(followup["request"].strip()) < 10:
            raise ValueError("invalid followup")
        if type(followup["max_chars"]) is not int or followup["max_chars"] <= 0 or type(followup["forbid_unprovided_advisories"]) is not bool:
            raise ValueError("invalid followup constraints")
        for name in ("required", "forbidden"):
            entries = followup[name]
            if type(entries) is not list or any(not ((type(x) is str and x) or
                    (type(x) is list and x and all(type(y) is str and y for y in x))) for x in entries):
                raise ValueError("invalid followup checks")
        if not followup["required"]:
            raise ValueError("followup requires a content check")
        # Apply the same sensitive-data checks as an ordinary case request.
        trial = {"schema_version": 2, "cases": [dict(case) for case in cases]}
        next(case for case in trial["cases"] if case["id"] == ident)["request"] = followup["request"]
        if simulate_eval.validate(trial):
            raise ValueError("invalid or sensitive followup request")
        result[ident] = item
    return result


def execute(command, workdir, timeout, platform, skill):
    started = time.monotonic()
    try:
        result = process_control.run(command, cwd=str(workdir), stdin=subprocess.DEVNULL,
                                     capture_output=True, text=True, encoding="utf-8",
                                     errors="replace", timeout=timeout)
        raw = result.stdout or ""
        observed = (run_eval.codex_jsonl_observation(raw) if platform == "codex" else
                    run_eval.claude_jsonl_observation(raw, skill))
        failed = result.returncode != 0 or observed.get("result_error", False)
        return {"status": "execution_failed" if failed else "completed", "exit_code": result.returncode,
                "seconds": round(time.monotonic() - started, 3), "raw": raw,
                "output": observed["final_text"], "trace": observed["trace"],
                "stderr_tail": (result.stderr or "")[-500:]}
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return {"status": "timeout", "exit_code": None, "seconds": round(time.monotonic() - started, 3),
                "raw": raw, "output": "", "trace": {"status": "unverified"}, "stderr_tail": "timeout"}
    except OSError as exc:
        return {"status": "execution_failed", "exit_code": None, "seconds": round(time.monotonic() - started, 3),
                "raw": "", "output": "", "trace": {"status": "unverified"}, "stderr_tail": str(exc)[-500:]}


def auto_check(output, case):
    checks = run_eval.evaluate_output(output, case)
    passed = (checks["nonempty"] and checks["has_content_checks"] and not checks["missing_required"]
              and not checks["forbidden_found"] and checks["within_limit"] and checks["ends_with_ok"]
              and not checks["unexpected_advisory_count"])
    return checks, bool(passed)


def main(argv=None):
    parser = argparse.ArgumentParser(description="같은 세션에서 2턴을 실행하고 자동 검사를 기록")
    parser.add_argument("--platform", choices=("codex", "claude"), required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--cases", default=str(simulate_eval.DEFAULT_CASES))
    parser.add_argument("--dialogues", default=str(DEFAULT_DIALOGUES))
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-calls", type=int, required=True)
    parser.add_argument("--max-seconds", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    if min(args.max_calls, args.max_seconds, args.timeout) <= 0:
        parser.error("budgets and timeout must be positive")
    try:
        cases = simulate_eval.load_cases(args.cases)
        if simulate_eval.validate(cases):
            raise ValueError("invalid cases")
        dialogue = validate_dialogue(simulate_eval.load_cases(args.dialogues), cases["cases"])[args.case]
        case = next(case for case in cases["cases"] if case["id"] == args.case)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        print(f"invalid inputs or output directory: {exc}", file=sys.stderr)
        return 1
    started = time.monotonic()
    deadline = started + args.max_seconds
    workdir = None
    summary = {"schema_version": 1, "case": case["id"], "platform": args.platform,
               "max_calls": args.max_calls, "max_seconds": args.max_seconds, "attempted_calls": 0,
               "input_manifest": simulate_eval.manifest({"cases": [case]})["cases"][0],
               "followup_request_sha256": hashlib.sha256(dialogue["followup"]["request"].encode("utf-8")).hexdigest(),
               "dialogue_contract_sha256": hashlib.sha256(json.dumps(dialogue, ensure_ascii=False, sort_keys=True,
                                                                       separators=(",", ":")).encode("utf-8")).hexdigest(),
               "turns": [], "followup_status": "NOT VERIFIED", "semantic_quality": "NOT VERIFIED",
               "note": "Automatic checks and local file snapshots do not establish semantic correctness or OS isolation."}
    try:
        workdir = run_eval.prepare_workdir(args.platform)
        original_skills = skill_snapshot(workdir)
        session = None
        for index in range(2):
            remaining = deadline - time.monotonic()
            if summary["attempted_calls"] >= args.max_calls or remaining <= 0 or (index and not session):
                summary["turns"].extend({"status": "not_run", "reason": "budget_or_session"}
                                        for _ in range(index, 2))
                break
            request = case if index == 0 else dialogue["followup"]
            command = (run_eval.platform_command(args.platform, run_eval.build_prompt(case, platform=args.platform))
                       if index == 0 else resume_command(args.platform, session, request["request"]))
            summary["attempted_calls"] += 1
            result = execute(command, workdir, min(args.timeout, remaining), args.platform, case["skill"])
            raw, output = result.pop("raw"), result.pop("output")
            observed_session = session_id(raw, args.platform)
            checks, passed = auto_check(output, request) if result["status"] == "completed" else (None, False)
            result["checks"] = checks
            result["passed_auto_checks"] = passed
            result["session_status"] = ("matched" if index and observed_session and observed_session == session else
                                        "identified" if not index and observed_session else "unverified")
            result["local_artifacts"] = artifacts(workdir)
            result["skill_tree_changed"] = skill_snapshot(workdir) != original_skills
            stem = f"turn-{index + 1}"
            (out / f"{stem}.jsonl").write_text(raw, encoding="utf-8")
            (out / f"{stem}.md").write_text(output + "\n", encoding="utf-8")
            result["trace_file"] = f"{stem}.jsonl"
            result["output_file"] = f"{stem}.md"
            summary["turns"].append(result)
            if index == 0:
                if result["status"] == "completed" and (not passed or result["local_artifacts"] or result["skill_tree_changed"]):
                    summary["followup_status"] = "AUTO FAIL"
                skill_loaded = (result["trace"].get("status") == "loaded"
                                and case["skill"] in result["trace"].get("skills", []))
                session = (observed_session if result["status"] == "completed" and passed and skill_loaded
                           and not result["local_artifacts"] and not result["skill_tree_changed"] else None)
            elif result["status"] == "completed" and result["session_status"] == "matched":
                if not passed or result["local_artifacts"] or result["skill_tree_changed"]:
                    summary["followup_status"] = "AUTO FAIL"
                elif (summary["turns"][0]["trace"].get("status") == "loaded"
                      and case["skill"] in summary["turns"][0]["trace"].get("skills", [])):
                    summary["followup_status"] = "AUTO PASS"
    finally:
        if workdir is not None:
            shutil.rmtree(workdir, ignore_errors=True)
        summary["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["followup_status"] == "AUTO PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

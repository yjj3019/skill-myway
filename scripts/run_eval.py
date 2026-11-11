#!/usr/bin/env python3
"""가상 케이스로 실제 모델 CLI를 실행하고 자동 검사를 기록한다.

사용: python3 scripts/run_eval.py [--platform claude|codex|grok] [--only ITEM ...]
        [--auto-select | --cases FILE] [--out DIR] [--timeout SEC] [--dry-run]
        실제 실행은 --max-calls N 또는 --max-seconds N 중 하나 이상 필수

- 기본은 Claude Code를 `--plugin-dir`로 띄워 스킬 지침을 로드한다.
- 각 케이스의 출력에서 필수 문자열·금지 패턴·최대 길이를 검사한다.
- 이 자동 검사는 형식·필수 요소 확인이며 문장 품질·사실 정확성을 판정하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import simulate_eval  # noqa: E402
import check_office  # noqa: E402

DEFAULT_CASES = simulate_eval.DEFAULT_CASES
DEFAULT_AUTO_CASES = ROOT / "tests" / "eval_cases" / "auto_select_cases.json"
DEFAULT_OUT = ROOT / "eval-results"


def build_prompt(case, auto_select=False, platform=None):
    if auto_select:
        return (
            "다음은 사용자의 요청이다. 사용 가능한 지침 중 필요한 것을 스스로 판단해 적용하고 작업을 수행해. "
            "특정 스킬 이름을 지정하지 않는다. 요청이 파일 산출물을 요구하면 현재 작업 디렉터리 안에만 저장하고, 저장소나 그 밖의 경로는 수정하지 마.\n\n"
            f"{case['request']}"
        )
    skill = case["skill"]
    if platform == "claude":
        instruction = f"Use the Skill tool to load myway:{skill} before answering."
    elif platform in ("codex", "grok"):
        directory = ".agents" if platform == "codex" else ".grok"
        instruction = f"먼저 {directory}/skills/{skill}/SKILL.md를 읽고 해당 지침을 적용해."
    else:
        instruction = f"다음 작업에 '{skill}' 스킬 지침을 적용해 수행해."
    return (
        instruction + "\n"
        "파일을 만들거나 저장소를 수정하지 말고, 요청한 결과만 출력해.\n\n"
        f"{case['request']}"
    )

def skill_load_evidence(jsonl_text, skill):
    """Return load evidence only from tool/file events that name the skill's SKILL.md path.

    The model's own statement is never accepted as evidence.
    """
    if not jsonl_text.strip():
        return {"status": "unverified", "reason": "no event output"}
    needle = f"{skill}/SKILL.md"
    matches = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = str(event.get("type", "")).lower()
        if kind in {"agent_message", "message", "assistant_message"}:
            continue
        if needle in json.dumps(event, ensure_ascii=False):
            matches.append(kind or "unknown")
    if matches:
        return {"status": "loaded", "event_types": sorted(set(matches))}
    return {"status": "unverified", "reason": "no tool/file event referenced the skill file"}


def cli_usage(event, platform_name):
    """Preserve only counters reported by the CLI; absent values stay unknown."""
    values = event.get("usage")
    if not isinstance(values, dict):
        return None
    def counter(key):
        value = values.get(key)
        return value if type(value) is int and value >= 0 else None
    cost = event.get("total_cost_usd") if platform_name == "claude" else None
    if type(cost) not in (int, float) or cost < 0 or (type(cost) is float and not math.isfinite(cost)):
        cost = None
    model_usage = event.get("modelUsage") if platform_name == "claude" else None
    models = sorted(key for key in model_usage if isinstance(key, str) and key) if isinstance(model_usage, dict) else None
    return {"source": "cli_event", "input_tokens": counter("input_tokens"),
            "output_tokens": counter("output_tokens"),
            "cache_read_tokens": counter("cache_read_input_tokens" if platform_name == "claude" else "cached_input_tokens"),
            "cache_write_tokens": counter("cache_creation_input_tokens" if platform_name == "claude" else "cache_write_input_tokens"),
            "reasoning_output_tokens": counter("reasoning_output_tokens") if platform_name == "codex" else None,
            "cli_reported_cost_usd": cost, "models": models}


def codex_jsonl_observation(jsonl_text):
    """Parse documented Codex JSONL items into final assistant text and load evidence."""
    messages = []
    event_types = []
    usage = None
    for line in jsonl_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        kind = str(event.get("type", "")).lower()
        event_types.append(kind or "unknown")
        if kind == "turn.completed":
            usage = cli_usage(event, "codex")
        item = event.get("item")
        if isinstance(item, dict) and str(item.get("type", "")).lower() == "agent_message":
            text = item.get("text")
            if isinstance(text, str):
                messages.append(text)
        elif kind in {"agent_message", "message", "assistant_message"} and isinstance(event.get("text"), str):
            messages.append(event["text"])
    final_text = messages[-1] if messages else ""
    trace = skill_load_any_evidence(jsonl_text)
    trace["event_types"] = event_types
    return {"final_text": final_text, "trace": trace, "usage": usage}


def claude_jsonl_observation(jsonl_text, skill):
    """Require a successful Skill tool result and the exact local skill body."""
    events = []
    for line in jsonl_text.splitlines():
        try:
            events.append(json.loads(line))
        except (ValueError, TypeError):
            continue
    pending = set()
    succeeded = False
    loaded = False
    final_text = ""
    result_error = False
    usage = None
    event_types = []
    skill_path = simulate_eval.SKILLS / skill / "SKILL.md"
    skill_body = skill_path.read_text(encoding="utf-8").split("---", 2)[-1].strip()
    for event in events:
        if not isinstance(event, dict):
            continue
        event_types.append(event.get("type", "unknown"))
        message = event.get("message", {})
        content = message.get("content", []) if isinstance(message, dict) else []
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if (event.get("type") == "assistant" and item.get("type") == "tool_use"
                        and item.get("name") == "Skill" and isinstance(item.get("input"), dict)
                        and item["input"].get("skill") == f"myway:{skill}" and item.get("id")):
                    pending.add(item["id"])
                elif (event.get("type") == "user" and item.get("type") == "tool_result"
                      and item.get("tool_use_id") in pending and not item.get("is_error") and item.get("content")):
                    succeeded = True
                elif (event.get("type") == "user" and item.get("type") == "text" and succeeded
                      and isinstance(item.get("text"), str) and skill_body and skill_body in item["text"]):
                    loaded = True
                elif event.get("type") == "assistant" and item.get("type") == "text":
                    final_text = item.get("text", "")
        if event.get("type") == "result":
            result_error = event.get("is_error") is True
            usage = cli_usage(event, "claude")
            if isinstance(event.get("result"), str):
                final_text = event["result"]
    trace = {"status": "loaded" if loaded else "unverified",
             "reason": "successful Skill call and matching local body" if loaded else "no successful Skill call with matching local body",
             "skills": [skill] if loaded else [], "event_types": event_types}
    return {"final_text": final_text, "trace": trace, "result_error": result_error, "usage": usage}


def skill_load_any_evidence(jsonl_text):
    """Find successful file-read tool events that return a skill file body."""
    if not jsonl_text.strip():
        return {"status": "unverified", "reason": "no event output"}
    skills = {p.name: (p / "SKILL.md").read_text(encoding="utf-8").strip()
              for p in simulate_eval.SKILLS.iterdir() if (p / "SKILL.md").is_file()}
    loaded = set()
    for line in jsonl_text.splitlines():
        if not line.strip().startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") not in {"tool_call", "command_execution"}:
            continue
        if item.get("exit_code") not in (None, 0) or item.get("status") in ("failed", "error") or item.get("is_error"):
            continue
        if item.get("type") == "command_execution" and (item.get("exit_code") != 0 or item.get("status") != "completed"):
            continue
        payload = json.dumps(item, ensure_ascii=False).replace("\\\\", "/").replace("\\", "/")
        output = " ".join(str(item.get(key, "")) for key in ("text", "output", "stdout", "content", "aggregated_output"))
        output = output.replace("\r\n", "\n")
        combined = payload + " " + output
        for skill, body in skills.items():
            needle = f"{skill}/SKILL.md"
            if needle in combined and body and body.replace("\r\n", "\n") in output:
                loaded.add(skill)
    if loaded:
        return {"status": "loaded", "skills": sorted(loaded), "evidence": "successful tool read with matching local skill content"}
    return {"status": "unverified", "reason": "Codex JSONL had no completed read-like tool event with skill path and content"}


def platform_command(platform, prompt):
    if platform == "claude":
        return ["claude", "--plugin-dir", str(ROOT / "plugins" / "myway"), "-p", prompt,
                "--output-format", "stream-json", "--verbose"]
    if platform == "codex":
        # 임시 작업 디렉터리의 스킬 사본만 읽고 쓸 수 있게 제한한다.
        return ["codex", "exec", "--json", "--sandbox", "workspace-write", "--skip-git-repo-check", prompt]
    if platform == "grok":
        # prepare_workdir creates this isolated directory and copies only our skills.
        # Grok 1.0.77 otherwise omits project skills in an untrusted directory.
        return ["grok", "-p", prompt, "--trust"]
    raise ValueError(f"지원하지 않는 플랫폼: {platform}")


def requirement_met(requirement, lowered):
    if isinstance(requirement, str):
        return requirement.lower() in lowered
    if isinstance(requirement, (list, tuple)):
        return any(str(alt).lower() in lowered for alt in requirement)
    return False


def evaluate_output(output, case):
    lowered = output.lower()
    missing = [item for item in case.get("required", []) if not requirement_met(item, lowered)]
    forbidden = [item for item in case.get("forbidden", []) if requirement_met(item, lowered)]
    max_chars = case.get("max_chars", 8000)
    return {
        "missing_required": missing,
        "forbidden_found": forbidden,
        "chars": len(output),
        "nonempty": bool(output.strip()),
        "has_content_checks": bool(case.get("required") or case.get("ends_with")),
        "ends_with_ok": output.rstrip().endswith(case["ends_with"]) if "ends_with" in case else True,
        "within_limit": len(output) <= max_chars,
    }


def prepare_workdir(platform):
    """평가용 임시 작업 디렉터리를 만든다.

    Claude는 `--plugin-dir`로 스킬을 읽으므로 빈 디렉터리를 쓴다.
    Codex·Grok은 프로젝트 스킬 경로에서 읽으므로 해당 경로에 스킬 사본을 만든다.
    """
    workdir = Path(tempfile.mkdtemp(prefix="myway-eval-"))
    if platform in ("codex", "grok"):
        base = workdir / (".agents/skills" if platform == "codex" else ".grok/skills")
        base.mkdir(parents=True)
        for skill in simulate_eval.SKILLS.iterdir():
            if (skill / "SKILL.md").is_file():
                shutil.copytree(skill, base / skill.name, ignore=shutil.ignore_patterns("__pycache__"))
    return workdir


def capture_artifacts(workdir, artifact_dir):
    """Copy regular model-created files from the isolated run, excluding installed skill trees."""
    ignored_roots = {".agents", ".grok"}
    files = []
    total_bytes = 0
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    if artifact_dir.exists() or artifact_dir.is_symlink():
        raise OSError(f"artifact directory already exists: {artifact_dir}")
    stage = Path(tempfile.mkdtemp(prefix=".artifact-", dir=artifact_dir.parent))
    try:
        for current, dirnames, filenames in os.walk(workdir, followlinks=False):
            dirnames.sort()
            filenames.sort()
            current_path = Path(current)
            rel_dir = current_path.relative_to(workdir)
            dirnames[:] = [name for name in dirnames
                           if not (rel_dir == Path(".") and name in ignored_roots)
                           and name != "__pycache__"
                           and not (current_path / name).is_symlink()]
            for name in filenames:
                source = current_path / name
                if source.is_symlink() or not source.is_file():
                    continue
                resolved = source.resolve()
                if not resolved.is_relative_to(workdir.resolve()):
                    raise OSError(f"artifact path escaped work directory: {source}")
                size = source.stat().st_size
                if len(files) >= 50 or total_bytes + size > 100 * 1024 * 1024:
                    raise OSError("artifact capture limit exceeded (50 files or 100 MiB)")
                relative = source.relative_to(workdir)
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.open("rb") as input_file, destination.open("xb") as output_file:
                    shutil.copyfileobj(input_file, output_file)
                digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                files.append({"path": relative.as_posix(), "bytes": size, "sha256": digest})
                total_bytes += size
        if files:
            stage.rename(artifact_dir)
        elif artifact_dir.parent.exists() and not any(artifact_dir.parent.iterdir()):
            stage.rmdir()
            try:
                artifact_dir.parent.rmdir()
            except OSError:
                pass
        else:
            stage.rmdir()
        return files
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        if artifact_dir.parent.exists() and not any(artifact_dir.parent.iterdir()):
            try:
                artifact_dir.parent.rmdir()
            except OSError:
                pass
        raise


def validate_auto_cases(document):
    """공개 자동 선택 케이스를 정답 스킬 필드 없이 검증한다."""
    if not isinstance(document, dict) or set(document) != {"schema_version", "cases"} or document.get("schema_version") != 1:
        return ["schema_version 1과 cases만 포함된 문서가 필요합니다"]
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        return ["cases 배열이 비어 있습니다"]
    errors = []
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            errors.append("케이스 항목이 객체가 아닙니다")
            continue
        case_id = case.get("id")
        request = case.get("request")
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", case_id):
            errors.append("id는 영문·숫자·하이픈·밑줄 1~100자여야 합니다")
        elif case_id in seen:
            errors.append(f"{case_id}: id가 중복됩니다")
        else:
            seen.add(case_id)
        if set(case) not in ({"id", "request", "artifact_policy"},
                             {"id", "request", "artifact_policy", "expected_extensions"}):
            errors.append(f"{case_id}: 공개 케이스에 허용되지 않은 필드가 있습니다")
        if not isinstance(case.get("artifact_policy"), str) or case["artifact_policy"] not in {"required", "forbidden", "conditional"}:
            errors.append(f"{case_id}: artifact_policy가 잘못됐습니다")
        extensions = case.get("expected_extensions")
        if extensions is not None and (not isinstance(extensions, list) or not extensions
                                       or any(not isinstance(ext, str) or not re.fullmatch(r"\.[a-z0-9]{1,8}", ext)
                                              for ext in extensions)):
            errors.append(f"{case_id}: expected_extensions가 잘못됐습니다")
        if case.get("artifact_policy") == "required" and not extensions:
            errors.append(f"{case_id}: required 케이스에는 expected_extensions가 필요합니다")
        if not isinstance(request, str) or len(request.strip()) < 10:
            errors.append(f"{case_id}: request가 너무 짧습니다")
            continue
        for kind, pattern in simulate_eval.validate_repo.SENSITIVE:
            for match in pattern.finditer(request):
                value = match.group(0)
                if kind == "ipv4" and (simulate_eval.validate_repo.SAFE_IP.match(value)
                                        or any(int(part) > 255 for part in value.split("."))):
                    continue
                if kind == "email" and simulate_eval.validate_repo.SAFE_EMAIL.search(value):
                    continue
                errors.append(f"{case_id}: 민감 패턴({kind}) 의심")
                break
    return errors


def cli_identity(platform):
    command = {"claude": "claude", "codex": "codex", "grok": "grok"}[platform]
    executable = shutil.which(command)
    if not executable:
        return {"name": command, "available": False, "version": None, "sha256": None}
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=10)
        identity = {"name": command, "available": True, "path": str(Path(executable).resolve()),
                    "version": (result.stdout.strip() or result.stderr.strip())[:500],
                    "version_exit_code": result.returncode,
                    "sha256_status": "pending"}
        if Path(executable).is_file() and Path(executable).stat().st_size <= 100 * 1024 * 1024:
            try:
                identity["sha256"] = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
                identity["sha256_status"] = "computed"
            except OSError as exc:
                identity["sha256"] = None
                identity["sha256_status"] = f"unavailable: {exc}"
        else:
            identity["sha256"] = None
            identity["sha256_status"] = "missing_or_over_100mib"
        return identity
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": command, "available": True, "path": str(executable),
                "version": None, "sha256": None, "identity_error": str(exc)}


def auto_manifest(cases):
    return {
        "schema_version": 1,
        "mode": "auto_select",
        "environment": {"python": sys.version.split()[0], "os": platform.platform()},
        "runtime": {"cli": cli_identity("codex"),
                    "selection_trace": "not_available",
                    "selection_status": "unverified"},
        "sandbox": {"platform": "codex", "mode": "workspace-write", "network_isolation": "unverified"},
        "skill_files": {
            path.relative_to(simulate_eval.SKILLS).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(simulate_eval.SKILLS.rglob("*"))
            if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts
        },
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "case_file_sha256": hashlib.sha256(DEFAULT_AUTO_CASES.read_bytes()).hexdigest(),
        "cases": [{
            "id": case["id"],
            "request_sha256": hashlib.sha256(case["request"].encode("utf-8")).hexdigest(),
            "artifact_policy": case["artifact_policy"],
            "expected_extensions": case.get("expected_extensions", []),
            "max_chars": 8000,
            "expected_result": "file" if case["artifact_policy"] == "required" else "no_file" if case["artifact_policy"] == "forbidden" else "review",
        } for case in cases],
    }


def claude_usage_limit(text):
    """관찰된 Claude CLI 한도 메시지 한 줄만 인식한다. 일반 답변의 인용은 제외한다."""
    return bool(re.fullmatch(r"You've hit your (?:\d+-hour )?limit\s*[·-]\s*resets [^\r\n]+", text.strip(), re.IGNORECASE))


def run_case(case, platform, timeout, auto_select=False, artifact_dir=None, timeout_artifact_dir=None, deadline=None):
    prompt = build_prompt(case, auto_select=auto_select, platform=platform)
    command = platform_command(platform, prompt)
    started = time.time()
    workdir = prepare_workdir(platform)
    try:
        if deadline is not None:
            time_left = deadline - time.monotonic()
            if time_left <= 0:
                return {"not_started": True}
            timeout = min(timeout, time_left)
        # 빈 임시 디렉터리에서 실행해 저장소 지침·훅·미커밋 변경이 평가에 섞이지 않게 한다.
        result = subprocess.run(
            command,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        raw_events = result.stdout if platform in ("codex", "claude") else ""
        event_types = []
        trace = {"status": "unverified", "reason": "trace unavailable"}
        output = result.stdout.strip()
        provider_error = False
        usage = None
        if platform == "codex" and result.stdout.lstrip().startswith("{"):
            observed = codex_jsonl_observation(result.stdout)
            output = observed["final_text"].strip()
            trace = observed["trace"]
            event_types = trace.get("event_types", [])
            usage = observed.get("usage")
        elif platform == "claude" and result.stdout.lstrip().startswith("{"):
            observed = claude_jsonl_observation(result.stdout, case["skill"])
            output = observed["final_text"].strip()
            trace = observed["trace"]
            event_types = trace.get("event_types", [])
            provider_error = observed.get("result_error", False)
            usage = observed.get("usage")
        # 오류 종료의 진단에만 적용한다. 정상 응답은 동일 문구를 인용할 수 있다.
        limit_line = next((line.strip() for line in (output + "\n" + result.stderr).splitlines()
                           if claude_usage_limit(line)), None) if platform == "claude" and (result.returncode != 0 or provider_error) else None
        artifacts = []
        artifact_error = None
        office_inspection = []
        if artifact_dir:
            try:
                artifacts = capture_artifacts(workdir, artifact_dir)
                office_inspection = check_office.inspect_office_artifacts(workdir, artifacts)
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                artifact_error = str(exc)
        exit_code = result.returncode if not artifact_error and not provider_error else (result.returncode or 1)
        return {
            "exit_code": exit_code,
            "output": output,
            "raw_events": raw_events,
            "selection_trace": trace,
            "event_types": event_types,
            "usage": usage,
            "stderr_tail": (result.stderr.strip() + (f"\n산출물 보존 실패: {artifact_error}" if artifact_error else ""))[-500:],
            "usage_limit": bool(limit_line),
            "usage_limit_message": limit_line,
            "artifacts": artifacts,
            "office_inspection": office_inspection,
            "artifact_error": artifact_error,
            "seconds": round(time.time() - started, 1),
        }
    except OSError as exc:
        return {
            "exit_code": None,
            "output": "",
            "raw_events": "",
            "selection_trace": {"status": "unverified", "reason": f"process could not start: {exc}"},
            "event_types": [],
            "usage": None,
            "stderr_tail": f"실행 실패: {exc}",
            "artifact_error": None,
            "artifacts": [],
            "office_inspection": [],
            "seconds": round(time.time() - started, 1),
        }
    except subprocess.TimeoutExpired as exc:
        def partial_text(value):
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")

        raw_output = partial_text(exc.stdout)
        observed = (codex_jsonl_observation(raw_output) if platform == "codex" else
                    claude_jsonl_observation(raw_output, case["skill"]) if platform == "claude" else None)
        artifacts = []
        artifact_error = None
        if artifact_dir or timeout_artifact_dir:
            try:
                artifacts = capture_artifacts(workdir, artifact_dir or timeout_artifact_dir)
            except (OSError, ValueError, zipfile.BadZipFile) as capture_exc:
                artifact_error = str(capture_exc)
        return {
            "exit_code": None,
            "output": observed["final_text"].strip() if observed else raw_output,
            "raw_events": raw_output if platform in ("codex", "claude") else "",
            "selection_trace": observed["trace"] if observed else {"status": "unverified", "reason": "process timed out before trace completion"},
            "event_types": observed["trace"].get("event_types", []) if observed else [],
            "usage": observed.get("usage") if observed else None,
            "stderr_tail": (f"timeout after {timeout}s\n" + partial_text(exc.stderr))[-500:],
            "artifact_error": artifact_error,
            "artifacts": artifacts,
            "office_inspection": [],
            "seconds": round(time.time() - started, 1),
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def output_stem(case_id):
    # 짧은 일반 ID는 유지하고 특수·긴 ID는 길이가 일정한 다이제스트로 표현한다.
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    if len(case_id) <= 100 and re.fullmatch(r"[A-Za-z0-9_-]+", case_id) and case_id.upper() not in reserved:
        return case_id
    return "encoded-" + hashlib.sha256(case_id.encode("utf-8")).hexdigest()


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="가상 케이스로 실제 모델을 실행하고 검사한다")
    parser.add_argument("--cases", help="일반 평가 케이스 파일")
    parser.add_argument("--auto-select", action="store_true", help="스킬명을 지정하지 않는 공개 자동 선택 사례 실행")
    parser.add_argument("--platform", choices=["claude", "codex", "grok"], default="claude")
    parser.add_argument("--only", nargs="+", help="일반 모드에서는 스킬, 자동 선택 모드에서는 케이스 ID")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--repeat", type=int, default=1, help="케이스별 반복 실행 횟수")
    parser.add_argument("--max-calls", type=int, help="전체 모델 호출 상한(시간 상한과 함께 지정 가능)")
    parser.add_argument("--max-seconds", type=int, help="호출 시작 및 프로세스 timeout 예산(호출 상한과 함께 지정 가능)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--inspect-artifacts", action="store_true",
                         help="일반 타깃 평가에서 저장소 밖에 보존한 파일을 Office 구조·보안 검사")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.repeat <= 0:
        parser.error("--timeout과 --repeat는 양수여야 합니다")
    if args.max_calls is not None and args.max_calls <= 0:
        parser.error("--max-calls는 양수여야 합니다")
    if args.max_seconds is not None and args.max_seconds <= 0:
        parser.error("--max-seconds는 양수여야 합니다")
    if not args.dry_run and args.max_calls is None and args.max_seconds is None:
        parser.error("실제 평가 실행에는 --max-calls 또는 --max-seconds 예산이 필요합니다")

    if args.auto_select and args.inspect_artifacts:
        parser.error("--inspect-artifacts는 일반 --cases 모드에서만 사용할 수 있습니다")
    if args.inspect_artifacts and args.platform == "claude":
        parser.error("Claude 플러그인 디렉터리는 작업 폴더 밖이므로 artifact 검사 모드를 지원하지 않습니다")
    if args.inspect_artifacts and not args.cases:
        parser.error("--inspect-artifacts는 명시적 --cases 입력이 필요합니다")
    if args.auto_select and args.cases:
        parser.error("--auto-select는 --cases와 함께 사용할 수 없습니다")
    if args.auto_select and args.platform != "codex":
        parser.error("--auto-select는 현재 Codex 전용 작업공간과 workspace-write가 필요합니다")
    auto_select = args.auto_select
    cases_path = DEFAULT_AUTO_CASES if auto_select else (args.cases or DEFAULT_CASES)
    try:
        document = simulate_eval.load_cases(cases_path)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    if auto_select:
        errors = validate_auto_cases(document)
    else:
        errors = simulate_eval.validate(document)
    if errors:
        print(f"케이스 검증 실패 {len(errors)}건")
        for error in errors:
            print(" -", error)
        return 1
    cases = document["cases"]
    if args.auto_select and args.only:
        if not args.only:
            parser.error("--only에는 자동 선택 케이스 ID가 하나 이상 필요합니다")
        valid_ids = {case["id"] for case in cases}
        unknown_ids = set(args.only) - valid_ids
        if unknown_ids:
            print("오류: 알 수 없는 자동 선택 케이스 ID: " + ", ".join(sorted(unknown_ids)), file=sys.stderr)
            return 1
        cases = [case for case in cases if case["id"] in args.only]
    elif args.only:
        cases = [c for c in cases if c["skill"] in args.only]
        if not cases:
            print("실행할 케이스가 없습니다")
            return 1

    if args.dry_run:
        for case in cases:
            command = platform_command(args.platform, build_prompt(case, auto_select=auto_select, platform=args.platform))
            print(f"[dry-run] {case['id']} <- {command[:2]}")
        print(f"케이스 {len(cases)}건 (모델 호출 없음)")
        return 0

    out_dir = Path(args.out)
    repeats = max(1, args.repeat)
    filenames = [f"{output_stem(case['id'])}{f'-r{i + 1}' if repeats > 1 else ''}.md"
                 for case in cases for i in range(repeats)]
    trace_filenames = [name[:-3] + ".trace.jsonl" for name in filenames] if args.platform in ("codex", "claude") else []
    artifact_paths = [out_dir / "artifacts" / f"{output_stem(case['id'])}-r{index + 1}"
                      for case in cases for index in range(repeats)]
    if len({str(path).casefold() for path in artifact_paths}) != len(artifact_paths):
        print("오류: 산출물 경로가 충돌합니다", file=sys.stderr)
        return 1
    if len({name.casefold() for name in filenames}) != len(filenames):
        print("오류: 케이스 결과 파일명이 충돌합니다", file=sys.stderr)
        return 1
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        if any((out_dir / name).exists() or (out_dir / name).is_symlink()
               for name in [*filenames, *trace_filenames, "summary.json"]) or any(
                   path.exists() or path.is_symlink() for path in artifact_paths):
            print("오류: 결과 파일이 이미 있습니다. 빈 출력 디렉터리를 사용하세요", file=sys.stderr)
            return 1
        input_manifest = auto_manifest(cases) if auto_select else simulate_eval.manifest({"cases": cases})
    except OSError as exc:
        print(f"오류: 결과 준비 실패: {exc}", file=sys.stderr)
        return 1
    summary = []
    failed = 0
    stop_reason = None
    started = time.monotonic()
    attempted_calls = 0
    for case in cases:
        label = case.get("skill", "auto-select")
        print(f"실행: {case['id']} ({label}) x{repeats}")
        runs = []
        for index in range(repeats):
            if not stop_reason and args.max_calls is not None and attempted_calls >= args.max_calls:
                stop_reason = "max_calls"
            if not stop_reason and args.max_seconds is not None and time.monotonic() - started >= args.max_seconds:
                stop_reason = "max_seconds"
            remaining = args.timeout
            if not stop_reason and args.max_seconds is not None:
                budget_left = args.max_seconds - (time.monotonic() - started)
                if budget_left <= 0:
                    stop_reason = "max_seconds"
                else:
                    remaining = min(remaining, budget_left)
            if stop_reason:
                runs.append({"status": "not_run", "exit_code": None, "seconds": None,
                             "checks": None, "passed_auto_checks": None, "stderr_tail": "",
                             "usage": None,
                             "selection_status": "unverified" if auto_select else None,
                             "artifacts": [], "artifact_error": None})
                continue
            artifact_dir = (out_dir / "artifacts" / f"{output_stem(case['id'])}-r{index + 1}"
                            if auto_select or args.inspect_artifacts else None)
            artifacts_preexisting = bool(artifact_dir and (artifact_dir.exists() or artifact_dir.is_symlink()))
            attempted_calls += 1
            run = run_case(case, args.platform, remaining, auto_select=auto_select,
                           artifact_dir=artifact_dir,
                           timeout_artifact_dir=out_dir / "artifacts" / f"{output_stem(case['id'])}-r{index + 1}",
                           deadline=started + args.max_seconds if args.max_seconds is not None else None)
            if run.get("not_started"):
                attempted_calls -= 1
                stop_reason = "max_seconds"
                runs.append({"status": "not_run", "exit_code": None, "seconds": None,
                             "checks": None, "passed_auto_checks": None, "stderr_tail": "",
                             "usage": None,
                             "selection_status": "unverified" if auto_select else None,
                             "artifacts": [], "artifact_error": None})
                continue
            limited = bool(run.get("usage_limit", False)) or (args.platform == "claude" and run["exit_code"] != 0 and any(
                claude_usage_limit(line) for line in (run["output"] + "\n" + run["stderr_tail"]).splitlines()))
            if limited:
                stop_reason = "claude_usage_limit"
            checks = evaluate_output(run["output"], case) if run["exit_code"] == 0 and not limited else None
            passed = bool(checks and checks["nonempty"] and not checks["missing_required"]
                          and not checks["forbidden_found"] and checks["within_limit"] and checks["ends_with_ok"])
            artifact_expectation = None
            office_inspection = []
            if auto_select or args.inspect_artifacts:
                if artifacts_preexisting:
                    run["artifact_error"] = "artifact destination existed before this run"
                    run["exit_code"] = run.get("exit_code") or 1
                office_inspection = run.get("office_inspection", [])
                expected_office_files = [artifact for artifact in run.get("artifacts", [])
                                         if Path(artifact["path"]).suffix.lower() in {".pptx", ".docx", ".xlsx"}]
                if expected_office_files and len(office_inspection) != len(expected_office_files):
                    run["artifact_error"] = "Office artifact inspection count mismatch"
                    run["exit_code"] = run.get("exit_code") or 1
                bad_office_files = [item for item in office_inspection if item.get("status") != "PASS"]
                unverified_calculations = [item for item in office_inspection
                                           if item.get("calculation_status") == "NOT VERIFIED"
                                           or item.get("missing_formula_caches")]
                failed_calculations = [item for item in office_inspection
                                       if item.get("calculation_status") == "FAIL"
                                       or item.get("cached_formula_errors")]
                run["office_calculation_unverified"] = unverified_calculations
                run["office_calculation_failures"] = failed_calculations
                run["office_calculation_passes"] = [item for item in office_inspection
                                                    if item.get("calculation_status") == "PASS"]
                if bad_office_files:
                    run["artifact_error"] = "Office artifact structure/security inspection failed"
                    run["office_inspection_error"] = bad_office_files
                    run["exit_code"] = run.get("exit_code") or 1
                if failed_calculations:
                    run["artifact_error"] = "Office formula cached error detected"
                    run["office_calculation_failures"] = failed_calculations
                    run["exit_code"] = run.get("exit_code") or 1
                if auto_select:
                    has_artifact = bool(run.get("artifacts"))
                    policy = case["artifact_policy"]
                    extensions = [Path(item["path"]).suffix.lower() for item in run.get("artifacts", [])]
                    expected_extensions = [ext.lower() for ext in case.get("expected_extensions", [])]
                    artifact_expectation = (
                        policy == "conditional" or
                        (policy == "required" and has_artifact
                         and all(any(ext == expected for ext in extensions) for expected in expected_extensions)) or
                        (policy == "forbidden" and not has_artifact)
                    )
                    if not artifact_expectation or run.get("artifact_error"):
                        passed = False
                elif run.get("artifact_error"):
                    passed = False
            if passed and not auto_select and not checks["has_content_checks"]:
                passed = None
            suffix = f"-r{index + 1}" if repeats > 1 else ""
            try:
                with (out_dir / f"{output_stem(case['id'])}{suffix}.md").open("x", encoding="utf-8") as output_file:
                    output_file.write(run["output"] + "\n")
                trace_filename = None
                trace_hash = None
                if args.platform in ("codex", "claude") and run.get("raw_events"):
                    trace_filename = f"{output_stem(case['id'])}{suffix}.trace.jsonl"
                    trace_bytes = run["raw_events"].encode("utf-8")
                    with (out_dir / trace_filename).open("xb") as trace_file:
                        trace_file.write(trace_bytes)
                    trace_hash = hashlib.sha256(trace_bytes).hexdigest()
            except OSError as exc:
                print(f"오류: 결과 저장 실패: {exc}", file=sys.stderr)
                return 1
            artifact_error = run.get("artifact_error")
            runs.append({
                "status": "execution_failed" if run["exit_code"] != 0 or limited or artifact_error else "completed",
                "selection_status": "unverified" if auto_select else None,
                "load_trace_status": (run.get("selection_trace", {}).get("status", "unverified")
                                      if args.platform in ("codex", "claude") else None),
                "load_trace_reason": (run.get("selection_trace", {}).get("reason")
                                      if args.platform in ("codex", "claude") else None),
                "event_types": (run.get("event_types", []) if args.platform in ("codex", "claude") else []),
                "usage": run.get("usage"),
                "observed_skill_reads": run.get("selection_trace", {}).get("skills", []),
                "trace_file": trace_filename,
                "trace_sha256": trace_hash,
                "trace_status": (run.get("selection_trace", {}).get("status") if auto_select else None),
                "artifact_expectation_met": artifact_expectation if auto_select else None,
                "artifact_count": len(run.get("artifacts", [])),
                "office_inspection": office_inspection if (auto_select or args.inspect_artifacts) else [],
                "office_inspection_error": run.get("office_inspection_error"),
                "office_inspection_requested": bool(auto_select or args.inspect_artifacts),
                "office_calculation_unverified": run.get("office_calculation_unverified", []),
                "office_calculation_failures": run.get("office_calculation_failures", []),
                "office_calculation_passes": run.get("office_calculation_passes", []),
                "office_calculation_status": (
                    "FAIL" if run.get("office_calculation_failures") else
                    "NOT VERIFIED" if run.get("office_calculation_unverified") else
                    "PASS" if run.get("office_calculation_passes") else
                    "NOT APPLICABLE" if auto_select or args.inspect_artifacts else None
                ),
                "office_inspection_status": (
                    "FAIL" if (any(item.get("status") == "FAIL" for item in office_inspection)
                                or bool(run.get("office_calculation_failures")))
                    else "NOT VERIFIED" if (any(item.get("status") == "NOT VERIFIED" for item in office_inspection)
                                             or bool(run.get("office_calculation_unverified")))
                    else "PASS" if office_inspection and all(item.get("status") == "PASS" for item in office_inspection)
                    else "NOT APPLICABLE" if not (auto_select or args.inspect_artifacts) else None
                ),
                "usage_limit_message": run.get("usage_limit_message"),
                "artifacts": run.get("artifacts", []),
                "actual_artifacts": run.get("artifacts", []),
                "artifact_error": run.get("artifact_error"),
                "exit_code": run["exit_code"],
                "seconds": run["seconds"],
                "checks": checks,
                "passed_auto_checks": passed,
                "semantic_quality": "NOT VERIFIED",
                "stderr_tail": run["stderr_tail"] if run["exit_code"] != 0 or artifact_error else "",
            })
            verdict = "PASS" if passed is True else "NOT VERIFIED" if passed is None else "FAIL"
            print(f"  r{index + 1}: {verdict} exit={run['exit_code']} "
                  f"{run['seconds']}s checks={checks}")
        passed_count = sum(1 for run in runs if run["passed_auto_checks"])
        not_run = sum(run["status"] == "not_run" for run in runs)
        case_passed = None if any(run["passed_auto_checks"] is None for run in runs) else passed_count == repeats
        if case_passed is not True:
            failed += 1
        summary.append({
            "id": case["id"],
            "skill": case.get("skill"),
            "mode": "auto_select" if auto_select else "targeted",
            "repeats": repeats,
            "attempted": sum(run["status"] != "not_run" for run in runs),
            "completed": sum(run["status"] == "completed" for run in runs),
            "execution_failed": sum(run["status"] == "execution_failed" for run in runs),
            "not_run": sum(run["status"] == "not_run" for run in runs),
            "passed_count": passed_count,
            "pass_rate": round(passed_count / repeats, 2) if case_passed is not None else None,
            "passed": case_passed,
            "runs": runs,
        })

    summary_doc = {
        "schema_version": 3,
        "mode": "auto_select" if auto_select else "targeted",
        "inspect_artifacts": args.inspect_artifacts,
        "platform": args.platform,
        "repeat": repeats,
        "timeout": args.timeout,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "stop_reason": stop_reason,
        "budget": {"max_calls": args.max_calls, "max_seconds": args.max_seconds,
                   "attempted_calls": attempted_calls,
                   "elapsed_seconds": round(time.monotonic() - started, 1)},
        "input_manifest": input_manifest,
        "cases": summary,
        "note": "자동 검사는 형식·필수 요소만 본다. 문장 품질과 사실 정확성은 사람이 판정해야 한다.",
    }
    try:
        with (out_dir / "summary.json").open("x", encoding="utf-8") as summary_file:
            summary_file.write(json.dumps(summary_doc, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        print(f"오류: 요약 저장 실패: {exc}", file=sys.stderr)
        return 1
    total = len(cases) * repeats
    passed = sum(item["passed_count"] for item in summary)
    attempted = sum(item["attempted"] for item in summary)
    print(f"\n결과: 예정 {total}, 시도 {attempted}, 미실행 {total - attempted}, 자동 검사 통과 {passed}. 저장: {out_dir}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

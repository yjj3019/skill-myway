#!/usr/bin/env python3
"""가상 케이스로 실제 모델 CLI를 실행하고 자동 검사를 기록한다.

사용: python3 scripts/run_eval.py [--platform claude|codex|grok] [--only SKILL ...]
        [--cases FILE] [--out DIR] [--timeout SEC] [--dry-run]

- 기본은 Claude Code를 `--plugin-dir`로 띄워 스킬 지침을 로드한다.
- 각 케이스의 출력에서 필수 문자열·금지 패턴·최대 길이를 검사한다.
- 이 자동 검사는 형식·필수 요소 확인이며 문장 품질·사실 정확성을 판정하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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

DEFAULT_CASES = simulate_eval.DEFAULT_CASES
DEFAULT_OUT = ROOT / "eval-results"


def build_prompt(case):
    return (
        f"다음 작업에 '{case['skill']}' 스킬 지침을 적용해 수행해.\n"
        "파일을 만들거나 저장소를 수정하지 말고, 요청한 결과만 출력해.\n\n"
        f"{case['request']}"
    )


def platform_command(platform, prompt):
    if platform == "claude":
        return ["claude", "--plugin-dir", str(ROOT / "plugins" / "myway"), "-p", prompt]
    if platform == "codex":
        # 평가용 임시 디렉터리의 스킬 파일을 읽을 수 있도록 샌드박스를 열어 실행한다.
        return ["codex", "exec", "--sandbox", "danger-full-access", "--skip-git-repo-check", prompt]
    if platform == "grok":
        return ["grok", "-p", prompt]
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


def claude_usage_limit(text):
    """관찰된 Claude CLI 한도 메시지 한 줄만 인식한다. 일반 답변의 인용은 제외한다."""
    return bool(re.fullmatch(r"You've hit your (?:\d+-hour )?limit\s*[·-]\s*resets [^\r\n]+", text.strip(), re.IGNORECASE))


def run_case(case, platform, timeout):
    prompt = build_prompt(case)
    command = platform_command(platform, prompt)
    started = time.time()
    workdir = prepare_workdir(platform)
    try:
        # 빈 임시 디렉터리에서 실행해 저장소 지침·훅·미커밋 변경이 평가에 섞이지 않게 한다.
        result = subprocess.run(
            command,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        output = result.stdout.strip()
        # 오류 종료의 진단에만 적용한다. 정상 응답은 동일 문구를 인용할 수 있다.
        limit_line = next((line.strip() for line in (result.stdout + "\n" + result.stderr).splitlines()
                           if claude_usage_limit(line)), None) if platform == "claude" and result.returncode != 0 else None
        return {
            "exit_code": result.returncode,
            "output": output,
            "stderr_tail": result.stderr.strip()[-500:],
            "usage_limit": bool(limit_line),
            "usage_limit_message": limit_line,
            "seconds": round(time.time() - started, 1),
        }
    except OSError as exc:
        return {
            "exit_code": None,
            "output": "",
            "stderr_tail": f"실행 실패: {exc}",
            "seconds": round(time.time() - started, 1),
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": None,
            "output": "",
            "stderr_tail": f"timeout after {timeout}s",
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
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--platform", choices=["claude", "codex", "grok"], default="claude")
    parser.add_argument("--only", nargs="*", help="이 스킬만 실행")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--repeat", type=int, default=1, help="케이스별 반복 실행 횟수")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        document = simulate_eval.load_cases(args.cases)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    errors = simulate_eval.validate(document)
    if errors:
        print(f"케이스 검증 실패 {len(errors)}건")
        for error in errors:
            print(" -", error)
        return 1
    cases = document["cases"]
    if args.only:
        cases = [c for c in cases if c["skill"] in args.only]
        if not cases:
            print("실행할 케이스가 없습니다")
            return 1

    if args.dry_run:
        for case in cases:
            print(f"[dry-run] {case['id']} <- {platform_command(args.platform, build_prompt(case))[:2]}")
        print(f"케이스 {len(cases)}건 (모델 호출 없음)")
        return 0

    out_dir = Path(args.out)
    repeats = max(1, args.repeat)
    filenames = [f"{output_stem(case['id'])}{f'-r{i + 1}' if repeats > 1 else ''}.md"
                 for case in cases for i in range(repeats)]
    if len({name.casefold() for name in filenames}) != len(filenames):
        print("오류: 케이스 결과 파일명이 충돌합니다", file=sys.stderr)
        return 1
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        if any((out_dir / name).exists() or (out_dir / name).is_symlink()
               for name in [*filenames, "summary.json"]):
            print("오류: 결과 파일이 이미 있습니다. 빈 출력 디렉터리를 사용하세요", file=sys.stderr)
            return 1
        input_manifest = simulate_eval.manifest({"cases": cases})
    except OSError as exc:
        print(f"오류: 결과 준비 실패: {exc}", file=sys.stderr)
        return 1
    summary = []
    failed = 0
    stop_reason = None
    for case in cases:
        print(f"실행: {case['id']} ({case['skill']}) x{repeats}")
        runs = []
        for index in range(repeats):
            if stop_reason:
                runs.append({"status": "not_run", "exit_code": None, "seconds": None,
                             "checks": None, "passed_auto_checks": None, "stderr_tail": ""})
                continue
            run = run_case(case, args.platform, args.timeout)
            limited = bool(run.get("usage_limit", False)) or (args.platform == "claude" and run["exit_code"] != 0 and any(
                claude_usage_limit(line) for line in (run["output"] + "\n" + run["stderr_tail"]).splitlines()))
            if limited:
                stop_reason = "claude_usage_limit"
            checks = evaluate_output(run["output"], case) if run["exit_code"] == 0 and not limited else None
            passed = bool(checks and checks["nonempty"] and not checks["missing_required"]
                          and not checks["forbidden_found"] and checks["within_limit"] and checks["ends_with_ok"])
            suffix = f"-r{index + 1}" if repeats > 1 else ""
            try:
                with (out_dir / f"{output_stem(case['id'])}{suffix}.md").open("x", encoding="utf-8") as output_file:
                    output_file.write(run["output"] + "\n")
            except OSError as exc:
                print(f"오류: 결과 저장 실패: {exc}", file=sys.stderr)
                return 1
            runs.append({
                "status": "execution_failed" if run["exit_code"] != 0 or limited else "completed",
                "usage_limit_message": run.get("usage_limit_message"),
                "exit_code": run["exit_code"],
                "seconds": run["seconds"],
                "checks": checks,
                "passed_auto_checks": passed,
                "stderr_tail": run["stderr_tail"] if run["exit_code"] != 0 else "",
            })
            print(f"  r{index + 1}: {'PASS' if passed else 'FAIL'} exit={run['exit_code']} "
                  f"{run['seconds']}s checks={checks}")
        passed_count = sum(1 for run in runs if run["passed_auto_checks"])
        not_run = sum(run["status"] == "not_run" for run in runs)
        case_passed = None if not_run else passed_count == repeats
        if case_passed is not True:
            failed += 1
        summary.append({
            "id": case["id"],
            "skill": case["skill"],
            "repeats": repeats,
            "attempted": sum(run["status"] != "not_run" for run in runs),
            "completed": sum(run["status"] == "completed" for run in runs),
            "execution_failed": sum(run["status"] == "execution_failed" for run in runs),
            "not_run": sum(run["status"] == "not_run" for run in runs),
            "passed_count": passed_count,
            "pass_rate": round(passed_count / repeats, 2) if not not_run else None,
            "passed": case_passed,
            "runs": runs,
        })

    summary_doc = {
        "schema_version": 3,
        "platform": args.platform,
        "repeat": repeats,
        "timeout": args.timeout,
        "stop_reason": stop_reason,
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

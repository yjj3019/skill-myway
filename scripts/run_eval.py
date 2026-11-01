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
import json
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
    forbidden = [item for item in case.get("forbidden", []) if item.lower() in lowered]
    max_chars = case.get("max_chars", 8000)
    return {
        "missing_required": missing,
        "forbidden_found": forbidden,
        "chars": len(output),
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
        return {
            "exit_code": result.returncode,
            "output": output,
            "stderr_tail": result.stderr.strip()[-500:],
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
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    failed = 0
    repeats = max(1, args.repeat)
    for case in cases:
        print(f"실행: {case['id']} ({case['skill']}) x{repeats}")
        runs = []
        for index in range(repeats):
            run = run_case(case, args.platform, args.timeout)
            checks = evaluate_output(run["output"], case)
            passed = run["exit_code"] == 0 and not checks["missing_required"] and not checks["forbidden_found"] and checks["within_limit"]
            suffix = f"-r{index + 1}" if repeats > 1 else ""
            (out_dir / f"{case['id']}{suffix}.md").write_text(run["output"] + "\n", encoding="utf-8")
            runs.append({
                "exit_code": run["exit_code"],
                "seconds": run["seconds"],
                "checks": checks,
                "passed_auto_checks": passed,
                "stderr_tail": run["stderr_tail"] if run["exit_code"] != 0 else "",
            })
            print(f"  r{index + 1}: {'PASS' if passed else 'FAIL'} exit={run['exit_code']} "
                  f"{run['seconds']}s chars={checks['chars']} missing={checks['missing_required']} forbidden={checks['forbidden_found']}")
        passed_count = sum(1 for run in runs if run["passed_auto_checks"])
        case_passed = passed_count == repeats
        if not case_passed:
            failed += 1
        summary.append({
            "id": case["id"],
            "skill": case["skill"],
            "repeats": repeats,
            "passed_count": passed_count,
            "pass_rate": round(passed_count / repeats, 2),
            "passed": case_passed,
            "runs": runs,
        })

    summary_doc = {
        "schema_version": 2,
        "platform": args.platform,
        "repeat": repeats,
        "cases": summary,
        "note": "자동 검사는 형식·필수 요소만 본다. 문장 품질과 사실 정확성은 사람이 판정해야 한다.",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = len(cases) * repeats
    passed = sum(item["passed_count"] for item in summary)
    print(f"\n결과: {passed}/{total} 자동 검사 통과, 케이스 {len(cases) - failed}/{len(cases)} 전부 통과. 저장: {out_dir}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

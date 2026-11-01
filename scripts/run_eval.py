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
        return ["codex", "exec", "--skip-git-repo-check", prompt]
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


def run_case(case, platform, timeout):
    prompt = build_prompt(case)
    command = platform_command(platform, prompt)
    started = time.time()
    try:
        # 빈 임시 디렉터리에서 실행해 저장소 지침·훅·미커밋 변경이 평가에 섞이지 않게 한다.
        with tempfile.TemporaryDirectory(prefix="myway-eval-") as workdir:
            result = subprocess.run(
                command,
                cwd=workdir,
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


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="가상 케이스로 실제 모델을 실행하고 검사한다")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--platform", choices=["claude", "codex", "grok"], default="claude")
    parser.add_argument("--only", nargs="*", help="이 스킬만 실행")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--timeout", type=int, default=300)
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
    for case in cases:
        print(f"실행: {case['id']} ({case['skill']})")
        run = run_case(case, args.platform, args.timeout)
        checks = evaluate_output(run["output"], case)
        passed = run["exit_code"] == 0 and not checks["missing_required"] and not checks["forbidden_found"] and checks["within_limit"]
        if not passed:
            failed += 1
        (out_dir / f"{case['id']}.md").write_text(run["output"] + "\n", encoding="utf-8")
        summary.append({
            "id": case["id"],
            "skill": case["skill"],
            "exit_code": run["exit_code"],
            "seconds": run["seconds"],
            "checks": checks,
            "passed_auto_checks": passed,
            "stderr_tail": run["stderr_tail"] if run["exit_code"] != 0 else "",
        })
        state = "PASS" if passed else "FAIL"
        print(f"  {state} exit={run['exit_code']} {run['seconds']}s chars={checks['chars']} "
              f"missing={checks['missing_required']} forbidden={checks['forbidden_found']}")

    summary_doc = {
        "schema_version": 1,
        "platform": args.platform,
        "cases": summary,
        "note": "자동 검사는 형식·필수 요소만 본다. 문장 품질과 사실 정확성은 사람이 판정해야 한다.",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n결과: {len(cases) - failed}/{len(cases)} 자동 검사 통과. 저장: {out_dir}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

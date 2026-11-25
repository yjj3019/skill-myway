#!/usr/bin/env python3
"""스킬 자연어 기동 점검과 스킬 유무 쌍 비교.

요청에 스킬 이름을 쓰지 않고 실행해 어떤 스킬이 실제로 로드됐는지를 이벤트 로그에서 확인한다.
기동 판정은 로그 근거만 쓰며 응답 품질을 판정하지 않는다. 결과 비교의 PASS는 자동 문자열 검사일 뿐이다.

사용:
  python scripts/activation_check.py --platform claude --arm with    --out DIR --max-calls 18
  python scripts/activation_check.py --platform claude --arm without --out DIR2 --max-calls 12
  python scripts/activation_check.py --compare DIR/summary.json DIR2/summary.json
  python scripts/activation_check.py --platform codex --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import process_control  # noqa: E402
import run_eval  # noqa: E402
import simulate_eval  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = ROOT / "tests" / "eval_cases" / "activation_cases.json"
MAX_BYTES = 4 * 1024 * 1024

ACTIVATION_STATUSES = ("ACTIVATED", "ACTIVATED_WITH_EXTRA", "WRONG_SKILL", "MISSED",
                       "FALSE_POSITIVE", "CORRECT_NONE", "UNVERIFIED")
OUTCOME_STATUSES = ("DISCRIMINATING", "NON_DISCRIMINATING", "SKILL_HURTS", "BOTH_FAIL", "UNVERIFIED")


def load_cases(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = data["cases"]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("케이스 id 중복")
    known = set(simulate_eval.skill_names())
    for case in cases:
        expected = case.get("expected_skill")
        if expected is not None and expected not in known:
            raise ValueError(f"{case['id']}: 알 수 없는 스킬 {expected}")
        if not case.get("request"):
            raise ValueError(f"{case['id']}: 요청 없음")
        for name in known:
            if name in case["request"]:
                raise ValueError(f"{case['id']}: 요청에 스킬 이름 '{name}'이 있다(자연어 기동 점검 위반)")
    covered = {case["expected_skill"] for case in cases if case.get("expected_skill")}
    if covered != known:
        raise ValueError(f"스킬 커버리지 불일치: 누락 {sorted(known - covered)}")
    return cases


def loaded_skills(platform, stdout):
    """이벤트 로그에서 로드가 확인된 스킬 집합과 로그 관측 가능 여부를 반환한다."""
    if platform == "codex":
        observed = run_eval.codex_jsonl_observation(stdout)
        trace = observed["trace"]
        skills = set(trace.get("skills", [])) if trace.get("status") == "loaded" else set()
    elif platform == "claude":
        observed = run_eval.claude_jsonl_observation(stdout, simulate_eval.skill_names()[0])
        skills = set()
        for name in simulate_eval.skill_names():
            trace = run_eval.claude_jsonl_observation(stdout, name)["trace"]
            if trace.get("status") == "loaded":
                skills.add(name)
    else:
        raise ValueError(f"지원하지 않는 플랫폼: {platform}")
    return {"skills": skills, "final_text": observed["final_text"].strip(),
            "observable": bool(observed["trace"].get("event_types")),
            "provider_error": bool(observed.get("result_error")),
            "permission_denials": observed.get("permission_denials", [])}


def classify_activation(expected, observation):
    """기대 스킬과 관측된 로드 집합으로 기동 상태를 분류한다."""
    if not observation["observable"] or observation["provider_error"] or not observation["final_text"]:
        return "UNVERIFIED"
    skills = observation["skills"]
    if expected is None:
        return "FALSE_POSITIVE" if skills else "CORRECT_NONE"
    if expected in skills:
        return "ACTIVATED" if skills == {expected} else "ACTIVATED_WITH_EXTRA"
    return "WRONG_SKILL" if skills else "MISSED"


def classify_outcome(with_row, without_row):
    """같은 케이스의 스킬 사용·미사용 자동 검사 결과를 쌍으로 분류한다. 품질 판정이 아니다."""
    a, b = with_row.get("auto_pass"), without_row.get("auto_pass")
    if a is None or b is None:
        return "UNVERIFIED"
    if a and b:
        return "NON_DISCRIMINATING"
    if a and not b:
        return "DISCRIMINATING"
    if b and not a:
        return "SKILL_HURTS"
    return "BOTH_FAIL"


def summarize_rows(rows):
    counts = {status: sum(1 for row in rows if row.get("activation") == status) for status in ACTIVATION_STATUSES}
    positives = [row for row in rows if row.get("expected_skill")]
    negatives = [row for row in rows if not row.get("expected_skill")]
    hit = sum(1 for row in positives if row.get("activation") in ("ACTIVATED", "ACTIVATED_WITH_EXTRA"))
    clean = sum(1 for row in negatives if row.get("activation") == "CORRECT_NONE")
    return {"counts": counts,
            "positive_total": len(positives), "positive_activated": hit,
            "negative_total": len(negatives), "negative_clean": clean}


def compare(with_summary, without_summary):
    """두 summary.json의 케이스별 결과 차이를 분류한다."""
    without_by_id = {row["id"]: row for row in without_summary["rows"]}
    rows = []
    for row in with_summary["rows"]:
        other = without_by_id.get(row["id"])
        if other is None or not row.get("expected_skill"):
            continue
        rows.append({"id": row["id"], "skill": row["expected_skill"],
                     "with": row.get("auto_pass"), "without": other.get("auto_pass"),
                     "activation": row.get("activation"),
                     "outcome": classify_outcome(row, other)})
    counts = {status: sum(1 for row in rows if row["outcome"] == status) for status in OUTCOME_STATUSES}
    return {"rows": rows, "counts": counts}


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def isolated_claude_command(command):
    """스킬 폴더 읽기만 추가로 허용한다(쓰기·실행·MCP 권한은 늘리지 않는다)."""
    plugin_dir = str(ROOT / "plugins" / "myway")
    return [command[0], "--add-dir", plugin_dir] + command[1:]


def run_one(case, platform, timeout, isolated=False):
    """한 케이스를 실제로 실행한다. 요청은 스킬 이름 없이 그대로 전달한다.

    isolated는 Claude 전용이다. 작업 폴더를 저장소 밖 시스템 임시 폴더에 만들어 저장소의 CLAUDE.md가
    응답에 섞이지 않게 하고, 스킬의 references 읽기 거부를 줄인다.
    """
    prompt = case["request"]
    command = run_eval.platform_command(platform, prompt)
    if isolated:
        command = isolated_claude_command(command)
    environment = run_eval.evaluation_environment(platform)
    if environment is not None:
        command[0] = shutil.which(command[0]) or command[0]
    if isolated:
        import tempfile
        workdir = Path(tempfile.mkdtemp(prefix="myway-act-"))
    else:
        workdir = run_eval.prepare_workdir(platform)
    started = time.perf_counter()
    try:
        try:
            result = process_control.run(command, cwd=str(workdir), stdin=subprocess.DEVNULL,
                                         capture_output=True, text=True, encoding="utf-8",
                                         errors="replace", timeout=timeout, env=environment)
        except subprocess.TimeoutExpired as exc:
            return {"status": "timeout", "stdout": exc.output or "", "returncode": None,
                    "seconds": round(time.perf_counter() - started, 1)}
        return {"status": "completed", "stdout": result.stdout, "returncode": result.returncode,
                "seconds": round(time.perf_counter() - started, 1)}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def judge_run(case, platform, run, arm):
    """실행 결과를 기동 상태와 자동 검사 결과로 변환한다."""
    row = {"id": case["id"], "expected_skill": case.get("expected_skill"), "status": run["status"],
           "seconds": run["seconds"], "returncode": run["returncode"], "arm": arm}
    if run["status"] != "completed":
        return {**row, "activation": "UNVERIFIED", "auto_pass": None, "loaded": [], "final_text": ""}
    observation = loaded_skills(platform, run["stdout"])
    text = observation["final_text"]
    auto_pass = None
    if text and not observation["provider_error"] and not observation["permission_denials"]:
        auto_pass = run_eval.auto_checks_passed(run_eval.evaluate_output(text, case))
    activation = classify_activation(case.get("expected_skill"), observation) if arm == "with" else "UNVERIFIED"
    return {**row, "activation": activation, "auto_pass": auto_pass,
            "loaded": sorted(observation["skills"]), "final_text": text}


def write_results(out_dir, platform, arm, cases_path, rows, runs, isolated=False):
    out = Path(out_dir)
    for row in rows:
        (out / f"{row['id']}.md").write_text(row["final_text"] + "\n", encoding="utf-8")
        (out / f"{row['id']}.trace.jsonl").write_text(runs[row["id"]]["stdout"], encoding="utf-8")
    stored = [{k: v for k, v in row.items() if k != "final_text"} for row in rows]
    summary = {"schema_version": 1, "platform": platform, "arm": arm, "isolated": isolated,
               "cases_sha256": file_sha256(cases_path), "tool_sha256": file_sha256(__file__),
               "cli": run_eval.cli_identity(platform), "rows": stored,
               "aggregate": summarize_rows(stored) if arm == "with" else None,
               "notice": "기동 판정은 이벤트 로그 근거다. 자동 검사 PASS는 응답 품질을 뜻하지 않으며 의미 품질은 NOT VERIFIED다."}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def print_summary(summary):
    for row in summary["rows"]:
        print(f"{row['activation']:<22} auto={row['auto_pass']!s:<5} loaded={row['loaded']} {row['id']}")
    if summary.get("aggregate"):
        agg = summary["aggregate"]
        print(f"기동 {agg['positive_activated']}/{agg['positive_total']}, "
              f"부정 사례 무기동 {agg['negative_clean']}/{agg['negative_total']}")
    print("주의: 기동은 로그 근거, auto는 문자열 검사다. 응답 품질은 NOT VERIFIED.", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description="스킬 자연어 기동 점검(모델 호출은 --dry-run이 아닐 때만)")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--platform", choices=["claude", "codex"])
    parser.add_argument("--arm", choices=["with", "without"], default="with")
    parser.add_argument("--only", nargs="+", help="케이스 id 또는 기대 스킬")
    parser.add_argument("--out")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-calls", type=int)
    parser.add_argument("--max-seconds", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--isolated", action="store_true",
                        help="Claude 전용: 작업 폴더를 저장소 밖에 만들고 스킬 폴더 읽기를 허용")
    parser.add_argument("--compare", nargs=2, metavar=("WITH_SUMMARY", "WITHOUT_SUMMARY"))
    args = parser.parse_args(argv)

    if args.compare:
        try:
            a = json.loads(Path(args.compare[0]).read_text(encoding="utf-8"))
            b = json.loads(Path(args.compare[1]).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            print(f"오류: {error}", file=sys.stderr)
            return 2
        if a.get("arm") != "with" or b.get("arm") != "without" or a.get("platform") != b.get("platform") \
                or a.get("cases_sha256") != b.get("cases_sha256"):
            print("오류: 비교는 같은 플랫폼·같은 케이스 파일의 with/without 결과만 허용한다", file=sys.stderr)
            return 2
        result = compare(a, b)
        for row in result["rows"]:
            print(f"{row['outcome']:<19} with={row['with']!s:<5} without={row['without']!s:<5} {row['id']}")
        print("집계: " + ", ".join(f"{k}={v}" for k, v in result["counts"].items()))
        print("주의: 자동 검사의 쌍 비교다. 의미 품질은 블라인드 리뷰 전까지 NOT VERIFIED다.", file=sys.stderr)
        return 0

    if not args.platform:
        parser.error("--platform 필요")
    if args.isolated and args.platform != "claude":
        parser.error("--isolated는 claude에서만 쓸 수 있다")
    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError, KeyError) as error:
        print(f"오류: 케이스 파일: {error}", file=sys.stderr)
        return 2
    if args.only:
        cases = [c for c in cases if c["id"] in args.only or c.get("expected_skill") in args.only]
        if not cases:
            print("오류: --only와 일치하는 케이스 없음", file=sys.stderr)
            return 2
    if args.arm == "without":
        cases = [c for c in cases if c.get("expected_skill")]
    if args.dry_run:
        for case in cases:
            print(f"[{args.platform}/{args.arm}] {case['id']} -> 기대: {case.get('expected_skill')}")
        print(f"총 {len(cases)}건, 모델 호출 없음")
        return 0
    if (args.max_calls is None) == (args.max_seconds is None) or not args.out:
        print("오류: --out과 --max-calls 또는 --max-seconds 중 정확히 하나가 필요하다", file=sys.stderr)
        return 2
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        print("오류: 결과 폴더가 비어 있지 않다", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    if args.arm == "without":
        os.environ["MYWAY_SKILLS_DISABLE"] = "1"
    elif run_eval.skills_disabled():
        print("오류: MYWAY_SKILLS_DISABLE이 켜져 있어 with 팔을 실행할 수 없다", file=sys.stderr)
        return 2

    deadline = time.monotonic() + args.max_seconds if args.max_seconds else None
    rows, runs, calls = [], {}, 0
    for case in cases:
        if args.max_calls is not None and calls >= args.max_calls:
            break
        timeout = args.timeout
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            timeout = min(timeout, left)
        calls += 1
        run = run_one(case, args.platform, timeout, args.isolated)
        runs[case["id"]] = run
        rows.append(judge_run(case, args.platform, run, args.arm))
    summary = write_results(out, args.platform, args.arm, args.cases, rows, runs, args.isolated)
    summary["not_run"] = len(cases) - len(rows)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print_summary(summary)
    if summary["not_run"]:
        print(f"예산 소진으로 미실행 {summary['not_run']}건", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

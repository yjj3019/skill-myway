#!/usr/bin/env python3
"""저장된 평가 응답에 현재 자동 검사 규칙을 다시 적용해 전후 차이를 분류한다.

모델을 호출하지 않는다. 판정 규칙(tests/eval_cases/cases.json)을 바꾼 뒤 과거 실행의
저장 응답(`<id>.md`)이 새 규칙에서 어떻게 달라지는지 확인하는 용도다. 이 결과는 자동 검사의
전후 비교일 뿐이며 응답 품질이나 사실 정확성을 판정하지 않는다. 차이는 사람이 분류한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval  # noqa: E402

MAX_BYTES = 8 * 1024 * 1024
STATUSES = ("SAME_PASS", "SAME_FAIL", "PASS_TO_FAIL", "FAIL_TO_PASS",
            "SAVED_UNCHECKED", "MISSING_OUTPUT", "CASE_REMOVED")


def read_text(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def load_cases(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["cases"] if isinstance(data, dict) else data
    return {case["id"]: case for case in items}


def replay_summary(summary_path, cases):
    """summary.json 하나의 실행별 전후 판정을 반환한다."""
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    folder = summary_path.parent
    rows = []
    for saved in summary.get("cases", []):
        case = cases.get(saved.get("id"))
        runs = saved.get("runs", [])
        for index, run in enumerate(runs, start=1):
            row = {"dir": str(folder), "case": saved.get("id"), "repeat": index,
                   "saved": run.get("passed_auto_checks")}
            if case is None:
                rows.append({**row, "now": None, "status": "CASE_REMOVED"})
                continue
            stem = run_eval.output_stem(case["id"])
            name = f"{stem}-r{index}.md" if len(runs) > 1 else f"{stem}.md"
            output = read_text(folder / name)
            if output is None:
                rows.append({**row, "now": None, "status": "MISSING_OUTPUT"})
                continue
            now = run_eval.auto_checks_passed(run_eval.evaluate_output(output, case))
            before = row["saved"]
            if before is None:
                status = "SAVED_UNCHECKED"
            elif before and now:
                status = "SAME_PASS"
            elif not before and not now:
                status = "SAME_FAIL"
            else:
                status = "PASS_TO_FAIL" if before else "FAIL_TO_PASS"
            rows.append({**row, "now": now, "status": status})
    return rows


def find_summaries(roots):
    found = []
    for root in roots:
        root = Path(root)
        if root.is_file() and root.name == "summary.json":
            found.append(root)
        elif root.is_dir():
            found.extend(sorted(p for p in root.rglob("summary.json") if not p.is_symlink()))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description="저장 응답에 현재 자동 검사를 다시 적용한다(모델 호출 없음)")
    parser.add_argument("results", nargs="+", help="summary.json 또는 이를 포함한 디렉터리")
    parser.add_argument("--cases", default=str(run_eval.ROOT / "tests" / "eval_cases" / "cases.json"))
    parser.add_argument("--json", action="store_true", help="행별 결과를 JSON으로 출력")
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"오류: 케이스 파일을 읽을 수 없습니다: {error}", file=sys.stderr)
        return 2
    summaries = find_summaries(args.results)
    if not summaries:
        print("오류: summary.json을 찾지 못했습니다", file=sys.stderr)
        return 2
    rows = []
    for path in summaries:
        try:
            rows.extend(replay_summary(path, cases))
        except (OSError, ValueError, TypeError) as error:
            print(f"오류: {path}: {error}", file=sys.stderr)
            return 2
    counts = {status: sum(1 for row in rows if row["status"] == status) for status in STATUSES}
    if args.json:
        print(json.dumps({"counts": counts, "rows": rows}, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            if row["status"] in ("PASS_TO_FAIL", "FAIL_TO_PASS", "MISSING_OUTPUT", "CASE_REMOVED"):
                print(f"{row['status']}: {row['case']} r{row['repeat']} ({row['dir']})")
        print("집계: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print("주의: 자동 검사의 전후 비교다. 차이는 응답 원문과 규칙 변경 사유를 보고 사람이 분류한다.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

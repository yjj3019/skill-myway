#!/usr/bin/env python3
"""기준선·후보 summary.json(schema_version 5) 두 개를 사례별로 대조해 한 보고서로 저장한다.

사용: python3 scripts/compare_runs_report.py --baseline BASE.json --candidate CAND.json --out DIR
  --baseline: run_eval.py가 저장한 기준선 summary.json
  --candidate: 같은 사례 파일로 실행한 후보 summary.json
  --out: compare-runs-summary.json과 compare-runs-summary.md를 저장할 디렉터리
종료 코드: 0 저장 성공, 1 입력 오류(읽기 실패·스키마 불일치·중복 키)·이미 존재하는 보고 파일·저장 실패.

자동 검사 상태(시도·완료·실패·타임아웃·미실행·자동 통과)만 대조한다.
의미 품질·독립 판정·기준선 우월성은 검증하지 않는다.

자동 통과 수는 run_eval.py가 저장한 원본 passed_count를 검증해 직접 사용한다.
반올림된 auto_check_pass_rate(repeats와 곱한 값을 다시 반올림)로 되살리지 않는다.
상태 건수의 관계를 검증하고 passed_count가 완료 건수 이하여야 집계한다.
필요한 값이 없거나 모순되면 '통과 미확인'으로 두고 합계에서 뺀다.

보고 파일 두 개는 각각 덮어쓰지 않고 게시한다. 게시는 파일 단위라서
두 파일의 동시 저장(쌍 원자성)은 보장되지 않는다. 중간 실패 시 이미 게시된
경로는 다른 작업이 교체했을 수 있으므로 삭제하지 않고 부분 저장을 보고한다.
재시도에는 빈 출력 디렉터리를 사용한다.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

import contract_json
from atomic_output import new_output

# 사례 항목에서 분모로 쓰는 정수 필드와 자동 통과 수·자동 통과율 필드.
COUNT_FIELDS = ("repeats", "attempted", "completed", "execution_failed", "timed_out", "not_run")
PASSED_COUNT = "passed_count"
RATE = "auto_check_pass_rate"
STATE_FIELDS = COUNT_FIELDS + ("auto_passed", "auto_checks_passed", RATE)


def _read(path):
    try:
        with open(path, "rb") as handle:
            data = contract_json.loads(handle.read().decode("utf-8"))
    except (OSError, UnicodeError, RecursionError, ValueError) as exc:
        raise ValueError(f"{path}: 읽을 수 없음 ({exc})")
    if type(data) is not dict or data.get("schema_version") != 5:
        raise ValueError(f"{path}: schema_version 5가 아님")
    cases = data.get("cases")
    if type(cases) is not list:
        raise ValueError(f"{path}: cases 목록 없음")
    by_id = {}
    for entry in cases:
        if type(entry) is not dict or not isinstance(entry.get("id"), str):
            raise ValueError(f"{path}: 케이스 항목에 문자열 id 없음")
        if entry["id"] in by_id:
            raise ValueError(f"{path}: 케이스 id 중복 {entry['id']}")
        by_id[entry["id"]] = entry
    return by_id


def _count(entry, field):
    value = entry.get(field)
    # bool은 int의 하위형이라 정수 검사에서 명시적으로 배제한다.
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _conflicting_total(total, parts):
    if total is None:
        return False
    known = [value for value in parts if value is not None]
    return sum(known) > total or (len(known) == len(parts) and sum(known) != total)


def _case_state(entry):
    counts = {field: _count(entry, field) for field in COUNT_FIELDS}
    issues = [field for field in COUNT_FIELDS if counts[field] is None and entry.get(field) is not None]
    outcomes = [counts[field] for field in ("completed", "execution_failed", "timed_out")]
    attempted, repeats, not_run = counts["attempted"], counts["repeats"], counts["not_run"]
    if (_conflicting_total(attempted, outcomes)
            or _conflicting_total(repeats, [attempted, not_run])
            or _conflicting_total(repeats, [*outcomes, not_run])):
        issues.append("상태 건수 합계")
        counts = dict.fromkeys(COUNT_FIELDS)

    passed = _count(entry, PASSED_COUNT)
    if None in counts.values() or passed is None or passed > counts["completed"]:
        if entry.get(PASSED_COUNT) is not None:
            issues.append(PASSED_COUNT)
        passed = None
    verdict = entry.get("auto_checks_passed")
    inconsistent_pass = verdict is True and (passed is None or not repeats or passed != repeats)
    inconsistent_fail = verdict is False and passed is not None and passed == counts["attempted"]
    if (verdict is not None and type(verdict) is not bool) or inconsistent_pass or inconsistent_fail:
        issues.append("auto_checks_passed")
        verdict = None
    rate = entry.get(RATE)
    if rate is not None and (type(rate) not in (float, int) or passed is None or not repeats
                             or rate != round(passed / repeats, 2)):
        issues.append(RATE)
        rate = None
    return {**counts, PASSED_COUNT: passed, "auto_passed": passed, RATE: rate,
            "auto_checks_passed": verdict, "input_issues": issues}


def build_rows(baseline, candidate):
    """사례 id를 기준선·후보로 짝지은 행 목록과 집계를 돌려준다."""
    ids = sorted(set(baseline) | set(candidate))
    rows = []
    for case_id in ids:
        sides = {"baseline": baseline.get(case_id), "candidate": candidate.get(case_id)}
        cells = {}
        present = []
        for side, entry in sides.items():
            if entry is None:
                cells[side] = None
                continue
            present.append(side)
            cells[side] = _case_state(entry)
        rows.append((case_id, cells, present))
    totals = {}
    for side in ("baseline", "candidate"):
        counts = Counter()
        for case_id, cells, _ in rows:
            entry = cells[side]
            if entry is None:
                continue
            for field in COUNT_FIELDS:
                if isinstance(entry[field], int):
                    counts[field] += entry[field]
                else:
                    counts[f"{field}_unknown"] += 1
            if isinstance(entry["auto_passed"], int):
                counts["auto_passed"] += entry["auto_passed"]
            else:
                counts["auto_passed_unknown"] += 1
        totals[side] = dict(counts)
        totals[side].setdefault("auto_passed", 0)
        totals[side].setdefault("auto_passed_unknown", 0)
    status = {"both": 0, "only_baseline": 0, "only_candidate": 0, "auto_state_differs": 0}
    for case_id, cells, present in rows:
        if len(present) == 2:
            status["both"] += 1
            if any(cells["baseline"][key] != cells["candidate"][key] for key in STATE_FIELDS):
                status["auto_state_differs"] += 1
        elif present == ["baseline"]:
            status["only_baseline"] += 1
        else:
            status["only_candidate"] += 1
    return rows, totals, status


def _cell(entry):
    if entry is None:
        return "-"
    parts = [f"시도 {entry['attempted']}" if entry["attempted"] is not None else "시도 ?"]
    for key, label in (("completed", "완료"), ("execution_failed", "실패"),
                     ("timed_out", "타임아웃"), ("not_run", "미실행"),
                     ("auto_passed", "자동 통과")):
        value = entry[key]
        parts.append(f"{label} {value}" if value is not None else f"{label} ?")
    verdict = {True: "PASS", False: "FAIL", None: "NOT VERIFIED"}[entry["auto_checks_passed"]]
    parts.append(f"자동 판정 {verdict}")
    if entry["input_issues"]:
        parts.append("입력 확인 필요: " + ", ".join(entry["input_issues"]))
    return " / ".join(parts)


def build_markdown(baseline_path, candidate_path, out_dir, rows, totals, status):
    lines = ["# 기준선·후보 대조 요약", ""]
    lines.append(f"- 기준선: {baseline_path}")
    lines.append(f"- 후보: {candidate_path}")
    lines.append(f"- 저장: {out_dir}")
    lines.append("- 자동 검사 상태(시도·완료·실패·타임아웃·미실행·자동 통과)만 대조한다. 의미 품질·독립 판정은 NOT VERIFIED다.")
    lines.append("")
    lines.append("| 케이스 | 기준선 | 후보 |")
    lines.append("|---|---|---|")
    for case_id, cells, _ in rows:
        lines.append(f"| {case_id} | {_cell(cells['baseline'])} | {_cell(cells['candidate'])} |")
    lines.append("")
    lines.append("## 분모")
    lines.append("")
    lines.append("| 측 | 예정 | 시도 | 완료 | 실패 | 타임아웃 | 미실행 | 자동 통과 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for side, label in (("baseline", "기준선"), ("candidate", "후보")):
        t = totals[side]
        def total_cell(field):
            value = t.get(field, 0)
            missing = t.get(f"{field}_unknown", 0)
            return f"? (확인 합계 {value}, 미확인 {missing}건)" if missing else str(value)
        lines.append(f"| {label} | " + " | ".join(total_cell(field) for field in
                     (*COUNT_FIELDS, "auto_passed")) + " |")
    unknown = {side: totals[side].get("auto_passed_unknown", 0)
               for side in ("baseline", "candidate")}
    lines.append("")
    if any(unknown.values()):
        lines.append(f"- 자동 통과 미확인 케이스(합계 제외): 기준선 {unknown['baseline']}건, "
                     f"후보 {unknown['candidate']}건")
        lines.append("")
    lines.append("## 대조 상태")
    lines.append("")
    lines.append(f"- 양쪽에 있는 케이스: {status['both']}, 기준선만: {status['only_baseline']}, "
                 f"후보만: {status['only_candidate']}, 자동 상태가 다른 케이스: {status['auto_state_differs']}")
    lines.append("")
    lines.append("자동 통과는 자동 검사 한정이며 답변의 사실성·의미 품질을 증명하지 않는다.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description="기준선·후보 summary.json 대조 보고서 저장")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out", required=True)
    parsed = parser.parse_args(args)
    out_dir = Path(parsed.out)
    try:
        baseline = _read(parsed.baseline)
        candidate = _read(parsed.candidate)
        rows, totals, status = build_rows(baseline, candidate)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    json_path = out_dir / "compare-runs-summary.json"
    md_path = out_dir / "compare-runs-summary.md"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        existing = [path for path in (json_path, md_path) if path.exists()]
    except OSError as exc:
        print(f"오류: 출력 디렉터리 준비 실패: {out_dir}: {exc}", file=sys.stderr)
        return 1
    if existing:
        print(f"오류: 이미 존재하는 보고 파일이 있어 덮어쓰지 않음: "
              f"{', '.join(path.name for path in existing)}", file=sys.stderr)
        return 1
    document = {
        "schema_version": 1,
        "baseline_path": parsed.baseline,
        "candidate_path": parsed.candidate,
        "rows": [
            {"id": case_id, "baseline": cells["baseline"], "candidate": cells["candidate"]}
            for case_id, cells, _ in rows
        ],
        "totals": totals,
        "state": status,
        "note": "자동 검사 상태만 대조한다. 의미 품질·독립 판정·기준선 우월성은 NOT VERIFIED다.",
    }
    try:
        json_bytes = __import__("json").dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        with new_output(json_path) as stream:
            stream.write(json_bytes)
        json_md = build_markdown(parsed.baseline, parsed.candidate, parsed.out,
                                 rows, totals, status).encode("utf-8")
        with new_output(md_path) as stream:
            stream.write(json_md)
    except OSError as exc:
        print(f"오류: 부분 저장 가능; 보고 경로를 삭제하지 않음: {json_path}, {md_path}. "
              "빈 출력 디렉터리에서 재시도하세요.", file=sys.stderr)
        print(f"오류: 대조 보고 저장 실패: {exc}", file=sys.stderr)
        return 1
    print(f"저장: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

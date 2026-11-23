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
passed_count가 없거나 0 이상·repeats 이하가 아니면 '통과 미확인'으로 두고 합계에서 뺀다.

보고 파일 두 개는 각각 덮어쓰지 않고 게시한다. 게시는 파일 단위라서
두 파일의 동시 저장(쌍 원자성)은 보장되지 않으며, 두 번째 게시가 실패하면
먼저 게시한 파일을 되돌린다.
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
FIELDS = COUNT_FIELDS + ("passed_count", RATE)


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
    if field == RATE:
        return value
    return value if isinstance(value, int) and value >= 0 else None


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
            cells[side] = {field: _count(entry, field) for field in FIELDS}
            repeats = _count(entry, "repeats")
            passed = _count(entry, PASSED_COUNT)
            cells[side]["auto_passed"] = None
            if isinstance(passed, int) and (not isinstance(repeats, int) or passed <= repeats):
                cells[side]["auto_passed"] = passed
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
            if cells["baseline"] != cells["candidate"]:
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
        lines.append(f"| {label} | {t.get('repeats', 0)} | {t.get('attempted', 0)} | {t.get('completed', 0)} | "
                     f"{t.get('execution_failed', 0)} | {t.get('timed_out', 0)} | {t.get('not_run', 0)} | {t.get('auto_passed', 0)} |")
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
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "compare-runs-summary.json"
    md_path = out_dir / "compare-runs-summary.md"
    existing = [path for path in (json_path, md_path) if path.exists()]
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
    published = []
    try:
        with new_output(json_path) as stream:
            stream.write(__import__("json").dumps(document, ensure_ascii=False, indent=2).encode("utf-8"))
        published.append(json_path)
        with new_output(md_path) as stream:
            stream.write(build_markdown(parsed.baseline, parsed.candidate, parsed.out,
                                       rows, totals, status).encode("utf-8"))
        published.append(md_path)
    except OSError as exc:
        for path in published:
            try:
                path.unlink(missing_ok=True)
            except OSError as cleanup_exc:
                print(f"오류: 되돌리기 실패: {path}: {cleanup_exc}", file=sys.stderr)
        print(f"오류: 대조 보고 저장 실패: {exc}", file=sys.stderr)
        return 1
    print(f"저장: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

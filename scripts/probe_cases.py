#!/usr/bin/env python3
"""평가 케이스의 자동 검사가 변별력이 있는지 모델 호출 없이 점검한다.

일을 하지 않은 퇴화 응답(요청문 그대로 되돌리기, 일반 거절 문구)이 자동 검사를 통과하는
케이스를 찾는다. 이런 케이스는 스킬이 실제로 일했는지 구분하지 못한다. 통과한 퇴화 응답은
검사가 약하다는 신호일 뿐이며 정상 응답의 품질이나 정확성을 판정하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval  # noqa: E402

FILLER = "확인하지 못했습니다. 자료가 없어 판단할 수 없습니다."
PROBES = {
    "echo": lambda case: case["request"],
    "filler": lambda case: FILLER,
}
DEFAULT_FILES = ("cases.json", "critical-regression-cases.json",
                 "critical-cases-extra.json", "duration-regression-cases.json")


def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["cases"] if isinstance(data, dict) else data
    return [case for case in items if isinstance(case, dict) and "request" in case and "id" in case]


def weak_probes(case):
    """퇴화 응답 중 모든 자동 검사를 통과하는 프로브 이름을 반환한다."""
    return sorted(name for name, make in PROBES.items()
                  if run_eval.auto_checks_passed(run_eval.evaluate_output(make(case), case)))


def scan(paths):
    """{`파일명::케이스 ID`: [프로브...]} 형태로 변별력이 약한 케이스를 반환한다."""
    found = {}
    for path in paths:
        for case in load(path):
            weak = weak_probes(case)
            if weak:
                found[f"{Path(path).name}::{case['id']}"] = weak
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description="퇴화 응답이 통과하는 평가 케이스를 찾는다(모델 호출 없음)")
    root = Path(__file__).resolve().parent.parent / "tests" / "eval_cases"
    parser.add_argument("files", nargs="*", default=[str(root / name) for name in DEFAULT_FILES])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        found = scan(args.files)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for key, probes in sorted(found.items()):
            print(f"{key}: {', '.join(probes)}")
        print(f"변별력 약한 케이스 {len(found)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""검증 실행의 재현성을 확인한다.

저장소 검사와 테스트를 모두 실행한 뒤 추적 파일이 바뀌지 않았는지 `git diff --exit-code`로
확인한다. 검증 명령이 추적 파일을 바꾸면 그 실행은 재현 가능한 기준이 아니므로 실패로 본다.
한 단계가 실패해도 나머지를 계속 실행한다(fail-fast 없음).
"""
import subprocess
import sys
from pathlib import Path

STEPS = (
    ("검사", "scripts/validate_repo.py"),
    ("테스트", "scripts/run_tests.py"),
)
DIFF_NAME = "작업 트리 변경"


def run(root):
    root = Path(root)
    failed = []
    for name, script in STEPS:
        result = subprocess.run([sys.executable, script], cwd=str(root))
        if result.returncode != 0:
            failed.append(name)
    diff = subprocess.run(["git", "diff", "--exit-code"], cwd=str(root))
    if diff.returncode != 0:
        failed.append(DIFF_NAME)
    if failed:
        print(f"재현 확인 실패: {' · '.join(failed)}")
        print("검증 실행이 추적 파일을 바꾸면 재현 가능한 기준이 아니므로 실패로 본다.")
        return 1
    print("재현 확인 통과: 검사·테스트 실행 후 추적 파일 변경 없음")
    return 0


if __name__ == "__main__":
    sys.exit(run(Path(__file__).resolve().parent.parent))

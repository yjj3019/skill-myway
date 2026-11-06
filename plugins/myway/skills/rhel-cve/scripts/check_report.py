#!/usr/bin/env python3
"""Confluence용 RHEL CVE 리포트의 구조를 검사한다. 사실·출처의 진위는 검사하지 않는다."""
import re
import sys
from pathlib import Path

SECTIONS = [
    "### 1. 취약점 개요",
    "### 2. 영향",
    "### 3. 완화 방법(Mitigation)",
    "### 4. 추가 정보",
    "### 5. 결론",
]
HEADER = ["RHEL", "Lifecycle", "Components", "Fixed Package", "RHSA", "Release Date", "비고"]
NOTICE = ("명시적으로 영향을 받지 않는다고 언급되지 않은 한, 이 목록에 있는 제품의 모든 마이너 업데이트 스트림에 "
          "포함된 기존 패키지 버전은 모두 취약한 것으로 간주해야 하며, 전체 분석이 이루어지지 않았을 수도 있습니다.")
LEGACY_NOTICE = NOTICE.replace("한, 이 목록", "한 이 목록")
TITLE = re.compile(r"^# CVE-\d{4}-\d{4,}(?:\s*[,/]\s*CVE-\d{4}-\d{4,})*\s+-\s+\S.+$")
PACKAGE_TITLE = re.compile(r"^영향을 받는 패키지 및 발행된 레드햇 보안 공지\s*\(\s*(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{2})\s*기준\s*\)$")
HTML = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^>]*)?/?>")
EPOCH = re.compile(r"(?<=[A-Za-z0-9_.+])-\d+:\d")
# EPOCH 오탐 예방: RHSA-2023:4201의 "-2023:4"와 CVSS:3.x/ 벡터는 epoch가 아니다.
_EPOCH_MASK = re.compile(r"RH[SBE]A-\d{4}:\d+|CVSS:3\.\d/", re.IGNORECASE)
SEPARATOR = re.compile(r"^:?-{3,}:?$")


def _epoch_free(line):
    return not EPOCH.search(_EPOCH_MASK.sub("", line))


def cells(line):
    return [value.strip() for value in line.strip().strip("|").split("|")]


def check(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    # references/report-example.md처럼 마커 줄(<!-- REPORT START -->)이 있으면 그 아래만 검사한다.
    # 마커가 없으면 전체를 검사한다(단위 테스트·실제 리포트 호환).
    marker = "\n<!-- REPORT START -->\n"
    raw = text.split(marker, 1)[1].splitlines() if marker in text else text.splitlines()
    lines, fenced = [], False
    for line in raw:
        if line.strip().startswith("```"):
            fenced = not fenced
            lines.append("")
        else:
            lines.append("" if fenced else line.strip())
    errors = []
    first = next((line for line in lines if line), "")
    if not TITLE.fullmatch(first):
        errors.append("제목은 CVE ID 목록과 한국어 설명을 포함해야 함")
    if [line for line in lines if line.startswith("### ")] != SECTIONS:
        errors.append("1~5장 제목 또는 순서 불일치")
    if any(line.startswith("## ") or line.startswith("#### ") for line in lines):
        errors.append("허용되지 않은 섹션 제목")

    def unique_index(predicate, name):
        found = [i for i, line in enumerate(lines) if predicate(line)]
        if len(found) != 1:
            errors.append(f"{name}: 정확히 한 번 필요")
            return None
        return found[0]

    grade = unique_index(lambda line: line == "보안등급", "보안등급")
    environment = unique_index(lambda line: line == "Environment", "Environment")
    package = unique_index(lambda line: bool(PACKAGE_TITLE.fullmatch(line)), "패키지 제목")
    sources = unique_index(lambda line: line == "참고문서", "참고문서")
    section_indices = [next((i for i, line in enumerate(lines) if line == heading), None) for heading in SECTIONS]
    order = [grade, environment, *section_indices, package, sources]
    if all(i is not None for i in order) and order != sorted(order):
        errors.append("보안등급, Environment, 1~5장, 패키지 표, 참고문서 순서 불일치")
    for index, name in ((environment, "Environment"), (package, "패키지 제목"), (sources, "참고문서")):
        if index is not None and (index + 1 >= len(lines) or not re.fullmatch(r"-{3,}", lines[index + 1])):
            errors.append(f"{name}: Setext 밑줄 필요")
    if grade is not None and environment is not None:
        summary = lines[grade + 1:environment]
        for label in ("Impact :", "CVSS v3 Base Score :", "기준일 :"):
            if not any(label in line for line in summary):
                errors.append(f"보안등급에 {label} 없음")
    if environment is not None and section_indices[0] is not None:
        if not any(re.match(r"^[*+-] ", line) for line in lines[environment + 1:section_indices[0]]):
            errors.append("Environment에 제품 또는 미확인 항목 필요")
    for line in lines:
        if HTML.search(line):
            errors.append("HTML 태그 사용")
            break
    if any(not _epoch_free(line) for line in lines):
        errors.append("NVR epoch 잔존")

    if package is not None and sources is not None and package < sources:
        segment = lines[package + 1:sources]
        headers = [i for i, line in enumerate(segment) if line.startswith("|") and cells(line) == HEADER]
        if len(headers) != 1:
            errors.append("패키지 표 7개 컬럼 불일치")
        else:
            pos = headers[0]
            if pos + 1 >= len(segment) or len(cells(segment[pos + 1])) != 7 or not all(SEPARATOR.fullmatch(c) for c in cells(segment[pos + 1])):
                errors.append("패키지 표 구분선 오류")
            body = []
            for line in segment[pos + 2:]:
                if not line.startswith("|"):
                    break
                body.append(line)
            if not body:
                errors.append("패키지 표에 제품 또는 미확인 행 필요")
            if any(len(cells(line)) != 7 for line in body):
                errors.append("패키지 표 행은 7개 컬럼이어야 함")
            notice_positions = [i for i, line in enumerate(segment) if line in (NOTICE, LEGACY_NOTICE)]
            if len(notice_positions) != 1 or notice_positions[0] <= pos + 1 + len(body):
                errors.append("패키지 표 아래 고정 문구 필요")
    if sources is not None and not any(re.match(r"^[*+-] ", line) for line in lines[sources + 1:]):
        errors.append("참고문서에 조회한 자료 또는 미확인 사유 필요")
    return errors


def self_test():
    """epoch 검사 오탐 회귀 시험. 예상 결과를 assert로 고정한다."""
    assert not _epoch_free("kernel-0:4.18.0-553.el8"), "epoch 잔존을 걸러야 함"
    assert _epoch_free("RHSA-2023:4201"), "RHSA 번호를 epoch로 오인하지 않아야 함"
    assert _epoch_free("CVSS:3.1/AV:N"), "CVSS 벡터를 epoch로 오인하지 않아야 함"
    assert _epoch_free("webkit2gtk3-2.46.3-1.el8_10.x86_64"), "정상 NVR을 통과해야 함"
    assert not _epoch_free("firefox-0:140.12.0-1.el9_8"), "firefox epoch 잔존을 걸러야 함"


def main(argv):
    if argv == ["--self-test"]:
        try:
            self_test()
        except AssertionError as e:
            print(f"FAIL: {e}")
            return 1
        print("PASS")
        return 0
    if len(argv) != 1:
        print("사용법: python check_report.py <리포트.md>", file=sys.stderr)
        return 2
    errors = check(argv[0])
    if errors:
        print(f"FAIL ({len(errors)}건)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))

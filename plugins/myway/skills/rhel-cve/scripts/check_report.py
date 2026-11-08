#!/usr/bin/env python3
"""Confluence용 RHEL CVE 리포트 구조와 epoch 잔존을 검사한다. 사실·출처·RPM EVR 비교의 진위는 검사하지 않는다."""
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
SCOPE_NOTE = "표의 판정 범위는 각 행에 기재한 제품 및 스트림입니다. 별도로 확인하지 않은 스트림은 이 표의 결론에 포함하지 않습니다."
CVE_TITLE = re.compile(r"^# (?P<cves>CVE-\d{4}-\d{4,}(?:\s*[,/]\s*CVE-\d{4}-\d{4,})*)\s+-\s+\S.+$")
INTEGRATED_FILENAME = re.compile(r"^RHEL_CVE_리포트_\d{8}\.md$")
INTEGRATED_TITLE = re.compile(r"^# RHEL CVE 통합 리포트 - 접수 (\d+)건 → 고유 (\d+)건$")
INTEGRATED_PREFIX = "# RHEL CVE 통합 리포트 - 접수"
PACKAGE_TITLE = re.compile(r"^영향을 받는 패키지 및 발행된 레드햇 보안 공지\s*\(\s*(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{2})\s*기준\s*\)$")
INTEGRATED_HEADER = ["CVE ID", *HEADER]
EPOCH = re.compile(r"(?<=[A-Za-z0-9_.+])-\d+:\d")
# 예약 예시 RHSA 형식의 "-2099:4"와 CVSS:3.x/ 벡터는 epoch가 아니다.
_EPOCH_MASK = re.compile(r"RH[SBE]A-\d{4}:\d+|CVSS:3\.\d/", re.IGNORECASE)
SEPARATOR = re.compile(r"^:?-{3,}:?$")


def _epoch_free(line):
    return not EPOCH.search(_EPOCH_MASK.sub("", line))


def cells(line):
    return [value.strip() for value in line.strip().strip("|").split("|")]


def check_integrated(path, text):
    """Check integrated report counts, per-CVE sections and linked package rows."""
    errors = []
    lines = []
    fenced = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            lines.append("")
        else:
            lines.append("" if fenced else line.strip())
    first = next((line for line in lines if line), "")
    m = INTEGRATED_TITLE.fullmatch(first)
    if not m:
        errors.append("통합 제목은 접수 N건 → 고유 M건 형식이어야 함")
        title_ids = re.findall(r"CVE-\d{4}-\d{4,}", first)
        if title_ids:
            errors.append("통합 제목에는 개별 CVE ID를 나열하지 않고 건수 요약만 둔다")
        return errors
    received, unique = map(int, m.groups())
    if received < unique or unique < 2:
        errors.append("통합 건수는 접수 N ≥ 고유 M ≥ 2여야 함")
    if not INTEGRATED_FILENAME.fullmatch(path.name):
        errors.append("통합 파일명은 RHEL_CVE_리포트_YYYYMMDD.md 형식이어야 함")
    cve_headings = [line for line in lines if re.fullmatch(r"### CVE-\d{4}-\d{4,}", line)]
    cves = [line[4:] for line in cve_headings]
    if len(cves) != unique or len(set(cves)) != unique:
        errors.append("고유 건수와 CVE별 상세 제목 수/중복이 일치하지 않음")
    if not cves:
        return errors
    if not any(line == "Environment" for line in lines):
        errors.append("통합 보고서에 Environment 항목 필요")
    heading_positions = {line[4:]: index for index, line in enumerate(lines)
                         if re.fullmatch(r"### CVE-\d{4}-\d{4,}", line)}
    if len(heading_positions) == unique:
        for cve in cves:
            start = heading_positions[cve]
            following = [heading_positions[next_cve] for next_cve in cves if heading_positions[next_cve] > start]
            end = min(following + [len(lines)])
            block = lines[start:end]
            if not all(section in block for section in SECTIONS):
                errors.append(f"CVE별 상세에 고정 1~5장 누락: {cve}")
    package_titles = [i for i, line in enumerate(lines) if PACKAGE_TITLE.fullmatch(line)]
    sources = [i for i, line in enumerate(lines) if line == "참고문서"]
    global_headings = [line for line in lines if line in {"Environment", *SECTIONS}
                       or re.fullmatch(r"### CVE-\d{4}-\d{4,}", line)]
    expected_headings = ["Environment", *[heading for cve in cves for heading in (f"### {cve}", *SECTIONS)]]
    if global_headings != expected_headings:
        errors.append("통합 리포트의 CVE별 1~5장 제목 순서가 잘못됨")
    if (len(package_titles) != 1 or len(sources) != 1
            or (package_titles and sources and package_titles[0] >= sources[0])):
        errors.append("통합 패키지 제목·참고문서 제목이 각각 한 번, 순서대로 필요")
        return errors
    seg = lines[package_titles[0] + 1:sources[0]]
    if not seg or not re.fullmatch(r"-{3,}", seg[0]):
        errors.append("통합 패키지 제목에 Setext 밑줄 필요")
    header_pos = [i for i, line in enumerate(seg) if line.startswith("|") and cells(line) == INTEGRATED_HEADER]
    if len(header_pos) != 1:
        errors.append("통합 패키지 표는 CVE ID 포함 8개 컬럼이어야 함")
        return errors
    pos = header_pos[0]
    if pos + 1 >= len(seg) or len(cells(seg[pos + 1])) != 8 or not all(SEPARATOR.fullmatch(c) for c in cells(seg[pos + 1])):
        errors.append("통합 패키지 표 구분선 오류")
        return errors
    body = []
    for line in seg[pos + 2:]:
        if not line.startswith("|"):
            break
        body.append(cells(line))
    if not body:
        errors.append("통합 패키지 표에 데이터 행 필요")
    for row in body:
        if len(row) != 8:
            errors.append("통합 패키지 표 행은 8개 컬럼이어야 함")
        elif row[0] not in cves:
            errors.append("통합 표 행 CVE ID가 상세 제목 목록에 없거나 비어 있음")
    seen = {row[0] for row in body if len(row) == 8}
    if seen != set(cves):
        errors.append("각 CVE가 통합 패키지 표에 최소 한 행씩 있어야 함")
    return errors


def check(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if INTEGRATED_FILENAME.fullmatch(path.name) or text.lstrip().startswith(INTEGRATED_PREFIX):
        return check_integrated(path, text)
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
    title_match = CVE_TITLE.fullmatch(first)
    cve_ids = []
    integrated = False
    if not title_match:
        errors.append("제목은 단건 CVE ID와 한국어 설명을 포함해야 함")
    else:
        cve_ids = re.findall(r"CVE-\d{4}-\d{4,}", title_match.group("cves"))
        integrated = len(cve_ids) > 1
        if integrated:
            errors.append("통합 리포트는 RHEL_CVE_리포트_YYYYMMDD.md 파일명과 전용 형식을 사용해야 함")
        elif not re.fullmatch(r"CVE-\d{4}-\d{4,}_리포트\.md", path.name):
            errors.append("단건 파일명은 CVE-YYYY-NNNNN_리포트.md 형식이어야 함")
    if integrated:
        if len(cve_ids) < 2:
            errors.append("통합 리포트에는 고유 CVE ID가 두 개 이상 필요")
        headings = [line for line in lines if line in SECTIONS
                    or re.fullmatch(r"### CVE-\d{4}-\d{4,}", line)]
        expected_headings = [heading for cve in cve_ids for heading in (f"### {cve}", *SECTIONS)]
    else:
        headings = [line for line in lines if line in SECTIONS]
        expected_headings = SECTIONS
    if headings != expected_headings:
        errors.append("허용된 단건 1~5장 또는 통합 CVE별 1~5장 제목만 정해진 순서로 사용해야 함")
    for line in lines:
        if re.match(r"^#{1,6}\s", line) and line not in SECTIONS:
            if integrated and re.fullmatch(r"### CVE-\d{4}-\d{4,}", line):
                continue
            if not integrated and line == first:
                continue
            errors.append(f"허용되지 않은 제목: {line}")

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
    if any(index is None for index in section_indices):
        errors.append("1~5장 고정 제목이 모두 필요")
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
    if section_indices[0] is not None and section_indices[1] is not None:
        overview = lines[section_indices[0] + 1:section_indices[1]]
        if not any("분석 대상 제품" in line for line in overview):
            errors.append("1장에 분석 대상 제품 표기 필요")
    for line in lines:
        if re.search(r"<(?!!--)[A-Za-z][^>]*>|</[A-Za-z][^>]*>", line):
            errors.append("HTML 태그 사용")
            break
    if any(not _epoch_free(line) for line in lines):
        errors.append("보고서 표시 위치에 NVR epoch 잔존(이 검사는 버전 비교를 확인하지 않음)")

    if package is not None and sources is not None and package < sources:
        segment = lines[package + 1:sources]
        body = []
        has_header = False
        pos = -1
        if integrated:
            headers = [i for i, line in enumerate(segment) if line.startswith("|") and cells(line) == INTEGRATED_HEADER]
            body = []
            pos = -1
            if len(headers) != 1:
                errors.append("통합 패키지 표에 CVE ID 포함 8개 컬럼 필요")
            else:
                has_header = True
                pos = headers[0]
                if pos + 1 >= len(segment) or len(cells(segment[pos + 1])) != 8 or not all(SEPARATOR.fullmatch(c) for c in cells(segment[pos + 1])):
                    errors.append("통합 패키지 표 구분선 오류")
                body = []
                for line in segment[pos + 2:]:
                    if not line.startswith("|"):
                        break
                    body.append(line)
                if not body:
                    errors.append("통합 패키지 표에 데이터 행 필요")
                if any(len(cells(line)) != 8 for line in body):
                    errors.append("통합 패키지 표 행은 8개 컬럼이어야 함")
                if any(cells(line)[0] not in cve_ids for line in body):
                    errors.append("통합 표 행의 CVE ID가 제목 목록에 없거나 누락됨")
        else:
            headers = [i for i, line in enumerate(segment) if line.startswith("|") and cells(line) == HEADER]
            if len(headers) != 1:
                errors.append("패키지 표 7개 컬럼 불일치")
            else:
                has_header = True
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
        if not has_header or not body:
            errors.append("패키지 표에 열 정의와 한 개 이상의 관측 행이 필요")
    if sources is not None and not any(re.match(r"^[*+-] ", line) for line in lines[sources + 1:]):
        errors.append("참고문서에 조회한 자료 또는 미확인 사유 필요")
    return errors


def self_test():
    """표시용 epoch 검사 오탐 회귀 시험. RPM EVR 비교는 검사하지 않는다."""
    assert not _epoch_free("kernel-0:4.18.0-553.el8"), "epoch 잔존을 걸러야 함"
    assert _epoch_free("RHSA-2099:4201"), "RHSA 번호를 epoch로 오인하지 않아야 함"
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

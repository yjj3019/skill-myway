#!/usr/bin/env python3
"""Validate the declared Markdown report contract, not vulnerability facts."""
import re
import sys
from pathlib import Path

SCOPE_NOTE = "표의 판정 범위는 각 행에 기재한 제품 및 스트림입니다. 별도로 확인하지 않은 스트림은 이 표의 결론에 포함하지 않습니다."
CHAPTERS = (
    "### 1. 취약점 개요", "### 2. 영향", "### 3. 완화 방법(Mitigation)",
    "### 4. 추가 정보", "### 5. 결론",
)
TABLE_COLUMNS = ("RHEL", "Lifecycle", "Components", "Fixed Package", "RHSA", "Release Date", "비고")
PACKAGE_LINE = re.compile(r"영향을 받는 패키지 및 발행된 레드햇 보안 공지\s*\(\s*(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{2})\s*기준\s*\)")
SINGLE_TITLE = re.compile(r"# (CVE-\d{4}-\d{4,})\s+-\s+\S.+")
BATCH_TITLE = re.compile(r"# RHEL CVE 통합 리포트 - 접수 (\d+)건 → 고유 (\d+)건")
CVE_HEADING = re.compile(r"### (CVE-\d{4}-\d{4,})")
SETEXT = re.compile(r"-{3,}")
RULE_CELL = re.compile(r":?-{3,}:?")
HTML_TAG = re.compile(r"<(?!!--)[A-Za-z][^>]*>|</[A-Za-z][^>]*>")
NVR_EPOCH = re.compile(r"(?<=[A-Za-z0-9_.+])-\d+:\d")
NON_PACKAGE_IDS = re.compile(r"RH[SBE]A-\d{4}:\d+|CVSS:3\.\d/", re.IGNORECASE)


def visible_lines(text):
    """Keep positional slots for code fences while excluding their contents."""
    if "\n<!-- REPORT START -->\n" in text:
        text = text.split("\n<!-- REPORT START -->\n", 1)[1]
    active = False
    result = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            active = not active
            result.append("")
        else:
            result.append("" if active else stripped)
    return result


def table_cells(line):
    return tuple(part.strip() for part in line.strip().strip("|").split("|"))


def one_position(lines, predicate, label, issues):
    positions = [i for i, line in enumerate(lines) if predicate(line)]
    if len(positions) != 1:
        issues.append(f"{label}: 정확히 한 번 필요")
        return None
    return positions[0]


def underlined(lines, position, label, issues):
    if position is not None and (position + 1 >= len(lines) or not SETEXT.fullmatch(lines[position + 1])):
        issues.append(f"{label}: Setext 밑줄 필요")


def package_table(lines, start, end, cves, issues):
    if start is None or end is None or start >= end:
        return
    expected = (("CVE ID",) if cves is not None else ()) + TABLE_COLUMNS
    area = lines[start + 1:end]
    headers = [i for i, line in enumerate(area) if line.startswith("|") and table_cells(line) == expected]
    if len(headers) != 1:
        issues.append("패키지 표의 열 정의가 없거나 중복됨")
        return
    first = headers[0] + 1
    if first >= len(area) or len(table_cells(area[first])) != len(expected) or not all(
            RULE_CELL.fullmatch(cell) for cell in table_cells(area[first])):
        issues.append("패키지 표 구분선 오류")
        return
    rows = []
    for line in area[first + 1:]:
        if not line.startswith("|"):
            break
        rows.append(table_cells(line))
    if not rows:
        issues.append("패키지 표에 데이터 행이 필요")
    if any(len(row) != len(expected) for row in rows):
        issues.append("패키지 표 행의 열 개수가 일치하지 않음")
    if cves is not None:
        linked = {row[0] for row in rows if len(row) == len(expected)}
        if linked != set(cves):
            issues.append("패키지 표의 CVE ID와 상세 목록이 일치하지 않음")


def single_report(path, lines, title, issues):
    match = SINGLE_TITLE.fullmatch(title)
    if match is None:
        issues.append("단건 제목에 CVE ID와 설명 필요")
    elif path.name != f"{match.group(1)}_리포트.md":
        issues.append("단건 파일명과 제목의 CVE ID가 일치해야 함")
    actual = [line for line in lines if line in CHAPTERS]
    if actual != list(CHAPTERS):
        issues.append("고정 1~5장 제목과 순서를 확인해야 함")
    if any(re.match(r"^#{1,6}\s", line) and line != title and line not in CHAPTERS for line in lines):
        issues.append("허용되지 않은 Markdown 제목이 있음")
    grade = one_position(lines, lambda x: x == "보안등급", "보안등급", issues)
    environment = one_position(lines, lambda x: x == "Environment", "Environment", issues)
    chapters = [one_position(lines, lambda x, item=item: x == item, item, issues) for item in CHAPTERS]
    package = one_position(lines, lambda x: bool(PACKAGE_LINE.fullmatch(x)), "패키지 제목", issues)
    sources = one_position(lines, lambda x: x == "참고문서", "참고문서", issues)
    positions = [grade, environment, *chapters, package, sources]
    if all(item is not None for item in positions) and positions != sorted(positions):
        issues.append("보고서 항목 순서가 올바르지 않음")
    for pos, name in ((environment, "Environment"), (package, "패키지 제목"), (sources, "참고문서")):
        underlined(lines, pos, name, issues)
    if grade is not None and environment is not None:
        area = lines[grade + 1:environment]
        for item in ("Impact :", "CVSS v3 Base Score :", "기준일 :"):
            if not any(item in line for line in area):
                issues.append(f"보안등급에 {item} 없음")
    if environment is not None and chapters[0] is not None:
        if not any(re.match(r"^[*+-] ", line) for line in lines[environment + 1:chapters[0]]):
            issues.append("Environment에 대상 또는 미확인 항목 필요")
    if chapters[0] is not None and chapters[1] is not None:
        if not any("분석 대상 제품" in line for line in lines[chapters[0] + 1:chapters[1]]):
            issues.append("1장에 분석 대상 제품 필요")
    package_table(lines, package, sources, None, issues)
    if sources is not None and not any(re.match(r"^[*+-] ", line) for line in lines[sources + 1:]):
        issues.append("참고문서에 자료 또는 미확인 사유 필요")


def batch_report(path, lines, title, issues):
    match = BATCH_TITLE.fullmatch(title)
    if match is None:
        issues.append("통합 제목에 접수 및 고유 건수가 필요")
        return
    received, unique = map(int, match.groups())
    if received < unique or unique < 2:
        issues.append("통합 건수는 접수 N ≥ 고유 M ≥ 2여야 함")
    if not re.fullmatch(r"RHEL_CVE_리포트_\d{8}\.md", path.name):
        issues.append("통합 파일명 형식 오류")
    cves = [m.group(1) for line in lines if (m := CVE_HEADING.fullmatch(line))]
    if len(cves) != unique or len(set(cves)) != unique:
        issues.append("고유 건수와 CVE 제목이 일치하지 않음")
    outline = [line for line in lines if line == "Environment" or line in CHAPTERS or CVE_HEADING.fullmatch(line)]
    expected = ["Environment"] + [line for cve in cves for line in (f"### {cve}", *CHAPTERS)]
    if outline != expected:
        issues.append("CVE별 장 제목과 순서가 올바르지 않음")
    package = one_position(lines, lambda x: bool(PACKAGE_LINE.fullmatch(x)), "패키지 제목", issues)
    sources = one_position(lines, lambda x: x == "참고문서", "참고문서", issues)
    if package is not None and sources is not None and package >= sources:
        issues.append("패키지 표가 참고문서보다 먼저 와야 함")
    underlined(lines, package, "패키지 제목", issues)
    package_table(lines, package, sources, cves, issues)


def check(path):
    path = Path(path)
    lines = visible_lines(path.read_text(encoding="utf-8-sig"))
    title = next((line for line in lines if line), "")
    issues = []
    if path.name.startswith("RHEL_CVE_리포트_") or title.startswith("# RHEL CVE 통합 리포트"):
        batch_report(path, lines, title, issues)
    else:
        single_report(path, lines, title, issues)
        if any(HTML_TAG.search(line) for line in lines):
            issues.append("HTML 태그는 허용하지 않음")
        if any(NVR_EPOCH.search(NON_PACKAGE_IDS.sub("", line)) for line in lines):
            issues.append("표시용 패키지 버전에 epoch가 남아 있음")
    return issues


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if argv == ["--self-test"]:
        for value, expected in (("kernel-0:4.18.0-553.el8", True), ("RHSA-2099:4201", False),
                                ("CVSS:3.1/AV:N", False), ("webkit2gtk3-2.46.3-1.el8_10.x86_64", False)):
            if bool(NVR_EPOCH.search(NON_PACKAGE_IDS.sub("", value))) != expected:
                print("FAIL")
                return 1
        print("PASS")
        return 0
    if len(argv) != 1:
        print("Usage: python check_report.py REPORT.md", file=sys.stderr)
        return 2
    try:
        issues = check(argv[0])
    except (OSError, UnicodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    if issues:
        print(f"FAIL ({len(issues)})")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

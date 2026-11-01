#!/usr/bin/env python3
"""가상 오피스 산출물을 생성·재열기해 구조를 확인한다. 가상 값만 사용한다.

사용: python3 scripts/check_office.py [--out DIR]

- PPTX: 3장 생성 후 다시 열어 슬라이드 수·제목 확인
- DOCX: 제목·문단·표 생성 후 다시 열어 개수 확인
- XLSX: 값·수식 생성 후 다시 열어 수식 문자열 확인
- 필요한 라이브러리(python-pptx, python-docx, openpyxl)가 없으면 NOT VERIFIED로 끝난다.
- 렌더링(넘침·겹침) 검증은 하지 않는다. 렌더러가 필요한 검사는 별도다.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


def check(out_dir):
    from pptx import Presentation
    from pptx.util import Inches
    from docx import Document
    from openpyxl import Workbook, load_workbook

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    prs = Presentation()
    for index, title in enumerate(("가상 표지: 20% 절감 제안", "가상 문제: 수작업 낭비", "가상 제안: 3단계 도입")):
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = title
        if index == 2:
            table = slide.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(6), Inches(1.2)).table
            table.cell(0, 0).text = "단계"
            table.cell(0, 1).text = "조치"
            table.cell(1, 0).text = "1"
            table.cell(1, 1).text = "통합"
    prs.save(out / "sample.pptx")
    reopened = Presentation(out / "sample.pptx")
    pptx = {"slides": len(reopened.slides), "titles": [s.shapes.title.text for s in reopened.slides]}

    document = Document()
    document.add_heading("가상 운영 보고서", level=1)
    document.add_paragraph("가상 서비스 A의 절차 통합 결과다. 수치는 가상 20% 절감이다.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "항목"
    table.cell(0, 1).text = "값"
    table.cell(1, 0).text = "절감률"
    table.cell(1, 1).text = "20%"
    document.save(out / "sample.docx")
    reopened_doc = Document(out / "sample.docx")
    docx = {
        "paragraphs": len(reopened_doc.paragraphs),
        "tables": len(reopened_doc.tables),
        "headings": [p.text for p in reopened_doc.paragraphs if p.style.name.startswith("Heading")],
    }

    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "항목"
    sheet["B1"] = "값"
    sheet["A2"] = "a"
    sheet["B2"] = 10
    sheet["A3"] = "b"
    sheet["B3"] = 20
    sheet["A4"] = "합계"
    sheet["B4"] = "=SUM(B2:B3)"
    workbook.save(out / "sample.xlsx")
    reopened_book = load_workbook(out / "sample.xlsx")
    reopened_sheet = reopened_book.active
    xlsx = {"rows": reopened_sheet.max_row, "formula": reopened_sheet["B4"].value}

    return {"pptx": pptx, "docx": docx, "xlsx": xlsx, "files": sorted(p.name for p in out.iterdir())}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="가상 오피스 산출물 생성·재열기 확인")
    parser.add_argument("--out", help="산출물을 저장할 디렉터리(기본: 임시)")
    args = parser.parse_args(argv)
    try:
        if args.out:
            result = check(args.out)
        else:
            with tempfile.TemporaryDirectory(prefix="myway-office-") as workdir:
                result = check(workdir)
    except ImportError as exc:
        print(f"NOT VERIFIED: 필요한 라이브러리가 없습니다 ({exc})")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

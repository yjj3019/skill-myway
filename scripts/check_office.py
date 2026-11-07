#!/usr/bin/env python3
"""가상 오피스 산출물을 생성·재열기해 구조를 확인한다. 가상 값만 사용한다.

사용: python3 scripts/check_office.py [--out DIR]

- PPTX: 3장 생성 후 다시 열어 슬라이드 수·제목 확인
- DOCX: 제목·문단·표 생성 후 다시 열어 개수 확인
- XLSX: 값·수식 구조 확인 후 가능하면 LibreOffice 재계산·캐시·기대값 검사
- 필요한 라이브러리(python-pptx, python-docx, openpyxl)가 없으면 NOT VERIFIED로 끝난다.
- LibreOffice/soffice가 있으면 샘플 XLSX 재계산 후 수식 캐시와 기대값을 별도 검사한다. 없거나 재계산을 확인할 수 없으면 calculation 상태를 NOT VERIFIED로 출력한다.
- 렌더링(넘침·겹침) 검증은 하지 않는다. 이 명령의 0 종료는 구조 검사 루틴 성공만 뜻하며 XLSX calculation 상태는 JSON에서 따로 확인한다.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath


def classify_calculation_value(value, expected):
    errors = {"#REF!", "#DIV/0!", "#VALUE!", "#N/A", "#NAME?", "#NULL!", "#NUM!"}
    if value is None:
        return {"status": "NOT VERIFIED", "value": None, "expected": expected}
    if isinstance(value, str) and value in errors:
        return {"status": "FAIL", "value": value, "expected": expected}
    return {"status": "PASS" if value == expected else "FAIL",
            "value": value, "expected": expected}


def recalculate_xlsx(path, expected_formula, expected_value):
    renderer = shutil.which("soffice") or shutil.which("libreoffice")
    if not renderer:
        return {"status": "NOT VERIFIED", "reason": "LibreOffice/soffice unavailable"}
    try:
        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory(prefix="myway-recalc-") as recalc_dir:
            profile = Path(recalc_dir) / "profile"
            profile.mkdir()
            result = subprocess.run(
                [renderer, "-env:UserInstallation=" + profile.resolve().as_uri(), "--headless",
                 "--convert-to", "xlsx", "--outdir", recalc_dir, str(path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
            )
            recalculated = Path(recalc_dir) / path.name
            if result.returncode != 0 or not recalculated.is_file():
                return {"status": "NOT VERIFIED", "engine": Path(renderer).name,
                        "returncode": result.returncode,
                        "diagnostic": (result.stderr.strip() or result.stdout.strip())[-300:]}
            formula_book = load_workbook(recalculated, data_only=False)
            cached_book = None
            try:
                formula = formula_book.active["B4"].value
                if formula != expected_formula:
                    return {"status": "FAIL", "reason": "formula changed or missing",
                            "formula": formula, "expected_formula": expected_formula,
                            "engine": Path(renderer).name}
                cached_book = load_workbook(recalculated, data_only=True)
                cached_value = cached_book.active["B4"].value
                result_data = classify_calculation_value(cached_value, expected_value)
                result_data["engine"] = Path(renderer).name
                return result_data
            finally:
                formula_book.close()
                if cached_book is not None:
                    cached_book.close()
    except subprocess.TimeoutExpired:
        return {"status": "NOT VERIFIED", "engine": Path(renderer).name, "reason": "recalculation timeout"}
    except ImportError as exc:
        return {"status": "NOT VERIFIED", "engine": Path(renderer).name, "reason": str(exc)}
    except (OSError, ValueError, KeyError) as exc:
        return {"status": "NOT VERIFIED", "engine": Path(renderer).name, "reason": str(exc)}


def inspect_office_file(path):
    """Inspect file structure only; never load external relationships or execute macros."""
    path = Path(path)
    suffix = path.suffix.lower()
    result = {"file": path.name, "format": suffix, "status": "FAIL"}
    if path.is_symlink() or not path.is_file():
        return {**result, "reason": "not a regular file"}
    if path.stat().st_size > 100 * 1024 * 1024:
        return {**result, "reason": "file exceeds 100 MiB inspection limit"}
    if suffix not in {".pptx", ".docx", ".xlsx"}:
        return {**result, "reason": "unsupported Office format"}
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            normalized = [PurePosixPath(name.replace("\\\\", "/").replace("\\", "/")) for name in names]
            if any(name.is_absolute() or ".." in name.parts for name in normalized):
                return {**result, "reason": "unsafe archive entry path"}
            total_uncompressed = sum(entry.file_size for entry in entries)
            if len(entries) > 2000 or total_uncompressed > 200 * 1024 * 1024:
                return {**result, "reason": "archive exceeds inspection limits"}
            if any(entry.file_size > 0 and entry.file_size / max(entry.compress_size, 1) > 1000
                   for entry in entries):
                return {**result, "reason": "archive entry compression ratio exceeds inspection limit"}
            lower_names = [name.lower() for name in names]
            if any(name.endswith("vbaproject.bin") for name in lower_names):
                return {**result, "reason": "macro project detected", "macro_project": True}
            if any(name.startswith("xl/externalLinks/".lower()) for name in lower_names):
                return {**result, "reason": "external workbook link part detected",
                        "external_workbook_links": True}
            rels = [name for name in names if name.endswith(".rels")]
            external_links = []
            for rel_path in rels:
                try:
                    root = ET.fromstring(archive.read(rel_path))
                except (ET.ParseError, KeyError):
                    return {**result, "reason": f"invalid relationship file: {rel_path}"}
                for rel in root:
                    if rel.attrib.get("TargetMode", "").lower() == "external":
                        external_links.append({"relationship_file": rel_path,
                                               "target": rel.attrib.get("Target", "")})
            if external_links:
                return {**result, "reason": "external relationships detected",
                        "external_relationships": external_links}
            if suffix == ".xlsx":
                from openpyxl import load_workbook
                formulas = load_workbook(path, data_only=False, read_only=True, keep_links=False)
                cached = load_workbook(path, data_only=True, read_only=True, keep_links=False)
                try:
                    formula_cells = []
                    missing_cache = []
                    cached_errors = []
                    for formula_sheet in formulas.worksheets:
                        cached_sheet = cached[formula_sheet.title]
                        for row in formula_sheet.iter_rows():
                            for cell in row:
                                if isinstance(cell.value, str) and cell.value.startswith("="):
                                    formula_cells.append(f"{formula_sheet.title}!{cell.coordinate}")
                                    cached_value = cached_sheet[cell.coordinate].value
                                    address = f"{formula_sheet.title}!{cell.coordinate}"
                                    if cached_value is None:
                                        missing_cache.append(address)
                                    elif isinstance(cached_value, str) and cached_value in {
                                            "#REF!", "#DIV/0!", "#VALUE!", "#N/A", "#NAME?", "#NULL!", "#NUM!"}:
                                        cached_errors.append({"cell": address, "error": cached_value})
                    calc_status = ("FAIL" if cached_errors else
                                   "NOT VERIFIED" if missing_cache else
                                   "PASS" if formula_cells else "NOT APPLICABLE")
                    return {**result, "status": "PASS", "sheets": len(formulas.sheetnames),
                            "formula_cells": formula_cells, "missing_formula_caches": missing_cache,
                            "cached_formula_errors": cached_errors,
                            "calculation_status": calc_status}
                finally:
                    formulas.close()
                    cached.close()
            if suffix == ".pptx":
                from pptx import Presentation
                presentation = Presentation(path)
                titles = []
                for slide in presentation.slides:
                    title = slide.shapes.title.text.strip() if slide.shapes.title else ""
                    titles.append(title)
                return {**result, "status": "PASS", "slides": len(presentation.slides),
                        "titles": titles, "untitled_slides": [index + 1 for index, title in enumerate(titles) if not title],
                        "images_without_alt_text": [
                            {"slide": slide_index, "shape": shape.name}
                            for slide_index, slide in enumerate(presentation.slides, 1)
                            for shape in slide.shapes
                            if shape.shape_type == 13 and not getattr(shape, "descr", "").strip()
                        ]}
            from docx import Document
            document = Document(path)
            return {**result, "status": "PASS", "paragraphs": len(document.paragraphs),
                    "tables": len(document.tables),
                    "headings": [p.text for p in document.paragraphs if p.style.name.startswith("Heading")],
                    "images_without_alt_text": [
                        shape.name for shape in document.inline_shapes
                        if not (shape._inline.docPr.get("descr") or "").strip()
                    ]}
    except PermissionError as exc:
        return {**result, "status": "NOT VERIFIED", "reason": f"file busy or permission denied: {exc}"}
    except PermissionError as exc:
        return {**result, "status": "NOT VERIFIED", "reason": f"file busy or permission denied: {exc}"}
    except ImportError as exc:
        return {**result, "status": "NOT VERIFIED", "reason": str(exc)}
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        return {**result, "reason": str(exc)}
    except Exception as exc:
        return {**result, "reason": f"inspection failed: {type(exc).__name__}: {exc}"}


def inspect_office_artifacts(workdir, files):
    reports = []
    for item in files:
        try:
            relative = PurePosixPath(item["path"])
            if relative.is_absolute() or ".." in relative.parts:
                reports.append({"file": item.get("path"), "status": "FAIL",
                                "reason": "unsafe artifact path"})
                continue
            path = Path(workdir).joinpath(*relative.parts)
            resolved_root = Path(workdir).resolve()
            if not path.resolve().is_relative_to(resolved_root):
                reports.append({"file": item.get("path"), "status": "FAIL",
                                "reason": "artifact path escaped work directory"})
                continue
            if path.suffix.lower() in {".pptx", ".docx", ".xlsx"}:
                reports.append(inspect_office_file(path))
        except (KeyError, OSError, ValueError) as exc:
            reports.append({"file": item.get("path"), "status": "FAIL", "reason": str(exc)})
    return reports


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
    formula_book = load_workbook(out / "sample.xlsx", data_only=False)
    formula_sheet = formula_book.active
    formula = formula_sheet["B4"].value
    formula_structure = {"rows": formula_sheet.max_row, "formula": formula,
                         "formula_preserved": formula == "=SUM(B2:B3)"}
    calculation = recalculate_xlsx(out / "sample.xlsx", "=SUM(B2:B3)", 30)
    xlsx = {**formula_structure, "calculation": calculation}
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
        print(json.dumps(result, ensure_ascii=False, indent=2))
        calculation = result.get("xlsx", {}).get("calculation", {})
        if calculation.get("status") == "FAIL":
            return 1
        return 0 if calculation.get("status") == "PASS" else 2
    except ImportError as exc:
        print(f"NOT VERIFIED: 필요한 라이브러리가 없습니다 ({exc})")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

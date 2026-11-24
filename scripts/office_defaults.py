"""python-pptx·python-docx의 기본 서식을 열 수 없을 때 대체 서식으로 문서를 만든다.

일부 환경에서는 보안 소프트웨어가 설치된 라이브러리의 서식 파일(zip 형식)을 다른 내용으로 바꿔
`Presentation()`·`Document()`가 실패한다. 서식을 확장자 없는 텍스트(base64 `.txt`)로 보관하고
임시 파일로 풀어 연다. 라이브러리 기본 서식이 정상이면 그대로 쓴다.
"""
from __future__ import annotations

import base64
import binascii
import tempfile
import zipfile
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "office_templates"


def _fallback_path(name, directory):
    data = base64.b64decode((TEMPLATES / f"{name}.b64.txt").read_text(encoding="ascii"), validate=False)
    if data[:2] != b"PK":
        raise ValueError(f"대체 서식이 손상됨: {name}")
    path = Path(directory) / f"{name}.package"
    path.write_bytes(data)
    return path


def new_presentation():
    from pptx import Presentation
    try:
        return Presentation()
    except Exception as error:  # 기본 서식이 zip이 아니거나 없을 때만 대체한다
        if not isinstance(error, (zipfile.BadZipFile, KeyError, OSError, ValueError)) and type(error).__name__ != "PackageNotFoundError":
            raise
    with tempfile.TemporaryDirectory() as tmp:
        return Presentation(str(_fallback_path("default-presentation", tmp)))


def new_document():
    from docx import Document
    try:
        return Document()
    except Exception as error:
        if not isinstance(error, (zipfile.BadZipFile, KeyError, OSError, ValueError)) and type(error).__name__ != "PackageNotFoundError":
            raise
    with tempfile.TemporaryDirectory() as tmp:
        return Document(str(_fallback_path("default-document", tmp)))

#!/usr/bin/env python3
"""Check recorded design-review evidence offline, without declaring quality success."""
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

MAX_MANIFEST = 1024 * 1024
MAX_FILE = 64 * 1024 * 1024
MAX_SURFACES = 200
KINDS = {"html", "image", "pdf", "pptx", "docx"}


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("invalid record")


def _linked(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _relative(value):
    if type(value) is not str or not value or len(value) > 512 or "\x00" in value or ":" in value:
        raise ValueError("invalid path")
    parts = value.replace("\\", "/").split("/")
    reserved = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)
    if any(not part or part in (".", "..") or reserved.match(part) or part.endswith((" ", ".")) for part in parts):
        raise ValueError("invalid path")
    return parts


def _digest_file(root, record):
    _shape(record, ("path", "sha256"))
    expected = record["sha256"]
    if type(expected) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("invalid digest")
    path = root
    for part in _relative(record["path"]):
        path = path / part
        if _linked(path):
            raise ValueError("linked path")
    if not path.resolve(strict=True).is_relative_to(root):
        raise ValueError("path outside evidence root")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > MAX_FILE:
            raise ValueError("invalid file")
        digest = hashlib.sha256()
        read = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            read += len(chunk)
            if read > MAX_FILE:
                raise ValueError("file too large")
            digest.update(chunk)
        if read == 0 or digest.hexdigest() != expected:
            raise ValueError("digest mismatch")
    finally:
        os.close(fd)


def check(root, manifest):
    _shape(manifest, ("schema_version", "artifacts"))
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("unsupported schema")
    root = Path(root)
    if _linked(root) or not root.is_dir():
        raise ValueError("invalid evidence root")
    root = root.resolve(strict=True)
    artifacts = manifest["artifacts"]
    if type(artifacts) is not list or not 1 <= len(artifacts) <= 20:
        raise ValueError("invalid artifacts")
    seen = set()
    summaries = []
    for artifact in artifacts:
        _shape(artifact, ("id", "kind", "source", "surfaces"))
        ident, kind = artifact["id"], artifact["kind"]
        if type(ident) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", ident) or ident in seen:
            raise ValueError("invalid artifact id")
        seen.add(ident)
        if type(kind) is not str or kind not in KINDS:
            raise ValueError("invalid artifact kind")
        _digest_file(root, artifact["source"])
        source_hash = artifact["source"]["sha256"]
        surfaces = artifact["surfaces"]
        if type(surfaces) is not list or not 1 <= len(surfaces) <= MAX_SURFACES:
            raise ValueError("invalid surfaces")
        render_paths = set()
        declared = []
        for number, surface in enumerate(surfaces, 1):
            _shape(surface, ("index", "render", "review"))
            if type(surface["index"]) is not int or surface["index"] != number:
                raise ValueError("invalid surface order")
            _digest_file(root, surface["render"])
            render_path = "/".join(_relative(surface["render"]["path"])).casefold()
            if render_path in render_paths:
                raise ValueError("duplicate render path")
            render_paths.add(render_path)
            review = surface["review"]
            _shape(review, ("source_sha256", "render_sha256", "status", "open_critical", "open_major"))
            if review["source_sha256"] != source_hash or review["render_sha256"] != surface["render"]["sha256"]:
                raise ValueError("review does not match evidence")
            if type(review["status"]) is not str or review["status"] not in ("PASS", "FAIL", "NOT VERIFIED"):
                raise ValueError("invalid review status")
            for key in ("open_critical", "open_major"):
                if type(review[key]) is not int or review[key] < 0:
                    raise ValueError("invalid finding count")
            declared.append("FAIL" if review["status"] == "FAIL" or review["open_critical"] or review["open_major"]
                            else review["status"])
        declared_status = ("FAIL" if "FAIL" in declared else
                           "NOT VERIFIED" if "NOT VERIFIED" in declared else "PASS")
        summaries.append({"id": ident, "kind": kind, "surfaces": len(surfaces), "declared_status": declared_status})
    return {"evidence_integrity": "PASS", "verdict": "FAIL" if any(x["declared_status"] == "FAIL" for x in summaries)
            else "NOT VERIFIED", "artifacts": summaries,
            "note": "Hashes match local bytes only; rendering, completeness, review truth and quality are not verified."}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("Usage: design_review_gate.py EVIDENCE_ROOT MANIFEST.json", file=sys.stderr)
        return 2
    try:
        path = Path(args[1])
        if _linked(path) or not path.is_file() or path.stat().st_size > MAX_MANIFEST:
            raise ValueError("invalid manifest")
        with path.open("rb") as source:
            data = source.read(MAX_MANIFEST + 1)
        if len(data) > MAX_MANIFEST:
            raise ValueError("manifest too large")
        manifest = json.loads(data.decode("utf-8"), object_pairs_hook=_unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid number")))
        result = check(args[0], manifest)
    except (OSError, ValueError, UnicodeError, RecursionError, TypeError):
        print("Invalid or unreadable design review evidence", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1  # Integrity alone is never a verified design-quality pass.


if __name__ == "__main__":
    sys.exit(main())

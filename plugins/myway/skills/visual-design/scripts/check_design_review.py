#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Adapted from the repository design review checker for planned PNG verification.
"""Check recorded design-review evidence offline, without declaring quality success."""
import hashlib
import io
import json
import math
import os
import re
import stat
import sys
import zlib
from pathlib import Path


MAX_MANIFEST = 1024 * 1024
MAX_FILE = 64 * 1024 * 1024
MAX_SURFACES = 200
KINDS = {"html", "image", "pdf", "pptx", "docx"}


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


def _png_size(buffer):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("schema 3 requires Pillow to decode PNG observations") from exc
    buffer.seek(0)
    header = buffer.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("observation must be a PNG raster")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    if width * height > 16_000_000:
        raise ValueError("render exceeds 16 million pixels")
    buffer.seek(0)
    with Image.open(buffer, formats=("PNG",)) as image:
        width, height = image.size
        image.verify()
    buffer.seek(0)
    with Image.open(buffer, formats=("PNG",)) as image:
        image.load()
    return [width, height]


def _digest_file(root, record, png=False):
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
        buffer = io.BytesIO() if png else None
        read = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            read += len(chunk)
            if read > MAX_FILE:
                raise ValueError("file too large")
            digest.update(chunk)
            if buffer is not None:
                buffer.write(chunk)
        if read == 0 or digest.hexdigest() != expected:
            raise ValueError("digest mismatch")
        if buffer is not None:
            return _png_size(buffer)
    finally:
        os.close(fd)


def _measurement_counts(rows):
    if type(rows) is not list or not 1 <= len(rows) <= 100:
        raise ValueError("invalid measurements")
    names = set()
    missing = 0
    for row in rows:
        if type(row) is not dict:
            raise ValueError("invalid measurement")
        unmeasured = "reason" in row
        fields = ("name", "reason") if unmeasured else ("name", "value", "unit", "location")
        _shape(row, fields)
        for key in fields:
            if key != "value" and (type(row[key]) is not str or not row[key].strip()):
                raise ValueError("empty measurement label or evidence")
        name = row["name"].strip()
        if name in names:
            raise ValueError("duplicate measurement")
        names.add(name)
        if unmeasured:
            missing += 1
        else:
            value = row["value"]
            if type(value) is not int and (type(value) is not float or not math.isfinite(value)):
                raise ValueError("invalid measurement value")
    return len(rows) - missing, missing


def _planned_surfaces(plan):
    _shape(plan, ("schema_version", "artifacts"))
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("unsupported plan schema")
    artifacts = plan["artifacts"]
    if type(artifacts) is not dict or not 1 <= len(artifacts) <= 20:
        raise ValueError("invalid planned artifacts")
    expected = {}
    for ident, item in artifacts.items():
        if type(ident) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", ident):
            raise ValueError("invalid planned artifact id")
        _shape(item, ("source_sha256", "surfaces"))
        if type(item["source_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", item["source_sha256"]):
            raise ValueError("invalid planned source digest")
        surfaces = item["surfaces"]
        if type(surfaces) is not dict or not 1 <= len(surfaces) <= MAX_SURFACES:
            raise ValueError("invalid planned surfaces")
        if len({name.casefold() for name in surfaces}) != len(surfaces):
            raise ValueError("ambiguous planned render names")
        for name, size in surfaces.items():
            if name != "/".join(_relative(name)):
                raise ValueError("use canonical relative render paths in the plan")
            key = (ident, name)
            if key in expected or type(size) is not list or len(size) != 2 or any(
                    type(n) is not int or n < 1 for n in size) or size[0] * size[1] > 16_000_000:
                raise ValueError("duplicate planned surface or invalid pixel size")
            expected[key] = size
    return expected


def check(root, manifest, plan=None):
    _shape(manifest, ("schema_version", "artifacts"))
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] not in (1, 2, 3):
        raise ValueError("unsupported schema")
    version = manifest["schema_version"]
    if (version == 3) != (plan is not None):
        raise ValueError("schema 3 and an independent plan must be supplied together")
    expected = _planned_surfaces(plan) if version == 3 else {}
    observed = {}
    source_mismatches = []
    root = Path(root)
    if _linked(root) or not root.is_dir():
        raise ValueError("invalid evidence root")
    root = root.resolve(strict=True)
    artifacts = manifest["artifacts"]
    if type(artifacts) is not list or not (0 if version == 3 else 1) <= len(artifacts) <= 20:
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
        if plan is not None and ident in plan["artifacts"] and source_hash != plan["artifacts"][ident]["source_sha256"]:
            source_mismatches.append(ident)
        surfaces = artifact["surfaces"]
        if type(surfaces) is not list or not (0 if version == 3 else 1) <= len(surfaces) <= MAX_SURFACES:
            raise ValueError("invalid surfaces")
        render_paths = set()
        declared = []
        measured = unmeasured = 0
        previous_index = 0
        for number, surface in enumerate(surfaces, 1):
            has_measurements = version >= 2
            fields = ("index", "render", "review")
            _shape(surface, fields + ("measurements",) if has_measurements else fields)
            index = surface["index"]
            if (type(index) is not int or not previous_index < index <= MAX_SURFACES
                    or (version < 3 and index != number)):
                raise ValueError("invalid surface order")
            previous_index = index
            size = _digest_file(root, surface["render"], png=version == 3)
            render_path = "/".join(_relative(surface["render"]["path"])).casefold()
            if render_path in render_paths:
                raise ValueError("duplicate render path")
            render_paths.add(render_path)
            if version == 3:
                observed[ident, "/".join(_relative(surface["render"]["path"]))] = size
            review = surface["review"]
            _shape(review, ("source_sha256", "render_sha256", "status", "open_critical", "open_major"))
            if review["source_sha256"] != source_hash or review["render_sha256"] != surface["render"]["sha256"]:
                raise ValueError("review does not match evidence")
            if type(review["status"]) is not str or review["status"] not in ("PASS", "FAIL", "NOT VERIFIED"):
                raise ValueError("invalid review status")
            for key in ("open_critical", "open_major"):
                if type(review[key]) is not int or review[key] < 0:
                    raise ValueError("invalid finding count")
            status = review["status"]
            if has_measurements:
                known, missing = _measurement_counts(surface["measurements"])
                measured += known
                unmeasured += missing
                if missing and status == "PASS":
                    status = "NOT VERIFIED"
            if review["open_critical"] or review["open_major"]:
                status = "FAIL"
            declared.append(status)
        declared_status = ("FAIL" if "FAIL" in declared else
                           "NOT VERIFIED" if not declared or "NOT VERIFIED" in declared else "PASS")
        summary = {"id": ident, "kind": kind, "surfaces": len(surfaces), "declared_status": declared_status}
        if version >= 2:
            summary.update(measured=measured, unmeasured=unmeasured)
        summaries.append(summary)
    result = {"evidence_integrity": "PASS", "artifacts": summaries,
              "verdict": "FAIL" if any(x["declared_status"] == "FAIL" for x in summaries) else "NOT VERIFIED"}
    if plan is not None:
        missing = sorted(expected.keys() - observed.keys())
        extra = sorted(observed.keys() - expected.keys())
        wrong_sizes = [{"surface": key, "expected": expected[key], "observed": observed[key]}
                       for key in sorted(expected.keys() & observed.keys()) if expected[key] != observed[key]]
        extra_artifacts = sorted(seen - plan["artifacts"].keys())
        complete = not (missing or extra or wrong_sizes or source_mismatches or extra_artifacts)
        result["plan_coverage"] = {"status": "PASS" if complete else "FAIL", "planned": len(expected),
                                   "observed": len(observed), "missing": missing, "unexpected": extra,
                                   "unexpected_artifacts": extra_artifacts, "size_mismatches": wrong_sizes,
                                   "source_mismatches": source_mismatches}
        if not complete:
            result["verdict"] = "FAIL"
    result["note"] = "File and plan checks do not establish rendering provenance or design quality."
    return result


def _read_record(path):
    if _linked(path) or not path.is_file() or path.stat().st_size > MAX_MANIFEST:
        raise ValueError("invalid manifest or plan")
    with path.open("rb") as source:
        data = source.read(MAX_MANIFEST + 1)
    if len(data) > MAX_MANIFEST:
        raise ValueError("record too large")

    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("duplicate JSON key")
        return result

    def invalid_number(token):
        raise ValueError("invalid JSON number")

    return json.loads(data.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_number)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (2, 4) or (len(args) == 4 and args[2] != "--plan"):
        print("Usage: design_review_gate.py EVIDENCE_ROOT MANIFEST.json [--plan PLAN.json]", file=sys.stderr)
        return 2
    try:
        manifest = _read_record(Path(args[1]))
        plan = _read_record(Path(args[3])) if len(args) == 4 else None
        result = check(args[0], manifest, plan)
    except (OSError, ValueError, RecursionError, TypeError, SyntaxError, zlib.error) as exc:
        print(f"Invalid or unreadable design review evidence: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if plan is not None:
        return 0 if result["plan_coverage"]["status"] == "PASS" and result["verdict"] != "FAIL" else 1
    return 1  # Legacy checks cannot certify design quality.


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Bind a declared human review to exact output and a pre-existing rubric.

This validates a review record, not the truth of the review or its independence.
"""
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

MAX_BYTES = 1024 * 1024
STATUSES = {"PASS", "FAIL", "NOT VERIFIED"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_bounded(path):
    with Path(path).open("rb") as source:
        data = source.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("input too large")
    return data


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json(data):
    return json.loads(data.decode("utf-8"), object_pairs_hook=_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid number")))


def _label(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 4000


def verify_evidence_file(root, item):
    """Check a bounded local file and its digest; this does not establish relevance or authorship."""
    if type(item) is not dict or set(item) != {"path", "sha256"}:
        raise ValueError("invalid evidence file")
    name, expected = item["path"], item["sha256"]
    if not _label(name) or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("invalid evidence file")
    relative = Path(name)
    if relative.is_absolute() or relative.drive or any(part in ("..", ".") for part in relative.parts):
        raise ValueError("invalid evidence path")
    base = Path(root).resolve(strict=True)
    if not base.is_dir():
        raise ValueError("invalid evidence root")
    target = base
    for part in relative.parts:
        target = target / part
        if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
            raise ValueError("linked evidence path")
    target = target.resolve(strict=True)
    if not target.is_relative_to(base) or not target.is_file():
        raise ValueError("evidence outside root or not a file")
    with target.open("rb") as source:
        data = source.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or not hmac.compare_digest(sha256(data), expected):
        raise ValueError("evidence size or hash mismatch")


def review(output_bytes, rubric_bytes, review_bytes, evidence_root=None):
    """Return a declared result. A matching record is not proof of its claims."""
    if any(len(data) > MAX_BYTES for data in (output_bytes, rubric_bytes, review_bytes)):
        raise ValueError("input too large")
    if not output_bytes.strip():
        raise ValueError("empty output")
    rubric, record = _json(rubric_bytes), _json(review_bytes)
    if type(rubric) is not dict or set(rubric) != {"schema_version", "criteria"} or type(rubric["schema_version"]) is not int or rubric["schema_version"] != 1:
        raise ValueError("invalid rubric")
    criteria = rubric["criteria"]
    if type(criteria) is not list or not 1 <= len(criteria) <= 100:
        raise ValueError("invalid criteria")
    required = {}
    for item in criteria:
        if type(item) is not dict or set(item) != {"id", "instruction", "evidence_required"} or not _label(item["id"]) or not _label(item["instruction"]) or type(item["evidence_required"]) is not bool or item["id"] in required:
            raise ValueError("invalid criterion")
        required[item["id"]] = item["evidence_required"]
    keys = {"schema_version", "output_sha256", "rubric_sha256", "reviewer", "independent", "criteria"}
    if type(record) is not dict or set(record) != keys or type(record["schema_version"]) is not int or record["schema_version"] != 1:
        raise ValueError("invalid review")
    if record["output_sha256"] != sha256(output_bytes) or record["rubric_sha256"] != sha256(rubric_bytes):
        raise ValueError("output or rubric hash mismatch")
    if not _label(record["reviewer"]) or type(record["independent"]) is not bool or type(record["criteria"]) is not list:
        raise ValueError("invalid reviewer")
    seen = {}
    for item in record["criteria"]:
        if type(item) is not dict or set(item) != {"id", "status", "reason", "evidence"}:
            raise ValueError("invalid judgment")
        ident = item["id"]
        if not isinstance(ident, str) or ident not in required or ident in seen or not isinstance(item["status"], str) or item["status"] not in STATUSES or not _label(item["reason"]):
            raise ValueError("invalid judgment")
        evidence = item["evidence"]
        if type(evidence) is not list:
            raise ValueError("invalid evidence")
        if evidence_root is None:
            if any(not _label(entry) for entry in evidence):
                raise ValueError("invalid evidence")
        else:
            for entry in evidence:
                verify_evidence_file(evidence_root, entry)
        if item["status"] == "PASS" and required[ident] and not evidence:
            raise ValueError("evidence required for pass")
        seen[ident] = item["status"]
    if set(seen) != set(required):
        raise ValueError("incomplete review")
    declared_result = ("FAIL" if "FAIL" in seen.values() else
                       "NOT VERIFIED" if "NOT VERIFIED" in seen.values() else "PASS")
    # A free-form evidence string and a self-declared identity cannot authenticate either.
    verdict = "FAIL" if declared_result == "FAIL" else "NOT VERIFIED"
    evidence_count = sum(len(item["evidence"]) for item in record["criteria"])
    return {"verdict": verdict, "declared_result": declared_result,
            "evidence_file_integrity": "PASS" if evidence_root is not None and evidence_count else "NOT VERIFIED",
            "output_sha256": sha256(output_bytes),
            "rubric_sha256": sha256(rubric_bytes), "reviewer": record["reviewer"],
            "independence_declared": record["independent"], "criteria": seen,
            "note": "Declarations only: evidence, reviewer independence and correctness are not authenticated."}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) in (3, 4) and args[0] == "--template":
        try:
            output, rubric_bytes = (read_bounded(path) for path in args[1:3])
            rubric = _json(rubric_bytes)
            template = {"schema_version": 1, "output_sha256": sha256(output),
                        "rubric_sha256": sha256(rubric_bytes), "reviewer": "",
                        "independent": False, "criteria": [
                            {"id": item["id"], "status": "NOT VERIFIED", "reason": "", "evidence": []}
                            for item in rubric["criteria"]]}
            rendered = json.dumps(template, ensure_ascii=False, indent=2) + "\n"
            if len(args) == 4:
                with Path(args[3]).open("x", encoding="utf-8", newline="\n") as target:
                    target.write(rendered)
            else:
                print(rendered, end="")
            return 0
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            print("Invalid or unreadable template inputs", file=sys.stderr)
            return 1
    evidence_root = None
    if len(args) == 5 and args[0] == "--evidence-root":
        evidence_root, args = args[1], args[2:]
    if len(args) != 3:
        print("Usage: review_evaluation.py [--template | --evidence-root DIR] OUTPUT RUBRIC.json REVIEW.json", file=sys.stderr)
        return 2
    try:
        data = [read_bounded(path) for path in args]
        result = review(*data, evidence_root=evidence_root)
    except (OSError, ValueError, UnicodeError, RecursionError, TypeError):
        print("Invalid or unreadable review inputs", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    sys.exit(main())

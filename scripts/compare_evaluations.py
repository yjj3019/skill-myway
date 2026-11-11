#!/usr/bin/env python3
"""Summarize declared paired judgments without calling models or promoting results."""
import json
import os
import stat
import sys
from collections import Counter

MAX_BYTES = 1024 * 1024
MAX_TRIALS = 10000
CONTEXT_KEYS = ("cases", "rubric", "scorer", "environment")
VERDICTS = ("PASS", "FAIL", "UNJUDGED", "TIMEOUT", "ERROR", "NOT_RUN")


def _object(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("bad record shape")


def _label(value):
    return type(value) is str and 0 < len(value) <= 200 and value == value.strip() and not any(ord(c) < 32 for c in value)


def summarize(record):
    """Count declared trial pairs; matching declarations do not establish truth."""
    _object(record, ("schema_version", "judgment_source", "context", "planned", "trials"))
    if type(record["schema_version"]) is not int or record["schema_version"] != 1:
        raise ValueError("unsupported schema")
    if record["judgment_source"] not in ("human", "automatic"):
        raise ValueError("bad judgment source")
    contexts = record["context"]
    _object(contexts, ("baseline", "candidate"))
    for side in ("baseline", "candidate"):
        _object(contexts[side], CONTEXT_KEYS)
        for field in CONTEXT_KEYS:
            value = contexts[side][field]
            if value is not None and (not _label(value) or value.upper() in ("UNKNOWN", "N/A", "TBD", "NONE")):
                raise ValueError("bad context value")

    plan = record["planned"]
    trials = record["trials"]
    if type(plan) is not list or not 1 <= len(plan) <= MAX_TRIALS or type(trials) is not list:
        raise ValueError("bad trial count")
    expected = set()
    for entry in plan:
        _object(entry, ("case", "repeat"))
        if not _label(entry["case"]) or type(entry["repeat"]) is not int or entry["repeat"] < 1:
            raise ValueError("bad planned key")
        pair = (entry["case"], entry["repeat"])
        if pair in expected:
            raise ValueError("duplicate planned key")
        expected.add(pair)
    counts = {"planned": len(plan), "judged": 0, "incomplete": 0,
              "fail_to_pass": 0, "pass_to_fail": 0, "pass_to_pass": 0, "fail_to_fail": 0}
    side_counts = {"baseline": Counter(), "candidate": Counter()}
    seen = set()
    for trial in trials:
        _object(trial, ("case", "repeat", "baseline", "candidate"))
        if not _label(trial["case"]) or type(trial["repeat"]) is not int or trial["repeat"] < 1:
            raise ValueError("bad trial key")
        key = (trial["case"], trial["repeat"])
        if key in seen:
            raise ValueError("duplicate trial key")
        if key not in expected:
            raise ValueError("unplanned trial")
        seen.add(key)
        for side in ("baseline", "candidate"):
            if type(trial[side]) is not str or trial[side] not in VERDICTS:
                raise ValueError("bad verdict")
            side_counts[side][trial[side]] += 1
        left, right = trial["baseline"], trial["candidate"]
        if left in ("PASS", "FAIL") and right in ("PASS", "FAIL"):
            counts["judged"] += 1
            counts[f"{left.lower()}_to_{right.lower()}"] += 1
        else:
            counts["incomplete"] += 1

    if seen != expected:
        raise ValueError("missing planned trial")

    missing = [field for field in CONTEXT_KEYS if any(contexts[side][field] is None for side in ("baseline", "candidate"))]
    different = [field for field in CONTEXT_KEYS if all(contexts[side][field] is not None for side in ("baseline", "candidate"))
                 and contexts["baseline"][field] != contexts["candidate"][field]]
    return {"schema_version": 1, "judgment_source": record["judgment_source"],
            "context_status": "UNVERIFIED" if missing or different else "DECLARED_MATCH",
            "missing_context": missing, "different_context": different, "pairs": counts,
            "status_counts": {side: {status: side_counts[side][status] for status in VERDICTS}
                              for side in ("baseline", "candidate")},
            "note": "Counts summarize declarations only; evidence, independence and quality are not verified."}


def _unique_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def read_record(path):
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("not a regular file")
        with os.fdopen(fd, "rb") as file:
            fd = -1
            data = file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("input too large")
        return json.loads(data.decode("utf-8"), object_pairs_hook=_unique_members,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid number")))
    finally:
        if fd != -1:
            os.close(fd)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: compare_evaluations.py RECORD.json", file=sys.stderr)
        return 2
    try:
        report = summarize(read_record(args[0]))
    except (OSError, ValueError, UnicodeError, RecursionError):
        print("Invalid or unreadable comparison record", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

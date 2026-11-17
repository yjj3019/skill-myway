#!/usr/bin/env python3
"""Compare explicitly supplied literal strings in two UTF-8 texts.

Only occurrence counts are checked; semantic preservation is not established.
The report deliberately excludes the input texts and protected strings.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_LIST_BYTES = 256 * 1024
MAX_ITEMS = 256
MAX_ITEM_CHARS = 4096


def read_utf8(path: str, limit: int) -> str:
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input size limit exceeded")
    return data.decode("utf-8")


def compare(source: str, edited: str, protected: object) -> list[dict]:
    if not isinstance(protected, list) or not 1 <= len(protected) <= MAX_ITEMS:
        raise ValueError("protected list must contain 1 to 256 items")
    if any(not isinstance(item, str) or not item or len(item) > MAX_ITEM_CHARS for item in protected):
        raise ValueError("protected items must be nonempty strings of at most 4096 characters")
    if len(set(protected)) != len(protected):
        raise ValueError("duplicate protected item")
    rows = []
    for index, item in enumerate(protected, 1):
        before, after = source.count(item), edited.count(item)
        if before == 0:
            raise ValueError("protected item absent from source")
        rows.append({"index": index, "source_count": before, "edited_count": after,
                     "status": "MATCH" if before == after else "CHANGED"})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="original UTF-8 text file")
    parser.add_argument("--edited", required=True, help="edited UTF-8 text file")
    parser.add_argument("--protected", required=True, help="UTF-8 JSON array of explicit literal strings")
    args = parser.parse_args(argv)
    try:
        source = read_utf8(args.source, MAX_TEXT_BYTES)
        edited = read_utf8(args.edited, MAX_TEXT_BYTES)
        protected = json.loads(read_utf8(args.protected, MAX_LIST_BYTES))
        rows = compare(source, edited, protected)
    except (OSError, UnicodeError, ValueError, RecursionError):
        print("Invalid or unreadable input; no comparison performed.", file=sys.stderr)
        return 2
    changed = sum(row["status"] == "CHANGED" for row in rows)
    print(json.dumps({"status": "MATCH" if not changed else "CHANGED", "items": rows,
                      "semantics": "NOT VERIFIED"}, ensure_ascii=False, indent=2))
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())

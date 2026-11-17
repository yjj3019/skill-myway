#!/usr/bin/env python3
"""Extract unambiguous exact title lines from a PDF, failing on missing matches."""
import argparse
import json
import re
import subprocess


def norm(value):
    return re.sub(r"\s+", "", value)


def find_titles(text, titles, skip_pages=0):
    if not isinstance(titles, list) or not titles or any(not isinstance(t, str) or not norm(t) for t in titles):
        raise ValueError("titles must be a nonempty list of nonempty strings")
    keys = [norm(title) for title in titles]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate normalized titles")
    pages = text.split("\x0c")
    if skip_pages < 0 or skip_pages >= len(pages):
        raise ValueError("invalid page skip")
    lines = [[norm(line) for line in page.splitlines() if norm(line)] for page in pages]
    results = []
    for title, key in zip(titles, keys):
        matches = [i + 1 for i, page in enumerate(lines) if i >= skip_pages for line in page if line == key]
        if len(matches) != 1:
            raise ValueError(f"title match count is {len(matches)}; inspect the extracted PDF")
        results.append({"title": title, "page": matches[0]})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("titles_json")
    parser.add_argument("out_json")
    parser.add_argument("--skip-pages", type=int, default=0)
    args = parser.parse_args(argv)
    txt = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", args.pdf, "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="strict",
                         check=True, timeout=120).stdout
    with open(args.titles_json, encoding="utf-8") as source:
        titles = json.load(source)
    toc = find_titles(txt, titles, args.skip_pages)
    with open(args.out_json, "x", encoding="utf-8") as target:
        json.dump(toc, target, ensure_ascii=False, indent=2)
    print(f"[OK] extracted {len(toc)} unambiguous titles")


if __name__ == "__main__":
    main()

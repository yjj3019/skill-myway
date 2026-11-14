#!/usr/bin/env python3
"""gen_toc.py — Pass1 PDF에서 각 TITLE의 첫 등장 페이지를 찾아 toc.json 생성.

사용: python3 gen_toc.py <temp.pdf> <titles.json> <out_toc.json>
  titles.json: ["1. 개요", "2. ...", ...]  (fcontent.js의 TITLES와 동일)
  out_toc.json: [{"title": "...", "page": N}, ...]

원리: pdftotext -layout 로 페이지 구분(\\x0c) 보존 → 페이지별로 제목 문자열
      최초 출현 페이지를 기록. 공백 정규화로 매칭 안정성 확보.
"""
import sys, json, subprocess, re

def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)

def main():
    if len(sys.argv) != 4:
        print("usage: gen_toc.py <pdf> <titles.json> <out.json>", file=sys.stderr)
        sys.exit(2)
    pdf, titles_path, out_path = sys.argv[1:4]

    txt = subprocess.run(
        ["pdftotext", "-layout", pdf, "-"],
        capture_output=True, text=True, check=True, timeout=120,
    ).stdout
    pages = [norm(page) for page in txt.split("\x0c")]  # 정규화는 페이지당 한 번

    with open(titles_path, encoding="utf-8") as f:
        titles = json.load(f)

    toc, missing = [], []
    for t in titles:
        key, found = norm(t), None
        for i, pg in enumerate(pages, start=1):
            if key in pg:
                found = i
                break
        toc.append({"title": t, "page": found})
        if found is None:
            missing.append(t)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(toc, f, ensure_ascii=False, indent=2)

    if missing:
        print(f"[WARN] 페이지 미발견 {len(missing)}건: {missing}", file=sys.stderr)
    print(f"[OK] toc.json 생성: {len(toc)}개 제목", file=sys.stderr)

if __name__ == "__main__":
    main()

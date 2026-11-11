#!/usr/bin/env python3
"""가상(시뮬레이션) 평가 입력을 검증하고 실행 패킷·manifest를 만든다. 모델 호출은 하지 않는다.

사용: python3 scripts/simulate_eval.py [--cases FILE] [--out DIR]

검사 항목
- 케이스 스키마: 필수 필드, id 중복, 알 수 없는 스킬
- 커버리지: 모든 스킬에 케이스가 하나 이상
- 안전성: 요청에 실제 형식의 CVE/RHSA, 이메일, IP, 홈 경로, 토큰이 없는지
- 패킷: 케이스별 요청 해시와 스킬 본문 해시를 기록해 같은 입력인지 추적
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo  # noqa: E402

DEFAULT_CASES = ROOT / "tests" / "eval_cases" / "cases.json"
SKILLS = ROOT / "plugins" / "myway" / "skills"


def skill_names():
    return sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())


def load_cases(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"케이스 파일을 읽을 수 없습니다: {path} ({exc})") from exc


def validate(cases):
    errors = []
    if not isinstance(cases, dict) or cases.get("schema_version") not in (1, 2):
        return ["schema_version 1 또는 2가 필요합니다"]
    items = cases.get("cases")
    if not isinstance(items, list) or not items:
        return ["cases 배열이 비어 있습니다"]
    known = set(skill_names())
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            errors.append("케이스 항목이 객체가 아닙니다")
            continue
        case_id = item.get("id")
        skill = item.get("skill")
        request = item.get("request")
        if not isinstance(case_id, str) or not case_id.strip():
            errors.append("id가 비어 있습니다")
            continue
        if case_id in seen:
            errors.append(f"{case_id}: id가 중복됩니다")
        seen.add(case_id)
        if not isinstance(skill, str) or skill not in known:
            errors.append(f"{case_id}: 알 수 없는 스킬 {skill}")
        if not isinstance(request, str) or len(request.strip()) < 10:
            errors.append(f"{case_id}: request가 너무 짧습니다")
            continue
        for kind, pattern in validate_repo.SENSITIVE:
            # rhel-cve 평가 케이스의 request는 실제 CVE ID를 조사 입력으로 쓴다(가상 값이 아니다).
            if kind == "real-advisory-id":
                continue
            for match in pattern.finditer(request):
                value = match.group(0)
                if kind == "ipv4":
                    if validate_repo.SAFE_IP.match(value) or any(int(x) > 255 for x in value.split(".")):
                        continue
                if kind == "email" and validate_repo.SAFE_EMAIL.search(value):
                    continue
                errors.append(f"{case_id}: 민감 패턴({kind}) 의심")
                break
        for key in ("required", "forbidden"):
            value = item.get(key, [])
            if not isinstance(value, list):
                errors.append(f"{case_id}: {key}는 배열이어야 합니다")
                continue
            for entry in value:
                if isinstance(entry, str) and entry:
                    continue
                if isinstance(entry, list) and entry and all(isinstance(alt, str) and alt for alt in entry):
                    continue
                errors.append(f"{case_id}: {key} 항목은 문자열 또는 문자열 배열이어야 합니다")
                break
        if "ends_with" in item and (cases["schema_version"] != 2 or not isinstance(item["ends_with"], str) or not item["ends_with"]):
            errors.append(f"{case_id}: ends_with는 schema_version 2의 비어 있지 않은 문자열이어야 합니다")
        max_chars = item.get("max_chars", 8000)
        if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars <= 0:
            errors.append(f"{case_id}: max_chars가 잘못됐습니다")
    covered = {item["skill"] for item in items
               if isinstance(item, dict) and isinstance(item.get("skill"), str)}
    for name in known:
        if name not in covered:
            errors.append(f"커버리지 누락: {name}")
    return errors


def manifest(cases):
    items = []
    for item in cases["cases"]:
        skill_md = SKILLS / item["skill"] / "SKILL.md"
        request = item["request"].encode("utf-8")
        items.append({
            "id": item["id"],
            "skill": item["skill"],
            "request_sha256": hashlib.sha256(request).hexdigest(),
            "skill_sha256": hashlib.sha256(skill_md.read_bytes()).hexdigest() if skill_md.is_file() else None,
            "required": item.get("required", []),
            "forbidden": item.get("forbidden", []),
            "max_chars": item.get("max_chars", 8000),
            **({"ends_with": item["ends_with"]} if "ends_with" in item else {}),
        })
    return {"schema_version": 1, "cases": items}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="가상 평가 케이스를 검증하고 패킷을 만든다")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--out", help="manifest를 저장할 파일")
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.cases)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    errors = validate(cases)
    if errors:
        print(f"FAIL {len(errors)}건")
        for error in errors:
            print(" -", error)
        return 1
    data = manifest(cases)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    skills = sorted({item["skill"] for item in data["cases"]})
    print(f"PASS 케이스 {len(data['cases'])}건 / 스킬 {len(skills)}개")
    print("스킬:", ", ".join(skills))
    return 0


if __name__ == "__main__":
    sys.exit(main())

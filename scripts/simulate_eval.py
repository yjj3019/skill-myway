#!/usr/bin/env python3
"""가상(시뮬레이션) 평가 입력을 검증하고 실행 패킷·manifest를 만든다. 모델 호출은 하지 않는다.

사용: python3 scripts/simulate_eval.py [--cases FILE] [--out DIR]

검사 항목
- 케이스 스키마: 필수 필드, id 중복, 알 수 없는 스킬
- 커버리지: 모든 스킬에 케이스가 하나 이상
- 안전성: 요청에 실제 형식의 CVE/RHSA, 이메일, IP, 홈 경로, 토큰이 없는지
- 패킷: 케이스별 요청과 스킬 트리의 파일별 해시를 기록
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
    def unique_members(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("중복 JSON 키")
            result[key] = value
        return result

    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_members,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("잘못된 JSON 숫자")))
    except (OSError, ValueError) as exc:
        raise ValueError(f"케이스 파일을 읽을 수 없습니다: {path} ({exc})") from exc


def validate(cases):
    errors = []
    if not isinstance(cases, dict) or type(cases.get("schema_version")) is not int or cases["schema_version"] not in (1, 2):
        return ["schema_version 1 또는 2가 필요합니다"]
    if set(cases) != {"schema_version", "cases"}:
        return ["문서의 필드가 잘못됐습니다"]
    items = cases.get("cases")
    if not isinstance(items, list) or not items:
        return ["cases 배열이 비어 있습니다"]
    known = set(skill_names())
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            errors.append("케이스 항목이 객체가 아닙니다")
            continue
        required_fields = {"id", "skill", "request", "required", "forbidden", "max_chars"}
        allowed_fields = required_fields | {"ends_with", "forbid_unprovided_advisories", "requires_followup",
                                            "artifact_policy", "expected_extensions"}
        if not required_fields.issubset(item) or set(item) - allowed_fields:
            errors.append("케이스 필드 누락 또는 알 수 없는 필드")
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
        if "forbid_unprovided_advisories" in item and type(item["forbid_unprovided_advisories"]) is not bool:
            errors.append(f"{case_id}: forbid_unprovided_advisories는 불리언이어야 합니다")
        if "requires_followup" in item and type(item["requires_followup"]) is not bool:
            errors.append(f"{case_id}: requires_followup은 불리언이어야 합니다")
        if "artifact_policy" in item and item["artifact_policy"] not in ("required", "forbidden", "conditional"):
            errors.append(f"{case_id}: artifact_policy가 잘못됐습니다")
        if "expected_extensions" in item and (type(item["expected_extensions"]) is not list or
                not item["expected_extensions"] or any(type(ext) is not str or not re.fullmatch(r"\.[a-z0-9]{1,8}", ext)
                                                       for ext in item["expected_extensions"])):
            errors.append(f"{case_id}: expected_extensions가 잘못됐습니다")
    covered = {item["skill"] for item in items
               if isinstance(item, dict) and isinstance(item.get("skill"), str)}
    for name in known:
        if name not in covered:
            errors.append(f"커버리지 누락: {name}")
    return errors


def _is_link(path):
    info = path.lstat()
    return (path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())
            or bool(getattr(info, "st_file_attributes", 0) & 0x400))


def skill_tree_hashes(skill):
    if skill not in skill_names():
        raise ValueError("unknown skill")
    root = SKILLS / skill
    if _is_link(root):
        raise ValueError("linked skill directory")
    entries = {}
    for current, dirs, files in os.walk(root, followlinks=False, onerror=lambda error: (_ for _ in ()).throw(error)):
        current = Path(current)
        dirs[:] = sorted(name for name in dirs if name != "__pycache__")
        for name in dirs + sorted(files):
            path = current / name
            if _is_link(path):
                raise ValueError("linked skill path")
            if name in dirs:
                continue
            if not path.is_file():
                raise ValueError("non-regular skill file")
            entries[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if "SKILL.md" not in entries:
        raise ValueError("missing skill file")
    return entries


def manifest(cases):
    items = []
    trees = {}
    for item in cases["cases"]:
        skill = item["skill"]
        if skill not in trees:
            trees[skill] = skill_tree_hashes(skill)
        files = trees[skill]
        request = item["request"].encode("utf-8")
        items.append({
            "id": item["id"],
            "skill": item["skill"],
            "request_sha256": hashlib.sha256(request).hexdigest(),
            "skill_sha256": files["SKILL.md"],
            "skill_files_sha256": files,
            "skill_tree_sha256": hashlib.sha256(json.dumps(files, ensure_ascii=True, sort_keys=True,
                                                            separators=(",", ":")).encode("utf-8")).hexdigest(),
            "required": item.get("required", []),
            "forbidden": item.get("forbidden", []),
            "max_chars": item.get("max_chars", 8000),
            **({"forbid_unprovided_advisories": item["forbid_unprovided_advisories"]} if "forbid_unprovided_advisories" in item else {}),
            **({"requires_followup": item["requires_followup"]} if "requires_followup" in item else {}),
            **({"ends_with": item["ends_with"]} if "ends_with" in item else {}),
            **({"artifact_policy": item["artifact_policy"]} if "artifact_policy" in item else {}),
            **({"expected_extensions": item["expected_extensions"]} if "expected_extensions" in item else {}),
        })
    return {"schema_version": 2, "cases": items}


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
    try:
        data = manifest(cases)
    except (OSError, ValueError) as exc:
        print(f"FAIL 스킬 이력 생성 실패: {exc}", file=sys.stderr)
        return 1
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    skills = sorted({item["skill"] for item in data["cases"]})
    print(f"PASS 케이스 {len(data['cases'])}건 / 스킬 {len(skills)}개")
    print("스킬:", ", ".join(skills))
    return 0


if __name__ == "__main__":
    sys.exit(main())

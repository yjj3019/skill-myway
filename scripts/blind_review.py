#!/usr/bin/env python3
"""블라인드 비교 평가용 패킷과 비공개 키를 만든다. 모델 호출·품질 판정은 하지 않는다.

사용: python3 scripts/blind_review.py --cases CASES.json \
        --candidate-1 A.json --candidate-2 B.json \
        --packet PACKET.json --key KEY.json [--seed 64hex]

케이스 형식: {"cases": [{"id", "source", "required_claims": [...], "protected_spans": [...]}]}
후보 형식: {"<id>": "<text>", ...} (케이스 id를 정확히 한 번씩 포함)
패킷: 검토자에게 주는 A/B 배치. 키: 어떤 후보가 A인지 기록한 비공개 대응표.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import secrets
import sys
from pathlib import Path

MAX_BYTES = 16 * 1024 * 1024
ALGORITHM = "hmac-sha256-case-id-v1"
DOMAIN = b"blind-review:allocation:v1\x00"
PRIVACY = (
    "블라인드 처리는 파일 메타데이터를 지우고 라벨만 섞는다. 후보 문장이나 케이스 내용에는 "
    "출처·민감정보가 남을 수 있으므로 두 파일과 비공개 키를 보호해야 한다. 의미 품질은 판정하지 않는다."
)


def read_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError(f"JSON 입력이 16 MiB를 넘습니다: {path}")
    try:
        return raw, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"JSON을 읽을 수 없습니다: {path} ({exc})") from exc


def load_cases(document):
    cases = document.get("cases") if isinstance(document, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("케이스 파일에 cases 배열이 필요합니다")
    seen = set()
    result = []
    for item in cases:
        if not isinstance(item, dict):
            raise ValueError("케이스 항목은 객체여야 합니다")
        case_id = item.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("케이스 id는 비어 있지 않고 중복되지 않아야 합니다")
        if not isinstance(item.get("source"), str):
            raise ValueError(f"케이스 {case_id}: source가 필요합니다")
        for key in ("required_claims", "protected_spans"):
            value = item.get(key, [])
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                raise ValueError(f"케이스 {case_id}: {key}는 문자열 배열이어야 합니다")
        seen.add(case_id)
        result.append({
            "id": case_id,
            "source": item["source"],
            "required_claims": list(item.get("required_claims", [])),
            "protected_spans": list(item.get("protected_spans", [])),
        })
    return result


def load_candidates(document, case_ids):
    if not isinstance(document, dict):
        raise ValueError("후보 파일은 객체여야 합니다")
    if set(document) != set(case_ids):
        missing = sorted(set(case_ids) - set(document))
        extra = sorted(set(document) - set(case_ids))
        raise ValueError(f"후보 키가 케이스와 다릅니다. 누락={missing} 추가={extra}")
    result = {}
    for case_id in case_ids:
        value = document[case_id]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"후보 {case_id}: 비어 있지 않은 문자열이어야 합니다")
        result[case_id] = value
    return result


def assignment(seed_hex, case_id):
    if not isinstance(seed_hex, str) or not re.fullmatch(r"[0-9a-f]{64}", seed_hex):
        raise ValueError("seed는 소문자 16진수 64자여야 합니다")
    digest = hmac.new(bytes.fromhex(seed_hex), DOMAIN + case_id.encode("utf-8"), hashlib.sha256).digest()
    first = digest[0] & 1
    a = 1 if first == 0 else 2
    return {"id": case_id, "A": a, "B": 3 - a}


def build(cases, candidate_1, candidate_2, seed_hex):
    assignments = [assignment(seed_hex, case["id"]) for case in cases]
    by_id = {a["id"]: a for a in assignments}
    packet_cases = []
    for case in cases:
        pick = by_id[case["id"]]
        first = pick["A"] - 1
        sources = (candidate_1, candidate_2)
        packet_cases.append({
            "id": case["id"],
            "source": case["source"],
            "required_claims": case["required_claims"],
            "protected_spans": case["protected_spans"],
            "candidates": {
                "A": sources[first][case["id"]],
                "B": sources[1 - first][case["id"]],
            },
        })
    packet = {"schema_version": 1, "privacy_caveat": PRIVACY, "cases": packet_cases}
    key = {
        "schema_version": 1,
        "privacy_caveat": PRIVACY,
        "randomization": {"algorithm": ALGORITHM, "seed": seed_hex},
        "assignments": assignments,
    }
    return packet, key


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def write_outputs(packet, key, packet_path, key_path):
    packet_bytes = (json.dumps(packet, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    key_bytes = (json.dumps(key, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    created = []
    try:
        for path, payload in ((packet_path, packet_bytes), (key_path, key_bytes)):
            handle = open(path, "xb")
            created.append((handle, path))
            handle.write(payload)
            handle.close()
    except OSError:
        for handle, path in created:
            try:
                handle.close()
            except OSError:
                pass
            try:
                Path(path).unlink()
            except OSError:
                pass
        raise
    return _digest(packet_bytes), _digest(key_bytes)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="블라인드 비교 평가 패킷과 비공개 키를 만든다")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--candidate-1", required=True)
    parser.add_argument("--candidate-2", required=True)
    parser.add_argument("--packet", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--seed", help="재현용 64자 16진수(기본: 무작위)")
    args = parser.parse_args(argv)
    try:
        _, case_doc = read_json(args.cases)
        cases = load_cases(case_doc)
        ids = [case["id"] for case in cases]
        _, cand1_doc = read_json(args.candidate_1)
        _, cand2_doc = read_json(args.candidate_2)
        cand1 = load_candidates(cand1_doc, ids)
        cand2 = load_candidates(cand2_doc, ids)
        seed = args.seed or secrets.token_hex(32)
        packet, key = build(cases, cand1, cand2, seed)
        write_outputs(packet, key, args.packet, args.key)
    except (ValueError, OSError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    print(f"패킷과 비공개 키를 만들었습니다. {PRIVACY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

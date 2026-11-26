#!/usr/bin/env python3
"""완료·검증 주장을 판정한 JSON 답변이 증거 판정 계약을 지키는지 결정적으로 검사한다.

모델이 산문 규칙을 건너뛸 수 있으므로, 이 검사는 모델에 의존하지 않고 완성된 답변을 읽어 계약 위반을 찾는다.
정답은 사람이 미리 고정한 fixture에만 있고 모델에는 보이지 않는다.

답변(JSON 객체, 키는 정확히 이 셋):
  EVIDENCE_STATUS   VERIFIED | CONTRADICTED | NOT_VERIFIED | BLOCKED   (주장 전체의 종합 판정)
  CLAIMS            [{"id": 문자열, "status": 판정, "evidence_ids": [문자열, ...]}, ...]
  REQUIRED_EVIDENCE [문자열, ...]   (종합이 VERIFIED가 아니면 다음에 필요한 증거를 1개 이상)

fixture(JSON 객체): {"claims": {"<id>": {"expected_status": 판정,
                                        "allowed_evidence": [증거 ID...], "required_evidence": [증거 ID...]}}}
  VERIFIED·CONTRADICTED가 기대값이면 required_evidence가 비어 있으면 안 된다. required는 allowed의 부분집합이다.

종합 판정의 우선순위는 CONTRADICTED > BLOCKED > NOT_VERIFIED > VERIFIED다.
  - CONTRADICTED: 관측된 반증이다. 확인 불능 뒤에 숨기면 안 되므로 가장 높다.
  - BLOCKED: 확인 자체가 막혀 아무것도 VERIFIED라고 할 수 없지만 반증을 관측한 것보다 약하다.
  - NOT_VERIFIED: 증거가 없는 상태다. 모든 주장이 VERIFIED일 때만 종합도 VERIFIED다.

이 검사는 형식과 일관성만 본다. 판정이 옳은지, 증거 ID가 실제 로그와 연결되는지(위조 가능), REQUIRED_EVIDENCE가 적절한지는
검증하지 않는다. 증거 ID의 실제 연결은 외부 수집기의 몫이며, 통과는 의미 품질이나 독립 검증을 대체하지 않는다.

종료 코드: 0 통과, 1 답변이 계약 위반(깨진 JSON 포함), 2 검사 불능(입력을 읽지 못함·fixture 오류·사용법 오류).
사용: python check_evidence_answer.py ANSWER.json FIXTURE.json
"""
import argparse
import json
import sys
from pathlib import Path

STATUSES = ("VERIFIED", "CONTRADICTED", "NOT_VERIFIED", "BLOCKED")
PRECEDENCE = ("CONTRADICTED", "BLOCKED", "NOT_VERIFIED")  # 이 순서로 하나라도 있으면 종합이 된다
ANSWER_KEYS = {"EVIDENCE_STATUS", "CLAIMS", "REQUIRED_EVIDENCE"}
CLAIM_KEYS = {"id", "status", "evidence_ids"}
RULE_KEYS = {"expected_status", "allowed_evidence", "required_evidence"}
MAX_BYTES = 1024 * 1024


class FixtureError(ValueError):
    """검사 불능: fixture가 스키마에 맞지 않는다."""


def _no_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"중복 키 {key!r}")
        seen[key] = value
    return seen


def loads(text):
    return json.loads(text, object_pairs_hook=_no_duplicate_keys)


def _string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate_fixture(fixture):
    """fixture 스키마를 검사하고 문제가 있으면 FixtureError를 던진다."""
    if not isinstance(fixture, dict) or set(fixture) != {"claims"}:
        raise FixtureError("fixture는 키 'claims' 하나만 가진 객체여야 한다")
    claims = fixture["claims"]
    if not isinstance(claims, dict) or not claims:
        raise FixtureError("claims는 비어 있지 않은 객체여야 한다")
    for cid, rule in claims.items():
        if not isinstance(rule, dict) or set(rule) != RULE_KEYS:
            raise FixtureError(f"{cid}: 규칙의 키는 정확히 {sorted(RULE_KEYS)}여야 한다")
        if rule["expected_status"] not in STATUSES:
            raise FixtureError(f"{cid}: expected_status가 올바르지 않다")
        allowed, required = rule["allowed_evidence"], rule["required_evidence"]
        if not _string_list(allowed) or not _string_list(required):
            raise FixtureError(f"{cid}: 증거 목록은 문자열 배열이어야 한다")
        if len(allowed) != len(set(allowed)) or len(required) != len(set(required)):
            raise FixtureError(f"{cid}: 증거 목록에 중복이 있다")
        if not set(required) <= set(allowed):
            raise FixtureError(f"{cid}: required_evidence는 allowed_evidence의 부분집합이어야 한다")
        if rule["expected_status"] in ("VERIFIED", "CONTRADICTED") and not required:
            raise FixtureError(f"{cid}: {rule['expected_status']}에는 required_evidence가 필요하다")


def overall_status(statuses):
    for status in PRECEDENCE:
        if status in statuses:
            return status
    return "VERIFIED"


def check(answer, fixture):
    """계약 위반 코드 목록을 반환한다. fixture는 이미 검증됐다고 가정한다."""
    if not isinstance(answer, dict):
        return ["INVALID_ANSWER: 답변이 JSON 객체가 아니다"]
    if set(answer) != ANSWER_KEYS:
        return [f"INVALID_FIELDS: 키는 정확히 {sorted(ANSWER_KEYS)}여야 한다"]
    claims = answer["CLAIMS"]
    if not isinstance(claims, list) or not claims:
        return ["MISSING_CLAIMS: CLAIMS는 비어 있지 않은 배열이어야 한다"]

    expected = fixture["claims"]
    errors, seen, valid_statuses, structure_ok = [], set(), [], True
    for position, claim in enumerate(claims, 1):
        if not isinstance(claim, dict) or set(claim) != CLAIM_KEYS:
            errors.append(f"INVALID_CLAIM: {position}번째 주장의 키가 올바르지 않다")
            structure_ok = False
            continue
        cid, status, refs = claim["id"], claim["status"], claim["evidence_ids"]
        if not isinstance(cid, str):
            errors.append(f"INVALID_CLAIM_ID: {position}번째 주장의 id가 문자열이 아니다")
            structure_ok = False
            continue
        if cid not in expected:
            errors.append(f"UNKNOWN_CLAIM: {cid}")
            structure_ok = False
            continue
        if cid in seen:
            errors.append(f"DUPLICATE_CLAIM: {cid}")
            structure_ok = False
            continue
        seen.add(cid)
        if not isinstance(status, str) or status not in STATUSES:
            errors.append(f"INVALID_STATUS: {cid}")
            structure_ok = False
            continue
        if not _string_list(refs):
            errors.append(f"INVALID_EVIDENCE_IDS: {cid}")
            structure_ok = False
            continue
        valid_statuses.append(status)
        rule = expected[cid]
        if len(refs) != len(set(refs)):
            errors.append(f"DUPLICATE_EVIDENCE: {cid}")
        if not set(refs) <= set(rule["allowed_evidence"]):
            errors.append(f"UNKNOWN_EVIDENCE: {cid}")
        if status in ("VERIFIED", "CONTRADICTED") and not set(rule["required_evidence"]) <= set(refs):
            errors.append(f"UNSUPPORTED_VERDICT: {cid}는 {status}이지만 필요한 증거가 없다")
        if status != rule["expected_status"]:
            errors.append(f"WRONG_VERDICT: {cid}는 {status}, 기대값은 {rule['expected_status']}")
    if seen != set(expected):
        errors.append(f"MISSING_CLAIMS: 빠진 주장 {sorted(set(expected) - seen)}")
        structure_ok = False

    overall = answer["EVIDENCE_STATUS"]
    if overall not in STATUSES:
        errors.append("INVALID_OVERALL_STATUS: EVIDENCE_STATUS가 올바르지 않다")
    elif structure_ok:
        # 개별 주장 구조가 깨졌으면 종합 일관성은 판단하지 않는다(오류가 연쇄해 원인을 가리는 것을 막는다).
        if overall != overall_status(valid_statuses):
            errors.append(f"INCONSISTENT_OVERALL_STATUS: 개별 판정의 종합은 {overall_status(valid_statuses)}인데 {overall}이다")
    required = answer["REQUIRED_EVIDENCE"]
    if not _string_list(required) or any(not item.strip() for item in required):
        errors.append("INVALID_REQUIRED_EVIDENCE: 비어 있지 않은 문자열 배열이어야 한다")
    elif overall in STATUSES and overall != "VERIFIED" and not required:
        errors.append("MISSING_NEXT_EVIDENCE: 종합이 VERIFIED가 아니면 필요한 증거를 1개 이상 적어야 한다")
    return errors


def _read(path):
    if path.stat().st_size > MAX_BYTES:
        raise OSError("파일이 너무 크다")
    return path.read_text(encoding="utf-8-sig")


def main(argv=None):
    cli = argparse.ArgumentParser(description="증거 판정 JSON 답변이 계약을 지키는지 검사한다(형식과 일관성만).")
    cli.add_argument("answer", type=Path, help="검사할 답변 JSON")
    cli.add_argument("fixture", type=Path, help="사람이 고정한 기대값 JSON")
    args = cli.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # 콘솔 인코딩이 한국어를 못 담아도 출력이 죽지 않게 한다
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    try:
        answer_text = _read(args.answer)
        fixture = loads(_read(args.fixture))
        validate_fixture(fixture)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"CHECKER_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        answer = loads(answer_text)
    except ValueError as exc:
        print(f"위반 INVALID_JSON: {exc}")
        print("EVIDENCE-ANSWER: FAIL (1)")
        return 1
    violations = check(answer, fixture)
    lines = [f"위반 {item}" for item in violations]
    verdict = "FAIL" if violations else "PASS"
    print("\n".join(lines + [f"EVIDENCE-ANSWER: {verdict} ({len(violations)})"]))
    if violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

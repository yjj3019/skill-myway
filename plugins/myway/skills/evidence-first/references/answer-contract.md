# 증거 판정 응답 계약

완료·검증 주장을 판정해 달라는 요청에서 판정과 증거를 분리해 보고하는 계약이다. 일반 질문, 구현, 설명에는 이 형식을 강제하지 않는다. 형식이 지정된 평가나 기계 검사 요청이면 아래 JSON을, 그 밖에는 같은 항목을 읽기 쉬운 문장과 표로 적는다.

## 판정 값

| 값 | 의미 |
|---|---|
| VERIFIED | 요구 범위와 일치하는 증거가 제시됐고 그 증거로 주장이 확인됐다 |
| CONTRADICTED | 제시된 증거가 주장과 어긋난다(실패 로그, 실행 0건, 전부 skip 등) |
| NOT_VERIFIED | 증거가 없거나 확인 범위를 벗어난다 |
| BLOCKED | 증거를 읽거나 확인하는 것이 권한·접근 문제로 막혔다 |

`NOT_VERIFIED`와 `BLOCKED`는 주장이 거짓이라는 뜻이 아니다. 증거가 없거나 범위를 벗어난 주장은 VERIFIED로 쓰지 않는다. 서술문에서는 "NOT VERIFIED"나 "미검증"이라고 쓰고, 밑줄이 있는 `NOT_VERIFIED`는 JSON 같은 기계 값에만 쓴다. 두 표기는 같은 뜻이다. 이 문서의 `UNVERIFIED`(지침 충돌 판정, 기동 점검의 관측 상태)는 별개의 축이며 이 계약의 판정 값이 아니다.

## 답변 형식 (평가·기계 검사용)

```json
{
  "EVIDENCE_STATUS": "NOT_VERIFIED",
  "CLAIMS": [
    {"id": "tests", "status": "NOT_VERIFIED", "evidence_ids": []},
    {"id": "deployment", "status": "NOT_VERIFIED", "evidence_ids": []}
  ],
  "REQUIRED_EVIDENCE": [
    "테스트 명령, 실행 수, 실패 수, skip 수",
    "배포 대상 버전과 상태 확인 기록"
  ]
}
```

- `EVIDENCE_STATUS`는 개별 판정의 종합이다. 우선순위는 CONTRADICTED > BLOCKED > NOT_VERIFIED > VERIFIED이고, 모든 주장이 VERIFIED일 때만 VERIFIED다.
- `evidence_ids`는 요청에 실제로 주어진 증거의 ID만 쓴다. 지어낸 ID를 쓰지 않는다. VERIFIED·CONTRADICTED에는 해당 증거 ID가 있어야 한다.
- 종합이 VERIFIED가 아니면 `REQUIRED_EVIDENCE`에 다음에 필요한 증거를 1개 이상 적는다.

## 결정적 검사

```text
python scripts/check_evidence_answer.py answer.json fixture.json
```

fixture는 사람이 미리 고정하고 모델에는 보여 주지 않는다.

```json
{"claims": {"tests": {"expected_status": "NOT_VERIFIED", "allowed_evidence": [], "required_evidence": []},
            "deployment": {"expected_status": "NOT_VERIFIED", "allowed_evidence": [], "required_evidence": []}}}
```

종료 코드는 0 통과, 1 답변의 계약 위반(깨진 JSON 포함), 2 검사 불능(입력을 읽지 못함, fixture 오류)이다.

## 한계

- 검사는 형식과 일관성만 본다. 판정이 옳은지, REQUIRED_EVIDENCE가 적절한지는 보지 않는다.
- 증거 ID가 허용 목록 안의 문자열이면 통과한다. 그 ID가 실제 로그와 연결되는지는 외부 수집기가 관리해야 한다. 모델이 쓴 ID는 증거가 아니다.
- 검사기를 실행하지 못했거나 접근이 막혔으면 통과로 보고하지 않고 미실행으로 적는다. 계약 통과는 의미 품질이나 독립 검증을 대체하지 않는다.

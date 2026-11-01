# 스킬 평가 결과 (2026-11-01)

가상 테스트(1단계)와 실제 모델 테스트(2단계)로 10개 스킬의 형식·필수 요소를 확인했다. 문장 품질과 사실 정확성은 자동으로 판정하지 않았다.

## 방법

| 항목 | 내용 |
|---|---|
| 입력 | `tests/eval_cases/cases.json` — 스킬 10개 × 1케이스, 모두 가상 값 |
| 모델 | Claude Code 2.1.316 headless (`claude -p --plugin-dir plugins/myway`) |
| 실행 조건 | 빈 임시 작업 디렉터리(저장소 지침·훅 차단), 케이스 타임아웃 240초 |
| 자동 검사 | 필수 요소(동의어 허용), 금지 패턴, 최대 길이 |
| 판정 한계 | 케이스당 1회 실행, 모델 1종. 의미 품질·사실 정확성·반복 안정성은 미판정 |

## 1단계 — 가상 테스트

`python3 scripts/simulate_eval.py`

- 케이스 스키마·id 중복·스킬 커버리지·민감 패턴 검사: **PASS 10/10**
- 케이스별 요청 해시와 `SKILL.md` 해시를 manifest로 기록
- 모델 호출 없음

## 2단계 — 실제 모델 실행

`python3 scripts/run_eval.py --platform claude`

| 케이스 | 스킬 | 시간 | 출력 | 자동 검사 |
|---|---|---|---|---|
| writing-01 | writing | 40.3s | 574자 | PASS |
| office-docs-01 | office-docs | 27.4s | 844자 | PASS |
| rhel-cve-01 | rhel-cve | 39.7s | 2,306자 | PASS |
| admission-helper-01 | admission-helper | 25.1s | 665자 | PASS |
| devlog-01 | devlog | 23.3s | 389자 | PASS |
| incident-rca-01 | incident-rca | 36.4s | 2,338자 | PASS |
| code-review-01 | code-review | 36.8s | 3,316자 | PASS |
| prompt-engineering-01 | prompt-engineering | 35.6s | 2,444자 | PASS |
| research-brief-01 | research-brief | 30.8s | 1,584자 | PASS |
| evidence-first-01 | evidence-first | 25.2s | 1,095자 | PASS |

**결과: 10/10 자동 검사 통과.**

## 반복 과정에서 찾은 문제와 수정

| 회차 | 결과 | 원인 | 수정 |
|---|---|---|---|
| 1차 | 9/10 | admission-helper가 "결과" 대신 "환산 점수 86.5"로 서술 | 필수 검사를 동의어·수치 허용으로 변경 |
| 2차 | 8/10 | 저장소 안에서 실행해 프로젝트 지침·훅이 개입(writing이 글 대신 저장소 상태를 설명), "미검증" 대신 "UNVERIFIED" 사용 | 빈 임시 작업 디렉터리에서 실행 + 동의어 허용 |
| 3차 | 10/10 | — | — |

## 품질 관찰 (정식 채점 아님)

- `rhel-cve`: 제공 값 외 수치를 만들지 않고, fix_state와 RHSA가 모순되면 미확인으로 남겼다.
- `code-review`: 심각도·근거·수정안·Validation Gap을 포함하고, 테스트를 실행하지 않았음을 밝혔다.
- `incident-rca`: 타임라인·가설·미확인을 분리하고, 시작 시각과 관측 시각의 간격 모순을 지적했다.
- `evidence-first`: skip 1건을 완료 미충족으로 판정하고 UNVERIFIED로 표시했다.
- `writing`: 제공된 정보만 사용하고 요청한 끝맺음을 지켰다.

## 한계

- 케이스당 1회, 모델 1종이라 반복 안정성과 모델 간 차이는 모른다.
- 자동 검사는 형식·필수 요소만 본다. 문장 품질·사실 정확성은 사람 판정이 필요하다.
- Codex·Grok Build의 실제 모델 실행은 하지 않았다(설치·스킬 인식은 별도 확인).
- 실제 업무 데이터·계정·조직 정보는 사용하지 않았다. 입력은 모두 가상 값이다.

## 재현

```sh
python3 scripts/simulate_eval.py
python3 scripts/run_eval.py --platform claude
```

원본 출력과 `summary.json`은 `eval-results/`(저장소에서 제외)에 남는다.

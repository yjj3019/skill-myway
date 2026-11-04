---
name: rhel-cve
description: Red Hat/RHEL CVE와 RHSB를 조사해 Confluence용 한국어 보안 리포트를 작성한다. CVE 한 건·여러 건 또는 RHSB의 영향 제품, fix_state, 수정 버전, RHSA와 근거를 확인한다. RHEL 취약점 점검, CVE 리포트, 영향도 판정, EPSS, KEV 요청에도 사용한다.
---

# Red Hat CVE 조사 및 리포트

고정 리포트와 조사·검증을 하나로 합친 스킬. 보고서 요청은 단건·다건 또는 RHSB를 한 파일로 작성한다.

## 1. 모드 판별 (입력 기준, 표현 무관)

| 입력 | 모드 | 산출물 | 읽을 파일 |
|---|---|---|---|
| CVE ID 1개 또는 Red Hat CVE URL | 리포트 | `CVE-YYYY-NNNNN_리포트.md` | data-sourcing, judgment-rules, report-format, report-example |
| CVE ID 여러 개 또는 RHSB URL | 통합 리포트 | `RHEL_CVE_리포트_YYYYMMDD.md` | data-sourcing, judgment-rules, report-format, report-example |
| 사용자가 다건 요약 목록을 명시적으로 요청 | 다건 요약 | `CVE_요약_YYYYMMDD_{N}건.md` | data-sourcing, judgment-rules, batch-summary |
| 특정 질문 ("RHEL 8 영향 있어?", "이 버전이 수정 버전 맞아?", "이 설명 무슨 CVE야?") | 검증 답변 | 대화 응답 (파일 없음) | data-sourcing, judgment-rules |

- RHSB URL이면 먼저 원문에서 관련 CVE와 RHSA를 확인한다. 문서에 접근할 수 없으면 범위를 추측하지 않는다.
- 검증 질문이 CVE ID 1개와 함께 오면 질문에 먼저 답한다. 리포트는 사용자가 원할 때만 이어서 만든다.
- 다건 입력은 중복을 제거한다. 중복 제거 결과 1건이면 단건 리포트.
- 사용자가 대상 RHEL 버전을 지정하면(예: "RHEL 6·7 기준") 모든 판정을 그 버전으로 한정한다.

## 2. 실행 환경

이 스킬은 claude.ai, Claude Code, Codex, Grok 등 Agent Skills 표준을 읽는 에이전트에서 동작한다.

- 스크립트 경로(`scripts/…`)와 참조 경로(`references/…`)는 이 SKILL.md가 있는 디렉터리 기준이다.
- 산출물 저장 위치: claude.ai는 `/mnt/user-data/outputs/`에 저장 후 `present_files`로 제공. 그 외 환경은 현재 작업 디렉터리에 저장하고 경로를 알린다.
- 웹 조회: claude.ai는 `web_search`/`web_fetch`, CLI 에이전트는 `curl` 또는 자체 웹 도구를 쓴다. 환경별 차이는 5절과 `references/data-sourcing.md` 0절.

## 3. 공통 절차

1. CVE ID 정규화 (`CVE-YYYY-NNNNN`, URL이면 마지막 경로에서 추출)
2. `references/data-sourcing.md` 순서대로 수집
3. `references/judgment-rules.md` 규칙으로 판정
4. 모드별 산출물 작성
5. 검증: 통합·단건 리포트는 `scripts/check_report.py` 통과 후 값과 출처를 수동 대조한다.
6. 대화 응답에 "값별 출처·수집 시점"과 미확인 항목을 명시

## 4. 절대 규칙 (요약 — 상세는 references)

**데이터**
- 추측 금지. 원자료에 없는 제품·버전·RHSA·점수는 쓰지 않는다. 확인 실패와 실제 데이터 없음을 구분한다.
- CVSS 점수의 버전과 출처는 원자료로 확인한 경우만 붙인다. 버전이 없으면 `버전 미확인`으로 표시하며 점수만 보고 v3로 추정하지 않는다.
- 제품 판정 1차 소스는 Hydra. CSAF/VEX는 x86_64 NVR 보강용.
- Hydra JSON과 XML이 다르면 CONFLICT로 표시하고 양쪽 값을 모두 보고한다. 기본 채택은 JSON.
- `product_name` 정확 일치 항목만 해당 RHEL 버전 판정으로 쓴다. EUS/ELS/AUS, JBCS, RHEL AI 등은 별개 제품.
- Statement 산문만으로 제품 상태를 추정하지 않는다.
- NVR epoch(`0:`, `1:`)는 모든 산출물에서 제거한다.
- "Red Hat 미추적"과 "영향 없음(Not affected)"을 구분한다.
- EPSS는 api.first.org 먼저 시도, 실패·CVE 불일치 시 GitHub 미러로 폴백.
- 출처에는 실제로 조회한 URL을 적는다. 조회하지 않은 URL을 관례적으로 적지 않는다.
- 2차 소스(OpenCVE, OSV 등)로 대체한 값은 대화 응답에 소스와 수집 시점을 밝힌다.

**리포트 형식** — `references/report-format.md`의 Confluence용 제목·섹션·표 순서를 따른다. 확인되지 않은 데이터는 임의로 채우지 않는다.

**조용한 생략 금지**
- RHSA 커버리지 축소, 소스 접근 실패, CONFLICT, 2차 소스 사용은 반드시 드러낸다.

## 5. 환경별 네트워크 제약

| 대상 | claude.ai `bash_tool` curl | claude.ai `web_fetch` | CLI 에이전트 curl (Claude Code, Codex, Grok) |
|---|---|---|---|
| access.redhat.com (CVE 페이지, Hydra, errata) | 차단 | 사용 (URL 선노출 필요) | 사용 |
| security.access.redhat.com (CSAF/VEX, OSV) | 차단 | 사용 (URL 선노출 필요) | 사용 |
| cveawg.mitre.org | 차단 | 사용 (URL 선노출 필요) | 사용 |
| api.first.org (EPSS) | 차단 | 대부분 거부 | 사용 |
| raw.githubusercontent.com (EPSS 미러, KEV) | 사용 | — | 사용 |

- claude.ai `web_fetch`는 이전 검색·fetch 결과에 나온 URL만 연다. 우회 절차는 `references/data-sourcing.md` 0절.
- CLI 에이전트는 Hydra JSON/XML과 CSAF를 `curl -sL`로 직접 받는다. 사내망·프록시로 막히면 claude.ai 절차로 전환한다.
- 폐쇄망이면 수집 불가 항목을 "미확인"으로 두고 사유를 밝힌다. 실제 조회했으나 값이 없는 경우만 "정보 없음"으로 구분한다.

## 6. 파일 구성

- `references/data-sourcing.md` — 소스 우선순위, 수집 절차, web_fetch 우회, verbatim 프롬프트
- `references/judgment-rules.md` — fix_state 어휘·번역, product_name, CONFLICT, 미추적 판별, 검증 질문 처리
- `references/report-format.md` — 단건·다건 Confluence 리포트 형식
- `references/report-example.md` — 규칙에 맞춘 완성본 예시
- `references/batch-summary.md` — 다건 요약 형식, 서브에이전트 배치, 검산식
- `scripts/epss_kev.py` — EPSS(api.first.org → 미러 폴백)·KEV 일괄 조회 (JSON 출력, 표준 라이브러리만 사용)
- `scripts/check_report.py` — 리포트 구조 자동 검사 (사실 검증은 별도)

## 특정 정보가 필요할 때

기관명, 고객명, 호스트명, 주소, 계정, 내부 식별자처럼 특정 대상을 가리키는 값이 필요하면 추측하거나 파일에 미리 적지 않는다. 필요한 항목을 모아 한 번에 질문하고, 받은 답은 이번 산출물과 세션에만 쓴다. 이 스킬의 파일과 저장소에는 되쓰지 않는다. 자격증명과 개인정보는 요청하지 않는다.

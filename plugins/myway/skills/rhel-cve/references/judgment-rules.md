# 판정 규칙

## 1. product_name 정확 일치

- RHEL 버전 판정은 `product_name`이 정확히 `Red Hat Enterprise Linux N`인 항목만 쓴다.
- 아래는 별개 제품·스트림으로 구분해 기재한다.
  - `Red Hat Enterprise Linux N.M Extended Update Support` / `… Update Services for SAP Solutions` / `… Advanced Mission Critical Update Support` — EUS·E4S·AUS 스트림
  - `Red Hat Enterprise Linux 6/7 Extended Lifecycle Support` — ELS. 표준 판정에는 반영하지 않되, ELS 계약 서버는 실제 패치가 있을 수 있음을 명시
  - `JBoss Core Services on RHEL 7`, `Red Hat Enterprise Linux AI`, `Ansible Automation Platform … for RHEL 8` — 별도 제품
- 관심 버전 항목이 하나도 없으면 "영향 없음"이라 쓰지 않는다. 실제 존재하는 product_name 목록을 기재한다.

## 2. RPM EVR 비교와 표시

- 원자료의 epoch·version·release·architecture를 원본 필드로 보존한다. 비교가 필요하면 RPM EVR 규칙을 적용하고, 도구·버전·두 입력값·결과를 근거로 남긴다. 단순 문자열·숫자 비교나 epoch 제거 뒤의 비교로 판정하지 않는다.
- Epoch를 제거하는 정규식은 비교 도구가 아니다. 실제 산출물에 epoch를 생략해야 하는 형식이면 EVR 비교를 끝낸 뒤 표시용 사본만 변환하고, 원본 EVR과 비교 결과는 작업 근거에 보존한다.

```text
비교용 원본: 1:1.0-1  vs  0:2.0-1
표시용 NVR 변환은 판정 이후에만 수행
```

- 고객 형식상 epoch를 생략할 때는 가능한 범위에서 epoch가 표기에서 생략됐다는 점을 밝힌다. 사람이 원문과 대조할 수 있도록 소스 NVR/EVR과 비교 근거를 보관한다.

## 3. fix_state 어휘와 한국어 표기

| 원문 | 리포트·요약 표기 | 의미 | 실무 함의 |
|---|---|---|---|
| (affected_release에 RHSA 존재) | 수정됨(Fixed) | 패치 발행 | 해당 NVR 이상으로 업데이트 |
| Affected | 영향 있음(Affected) | 영향 확인, 패치 미발행 | 완화책 적용, 패치 대기 |
| Fix deferred | 패치 보류(Fix deferred) | 영향 확인, 일정 미정 | 노출 축소로 대응 |
| Will not fix | 패치 계획 없음(Will not fix) | 영향 확인, 수정 안 함 | 완화책 또는 구성 변경 |
| Out of support scope | 지원 범위 밖(Out of support scope) | 지원 종료 브랜치, 평가 안 함 | "영향 없음" 아님. 마이그레이션 근거 |
| Under investigation | 조사 중(Under investigation) | 평가 진행 중 | 재확인 필요 |
| Not affected | 영향 없음(Not affected) | 평가 결과 해당 없음 | 조치 불필요 |

CSAF justification 번역: `vulnerable_code_not_present` → 취약한 코드 없음, `component_not_present` → 컴포넌트 없음, `vulnerable_code_not_in_execute_path` → 실행 경로에 없음, `inline_mitigations_already_exist` → 기존 완화 조치 존재.

같은 칸에 Out of support scope와 Not affected를 함께 넣지 않는다.

## 4. JSON·XML CONFLICT

1. 두 값이 다르면 CONFLICT로 표시하고 양쪽 값을 모두 보고한다.
2. 기본 채택은 JSON. 사용자가 소스를 지정하면 그 소스로 판정한다.
3. 산출물에는 채택 값을 쓰고 불일치를 드러낸다(리포트는 패키지 표의 "비고" 또는 4장에 "JSON 기준, XML은 {값}", 요약 리스트는 비고).
4. Statement, affected_release의 RHSA 유무를 방증으로 제시한다.
5. 확정이 필요하면 Red Hat Product Security 문의를 권고한다.

## 5. Statement·Description 처리

- Statement 산문만으로 제품 상태를 추정하지 않는다. 방증으로만 쓴다.
- Description은 영문 원문을 보관하고, 한정어("statically linked", "unprivileged", 옵션 플래그, 조건절)를 번역에서 빠뜨리지 않는다.
- Red Hat Description과 CNA(cve.org) Description이 다르면 Red Hat 원문 기준으로 쓰고 CNA 원문의 구체 정보(함수명·파일명)는 보강 용도로 쓴다.

## 6. 미추적과 영향 없음

| 상황 | 표기 |
|---|---|
| Red Hat CVE 페이지·Hydra 모두 NOTFOUND, RHEL 무관 근거 있음 | Red Hat 미추적 — 근거: … |
| NOTFOUND, 근거 불충분 | 미확인 — Red Hat 포털 직접 확인 필요 |
| EXISTS, 모든 package_state가 Not affected | 영향 없음(Not affected) |
| EXISTS, package_state·affected_release 모두 비어 있음 | 평가 데이터 없음 |

## 8. 이상 데이터 판정 (1.10.x 신규)

Red Hat이 지정한 **수정 빌드**가 아래 중 하나에 해당하면 리포트 4장에 **"Red Hat 데이터 특이사항"**으로 기록하고, 패키지 표 비고에도 표시한다. 이 경우에도 Red Hat 값을 표에 그대로 둔다.

| 특이사항 | 판정 조건 |
|---|---|
| 수정 빌드의 errata 발행일이 CVE 공개일보다 이르다 | 발행일 < public_date |
| 수정 빌드의 업스트림 버전이 업스트림 수정 버전보다 낮다 | Red Hat NVR 버전 < 업스트림 수정 버전 |
| 같은 패키지의 이후 errata에 해당 CVE가 수록되지 않는다 | 이후 RHSA의 CVE 목록에 부재 |

- 비고 표기: "업스트림 수정(x.y.z)보다 이전 버전"처럼 구체적으로 쓴다.
- 실무 권고(스트림 최신 빌드 적용 등)를 덧붙일 때는 "버전 비교에 근거한 판단이며 Red Hat 공지 문구 아님"을 함께 적는다.
- 가상 예: Red Hat 지정 수정 빌드가 `pkg-a-1.2.3-4.el9_1.x86_64`, 별도 확인한 업스트림 수정 버전이 `1.2.4`이면, RPM 비교 도구와 비교 근거를 기록하고 결과가 실제로 이전일 때만 특이사항으로 분류한다.

## 9. KEV 등재와 출처 구분

- CISA KEV의 `vulnerabilityName`이 다른 벤더 제품(예: Apple)을 가리키면, 그 사실과 Red Hat 패키지가 같은 코드를 쓰는지 여부를 구분해 적는다. KEV 등재만으로 Red Hat 제품의 악용을 단정하지 않는다.
- Red Hat 공지에 악용 사례가 없으면 "Red Hat 공지에는 악용 사례가 명시되어 있지 않습니다. 악용 근거는 CISA KEV 등재입니다."처럼 출처를 나눠 쓴다.

## 10. 검증 질문 모드

- **영향 여부**: 해당 product_name 항목의 fix_state와 affected_release를 근거로 "해당/비해당 + 근거"를 답한다.
- **설명문 대조**: Red Hat 원문과 구 단위로 비교해 누락·추가된 한정어를 지적한다. 일치하는 부분도 밝혀 과장하지 않는다.
- **버전 대조**: `web_search "{NVR}" RHSA`로 RHSA·제품·발행일을 특정하고 errata SRPM 목록으로 재확인한다. epoch를 보존한 원본 EVR을 기준으로 비교하며, epoch 차이만으로 불일치라거나 일치라고 결론내리지 않는다. RPM 비교 기준과 근거를 확인한다.
- **외부 자료 검증**: 사용자가 가져온 자료(워크시트, 타 AI 산출물)의 주장은 직접 재조회해 검증한다. 불일치 시 어느 쪽이 틀렸는지 근거와 함께 보고한다.
- **설명만 주어진 경우**: 핵심 용어(함수명, 컴포넌트, 조건절)로 검색해 후보 CVE를 찾고 Red Hat 원문으로 확정한다. 후보가 여럿이면 제시하고 사용자에게 확정을 요청한다.
- 답은 "일치/불일치(해당/비해당) + 근거"로 짧게. 얼버무리지 않는다.

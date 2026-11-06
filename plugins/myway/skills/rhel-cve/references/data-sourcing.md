# 데이터 수집 절차

모든 모드 공통. 순서대로 시도하고, 실패한 단계는 실패 사실을 기록한다. 세션 시작 시 Hydra 직접 조회를 한 번 시도한 뒤 실패하면 아래 우회 경로로 전환한다. 같은 요청을 다른 명령으로 반복 시도하지 않는다.

환경 제약 요약:

| 대상 | 셸 curl | 웹 조회 도구 |
|---|---|---|
| access.redhat.com, security.access.redhat.com | 환경에 따라 프록시 차단 | 사용 (일부 환경은 이전 검색·조회 결과에 나온 URL만 열림) |
| api.first.org | 자주 차단 | 대부분 거부 |
| raw.githubusercontent.com | 사용 | — |

URL 선노출 제약이 있는 환경에서는 `"{CVE} Red Hat"`, `"{RHSA} {패키지}"`로 먼저 검색해 URL을 노출시킨 뒤 조회한다.

RHSB가 입력이면 RHSB 본문을 먼저 확인해 포함된 CVE와 RHSA를 식별한다. CVE가 입력이면 RHSB 존재 여부를 확인한다. 접근하지 못한 RHSB의 범위는 추측하지 않는다.

## 0. 환경별 조회 방법 (먼저 읽을 것)

### CLI 에이전트 (Claude Code, Codex, Grok 등)

access.redhat.com, security.access.redhat.com, cveawg.mitre.org, api.first.org를 `curl -sL`로 직접 조회한다. 원시 JSON/XML을 받으므로 verbatim 프롬프트(2-2절) 없이 `python3 -c`나 `jq`로 필드를 추출한다.

```bash
curl -sL "https://access.redhat.com/hydra/rest/securitydata/cve/CVE-YYYY-NNNNN.json" -o hydra.json
curl -sL "https://access.redhat.com/hydra/rest/securitydata/cve/CVE-YYYY-NNNNN.xml"  -o hydra.xml
```

HTTP 404는 NOTFOUND, 403·연결 실패는 네트워크 제약으로 보고 아래 claude.ai 절차 또는 대체 소스로 전환한다.

### claude.ai

`web_fetch`는 **이전 `web_search`/`web_fetch` 결과에 등장한 URL만** 연다. 직접 조립한 URL은 `PERMISSIONS_ERROR`("This URL was not in any prior search or fetch result")로 거부된다.

우회 순서:
1. `web_search "{CVE-ID}"` → `web_search "{CVE-ID} Red Hat {패키지명}"` 순으로 검색해 access.redhat.com·bugzilla.redhat.com URL을 노출시킨다.
2. 노출된 URL을 `web_fetch`한다. fetch한 페이지 안의 링크도 이후 fetch 가능해진다(예: OpenCVE 페이지 → access.redhat.com CVE 페이지·Bugzilla 링크).
3. Hydra·CSAF 원시 API URL은 검색에 거의 색인되지 않는다. 한 번은 직접 시도하고, 거부되면 아래 대체 소스로 간다.

| 필요한 데이터 | 1차 | 대체 (1차 불가 시) |
|---|---|---|
| package_state / affected_release | Hydra JSON·XML | OpenCVE `app.opencve.io/cve/{CVE-ID}` — Red Hat Hydra JSON을 원문 그대로 포함(수집 시점 확인 필수) |
| x86_64 NVR | CSAF/VEX JSON | `security.access.redhat.com/data/osv/{RHSA-ID}.json`, `api.osv.dev/v1/vulns/{RHSA-ID}`, errata 페이지 |
| cve.org 레코드 | `cveawg.mitre.org/api/cve/{CVE-ID}` | OpenCVE의 MITRE JSON, `osv.dev/vulnerability/{CVE-ID}` |

대체 소스를 쓰면 산출물 출처(8절)와 대화 응답 양쪽에 "소스명 + 해당 소스의 수집·갱신 시점"을 적고, 1차 소스 재확인을 권고한다.

## 1. Red Hat CVE 페이지 (필수)

`https://access.redhat.com/security/cve/{CVE-ID}`

| 응답 | 판정 |
|---|---|
| Description/Statement/CVSS 본문 | EXISTS |
| 명시적 404, "we could not find" | NOTFOUND |
| JS 필요 안내문만 있는 셸 | 보류 → Hydra(또는 대체 소스)로 확정 |

EXISTS면 원문 그대로 보관:
- Description (영문 원문. 한정어 하나가 취약 범위를 바꾼다)
- Statement (심각도 근거, 제품별 비영향 사유 — 버전 판정의 방증)
- Mitigation (구체 조치인지, "not available … do not meet the Red Hat Product Security criteria" 보일러플레이트인지 구분)
- CVSS v3 Score Breakdown: Red Hat / NVD / cve.org 각각의 점수·벡터
- CWE, 공개일, Security Bulletin(RHSB) 존재 여부

주의: 이 페이지의 제품별 상태표(Affected Products)는 JS 위젯이라 `web_fetch` 결과에서 빠지는 경우가 많다. 제품 상태는 반드시 2절에서 확인한다.

RHSB가 있으면(`access.redhat.com/security/vulnerabilities/RHSB-YYYY-NNN`) 반드시 연다. 영향 제품·원인·완화 절차가 CVE 페이지보다 상세하다.

## 2. Hydra Security Data (필수, 제품 판정 1차 소스)

```
JSON : https://access.redhat.com/hydra/rest/securitydata/cve/{CVE-ID}.json
XML  : https://access.redhat.com/hydra/rest/securitydata/cve/{CVE-ID}.xml
```

- `package_state[]`: product_name / fix_state / package_name — 미수정 상태 제품
- `affected_release[]`: product_name / advisory / package / release_date — 패치 발행 제품
- `bugzilla`, `threat_severity`, `public_date`, `cvss3`, `statement`, `mitigation`

두 배열은 서로 다른 이야기를 한다(예: package_state에서 redis는 Not affected, affected_release에는 valkey 패치). 합치지 말고 각각 기록한다.

### 2-1. JSON·XML 교차검증

결론을 바꾸는 항목(사용자 관심 버전의 fix_state, Affected/Fix deferred/Under investigation 판정)은 JSON과 XML을 둘 다 조회한다. JSON과 XML의 fix_state가 서로 다른 경우가 실제로 있다(예: 한쪽은 Affected, 다른 쪽은 Not affected).

### 2-2. verbatim 인용 프롬프트

`web_fetch` 요약 모델이 값을 패러프레이즈·누락하지 않도록 원문 나열을 강제한다.

전수 나열:
> List EVERY entry in the package_state array as `product_name | fix_state | package_name`, and EVERY entry in the affected_release array as `product_name | advisory | package | release_date`. Output them verbatim as a plain list. Do not summarize, do not omit entries, do not deduplicate.

단일 항목 확정:
> Find the entry in package_state where product_name is "Red Hat Enterprise Linux 7". Quote that single JSON object character-for-character exactly as it appears in the raw document. Output only that object.

같은 URL 응답은 캐시된다. 재확인할 때는 프롬프트를 바꿔 호출한다.

## 3. CSAF/VEX JSON (NVR 보강)

`https://security.access.redhat.com/data/csaf/v2/vex/{YYYY}/{cve-yyyy-nnnnn}.json` (소문자)

- 용도: affected_release의 package 문자열로 부족할 때 x86_64 정확한 NVR 확보.
- `product_tree > branches`의 x86_64 `product_version` `purl`을 파싱한다.
- `product_status`(fixed / known_affected / known_not_affected / under_investigation)와 `flags`의 justification(예: vulnerable_code_not_present)은 리포트 "근거" 컬럼에 쓴다.
- 커널류는 응답이 잘린다. 잘리면 Hydra affected_release 값으로 대신하고 그 사실을 기록한다.
- `text_content_token_limit`을 높여 호출한다.

## 4. RHSA errata (필수, 패치가 있을 때)

`https://access.redhat.com/errata/{RHSA-ID}` — 발행일(Issued), 대상 제품, SRPM NVR 확인.

광범위 배포 CVE(RHSA 20개 초과: kernel, openssl 등):
- 메이저 버전별 기본(main) 스트림 RHSA 1개씩만 확정한다.
- 나머지는 Hydra affected_release 값을 그대로 쓰되 errata 미확인과 줄인 범위를 리포트와 대화 응답에 적는다.
- kpatch(라이브 패치) RHSA와 kernel 패키지 RHSA를 구분한다.

## 5. EPSS (필수)

기본: `python3 scripts/epss_kev.py CVE-A [CVE-B …]` — api.first.org를 먼저 호출하고, 실패·불일치 건만 미러로 폴백한다. 결과의 `source_url`이 실제 사용한 URL이다.

claude.ai에서 수동으로 할 때 1차: `web_fetch` → `https://api.first.org/data/v1/epss?cve={CVE-ID}`
- 이 URL은 검색 결과에 거의 나오지 않아 0절 제약으로 `PERMISSIONS_ERROR`가 나는 경우가 대부분이다. 한 번 시도하고 거부되면 검색으로 우회하지 말고 바로 폴백한다.
- 응답 `data[0].cve`가 요청 CVE와 정확히 일치해야 채택한다(도구 캐시로 다른 CVE 값이 오는 사례 있음).
- 채택 시 `epss`, `percentile`, `date`를 쓴다.

폴백 (거부·오류·빈 data·CVE 불일치 중 하나라도 해당): 재시도하지 않고 즉시 미러로 전환.
```bash
curl -sL "https://raw.githubusercontent.com/lucacapacci/epss/main/data_single/{YYYY}/{CVE-ID}.csv"
```
CSV 1행 `#model_version:…,score_date:…` → 조회 기준일, 3행 `{cve},{epss},{percentile}` → 100을 곱해 %.

미러 파일이 없으면(404) "정보 없음". 신규 CVE는 점수 산출 전일 수 있다.

해석 주의: EPSS는 원격·인터넷 노출형 취약점에 최적화돼 있어 로컬 권한상승형은 과소평가된다.

## 6. CISA KEV (필수)

```bash
python3 scripts/epss_kev.py CVE-YYYY-NNNNN
```
스크립트는 `raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json`을 한 번 받아 전체 CVE와 대조한다. 카탈로그 `dateReleased`를 조회 기준일 참고값으로 쓴다. 등재 시 `dateAdded`, `dueDate`, `vulnerabilityName`, `knownRansomwareCampaignUse`를 기록한다.

KEV 등재는 위험도의 하한선이다. 미등재라도 PoC 공개, CISA SSVC `Exploitation: poc/active` 등은 함께 서술한다.

## 7. 업스트림 공지

업스트림(프로젝트)이 밝힌 영향 버전과 수정 버전을 확인한다. 예: WebKitGTK WSA, OpenSSL Advisory. 이를 judgment-rules.md 8절의 이상 데이터 판정(수정 버전 비교)에 쓴다. 업스트림 공지에 접근하지 못하면 추측하지 않고 4장에 미확인으로 남긴다. 이후 절 번호는 그대로 둔다(6장 기준 인용).

## 7. Red Hat 미추적(NOTFOUND) 처리

1. JS 셸 오판이 아닌지 확인(1절 보류 규칙).
2. `cveawg.mitre.org/api/cve/{CVE-ID}`(또는 대체 소스)로 벤더·제품·버전 확인.
3. RHEL 무관 근거를 찾는다: 업스트림 구현체 차이, RHEL 제공 버전이 영향 범위 밖, Fedora Packages·rpmfind 소스 비교.
4. 근거 불충분 시 "미확인, Red Hat 포털 직접 확인 필요". "영향 없음"으로 단정하지 않는다.
5. CVE ID로 확인이 안 되면 RHSA/RHBA/RHEA 번호로, 그래도 안 되면 AlmaLinux git commit log를 대리 지표로 참고한다.

## 8. 출처 기록 규칙

- 산출물 출처에는 **실제로 조회에 성공한 URL**을 적는다. 조회하지 않은 URL을 관례적으로 적지 않는다.
- EPSS를 미러로 폴백했으면 미러 URL을, api.first.org로 받았으면 API URL을 적는다.
- KEV는 스크립트가 받은 raw.githubusercontent.com URL을 적는다.
- Hydra·CSAF·errata·RHSB, 대체 소스(OpenCVE, OSV 등)는 참고문서에 실제로 읽은 URL을 적는다. 대체 소스는 "(대체 소스, 수집 시점 YYYY-MM-DD)"를 붙인다.
- 조회를 시도했으나 실패한 문서와 그 영향은 리포트 4장과 대화 응답에 밝힌다. 접근하지 못한 URL은 조회한 출처로 나열하지 않는다.

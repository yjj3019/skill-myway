# 검증 현황

## 현재 상태 (버전 1.14.7)

- **기준**: 원격 `main`의 HEAD `b00875c` 및 VERSION 1.14.7. 이번 추가 분석 문서는 이 저장소 상태를 점검한 기록이며, 외부 모델·오피스 실행이나 새 성능 평가를 수행하지 않았다.
- **실행 시각**: 2026-11-08. DSH bundle `scripts/validate_repo.py` PASS, `scripts/run_tests.py` 124건·실패 0·skip 0.
- **범위**: preview-first 정책은 대형 파일 생성 전에 핵심 구성만 확인한다. 1.11.0 시점 사용자가 제공한 분석에서 현재화가 필요한 주장을 고치고, 역사적 발견과 현재 상태를 구분한다. 외부 후보 도구의 최신 라이선스·데이터 전송은 새로 확인하지 않았다.

| 항목 | 상태 | 근거 |
|---|---|---|
| 저장소 구조·버전·민감 패턴 (1.14.7) | VERIFIED | DSH bundle `scripts/validate_repo.py` PASS (2026-11-08) |
| 회귀 테스트 (1.14.7) | VERIFIED | `scripts/run_tests.py` 124건·실패 0·skip 0 (2026-11-08) |
| 스킬 버전 매니페스트 동기화 | VERIFIED | VERSION 및 5개 매니페스트 1.14.7 일치 |
| Git 반영 | VERIFIED | `e3210e8` forward correction은 `main`에 기록. Push 전에는 `origin/main`이 `ab5fcf2`; 이 이력은 보존되며 과거 clone의 자료도 회수하지 않음 |
| 평가 권한·예산 제한 | NOT VERIFIED | Codex에 `workspace-write`를 요청하고 모든 실제 평가에 호출 또는 시간 상한을 요구하도록 변경. 단위 테스트는 통과했으나 OS·네트워크 격리는 미확인. 원인: `codex exec`는 쓰기 범위 요청만 받으며 호스트 격리 증거를 출력하지 않음 |
| 자동 선택 평가기 | NOT VERIFIED | Codex `--json` 이벤트를 수집하고 최종 메시지와 trace를 분리한다. `as-10` 합성 질문 1회 자동 형식 검사 PASS. 실제 JSONL은 `thread.started`, `turn.started`, `item.completed(agent_message)`, `turn.completed`만 기록했고 스킬 파일 읽기 이벤트가 없어 선택 여부는 미확인. 단일 질문은 전체 스킬 선택 품질을 입증하지 않음 |
| CI 매트릭스 | VERIFIED (이전 커밋) | windows·macos·ubuntu × Python 3.11/3.12/3.13 9 job success 기록은 1.11.0 기준. 1.14.0 CI는 미실행 |
| 스킬 배포·설치·롤백 | VERIFIED | 9개 스킬 ZIP·3 플랫폼 설치, 이력 표 참조 |
| Office 샘플 생성·재열기 | PARTIAL | 번들 Python으로 PPTX 3장·DOCX 1표·XLSX 생성·구조 확인. LibreOffice `soffice.COM`: 기본 SUM 10/10 반복 PASS(캐시 30); 별도 수식 10개 시뮬레이션 PASS(정상 9개 기대값 일치, 0 나눗셈 `#DIV/0!` 검출). Office sidecar는 실제 PPTX 3장을 렌더했고 3장 모두 이미지 생성·missingFonts 0을 반환. 현재 모델에 이미지 입력이 없어 시각 내용은 수동 판정하지 못함. 실제 업무 파일 검증과 PowerPoint 호환성은 NOT VERIFIED |
| 스킬 자동 선택·조합 | PARTIAL | 기존 4케이스는 모델 자기보고만 있어 실제 호출은 미확인. 공개 10케이스는 파일과 요청형 실행기만 준비했으며 신규 모델 실행 없음. 한글 CLI 인코딩·실호출 추적·전문 판정은 미검증 |
| 실제 모델 평가 | VERIFIED(자동 검사) | Claude Code 2.1.316 headless 20/20 + Codex 3/3 + Grok 2/2 (2026-11-01) |
| 블라인드 비교 | PARTIAL | writing·code-review·research-brief 3케이스, 단일 평가자 표본 3 |
| Grok Bot 스킬 저장 / 앱 업로드 | NOT VERIFIED | 계정·앱 한도·실제 저장 미확인 |
| 교차 플랫폼 모델 실행 | PARTIAL | Codex·Grok 각 1회, 출력 길이 편차·타임아웃 관찰 |

---

# 버전별 검증 이력

기준일 2026-11-01, 버전 1.5.0. 확인한 것만 VERIFIED로 적는다. 아래 기록은 커밋 전 작업트리 기준이다.

## RHEL CVE 명세 개정 (2026-11-07, 1.14.1)

- RHEL 스킬을 Confluence용 Markdown 단건/통합 형식, HTTP 상태코드 취급, 가상 평가자료, 단건·통합 checker 동작에 맞춰 개정했다.
- `check_report.py`는 단건 파일명·고정 5장·7컬럼과 통합 접수/고유 건수·CVE별 5장·8컬럼 행 연결을 검사한다. 이 검사는 출처·사실의 진위를 확인하지 않는다.
- 외부 Red Hat·EPSS·KEV API를 예약된 `CVE-2099-00001`로 read-only probe했다. Red Hat CVE page·Hydra JSON·XML 각각 HTTP 404; EPSS First API HTTP 200이나 CVE 결과 없음; 미러 HTTP 404; KEV catalog released `2026-11-06`, 예약 CVE unlisted였다. 이 probe는 예약 identifier의 endpoint 동작만 확인하며 실제 CVE 데이터 정확도·최신 API 스키마·외부 실데이터 정합성은 NOT VERIFIED다.
- RHEL 전용 checker fixture 3건 통과. 마지막 전체 validator/suite 상태는 현재 상단 상태표에 기록한다.

## 결과 신뢰성·산출물 검증 보완 (2026-11-07, 1.13.0 작업트리)

> 과거 기록. 1.14.3 라이선스 감사 수정으로 evaluator의 기존 확인 상태가 바뀐 것은 아니다.

- 자동 선택 공개 10케이스와 `run_eval.py --auto-select`는 앞선 작업에서 추가했다. 이번 확인에서도 모델을 호출하지 않았다. 실제 스킬 선택 여부는 미확인이다.
- Codex `workspace-write`와 평가 호출·시간 예산은 CLI 설정으로 요청한다. OS·네트워크 격리 및 실제 스킬 로드 추적은 미확인이다.
- LibreOffice `soffice.COM`으로 샘플 XLSX 재계산을 기본 smoke 10회와 추가 가상 수식 10사례로 실행해 기대 결과 일치를 관찰했다. 이는 가상 입력·단일 LibreOffice 환경의 결과다.
- Office sidecar CLI로 가상 PPTX 3장 렌더를 완료하고 page count 3, 이미지 3개, missingFonts 0을 관찰했다. 현재 모델은 이미지 입력을 지원하지 않아 시각 내용 리뷰는 미완료다.
- Codex/Grok 일반 타깃 평가용 `--inspect-artifacts`를 구현해 생성 Office 파일을 재열어 일부 구조, ZIP 경로·크기·압축률, 매크로·외부 관계를 검사한다. XLSX 계산 캐시 누락·오류·정상 상태는 Office 구조 검사 상태와 분리 기록한다. 일반 파일의 수식 캐시 존재만으로 재계산 완료·기대값 일치를 주장하지 않는다.
- Office artifact 검사 구현의 회귀 테스트 추가 후 전체 suite에서 assertion 기대 불일치, 임시 XLSX 핸들 미닫힘, 테스트 케이스 필수 policy 누락을 찾아 수정했다. 이 세부 수정을 반영한 최종 전체 suite 실행 결과를 아래 최종 검증 행에 기록한다.
- RPM 비교 규칙은 원본 EVR 보존·RPM 규칙 비교·판정 후 표시 변환으로 정정했다. 접근성·입력/외부링크 기준 문서는 보강했으며 자동 검사는 없다.
- OS/네트워크 격리, 실제 호출 추적, 자동 선택 모델 평가, 이미지 육안 리뷰, 실제 업무 파일의 계산·출처 검증은 NOT VERIFIED다.

## 결과 신뢰성 보강 (2026-11-06, 1.12.0 이력)

- xlsx.md 4상태 판정·epoch 보존 규정·RENDER-GATE 표 정정·AUTO-SELECT 호출 추적 절차를 반영(D-032). 문서·지침 변경이다.
- 저장소 구조·버전·회귀 테스트 및 새 계산·호출 추적·렌더링 절차는 당시 검증 기록이 없어 **NOT VERIFIED**로 유지한다.

## 실제 평가 실행 (2026-11-06, 1.11.0 이력)

- **자연어 4케이스의 모델 자기보고 결과 (claude 2.1.318 headless, 1.11.0 이력)**: PARTIAL. 네 요청에서 모델이 예상된 스킬명을 응답에 언급했다. 이 결과는 자기보고이며, 플랫폼 스킬 로드 이벤트·파일 접근 추적이 없어 **실제 스킬 호출 또는 선택 성공으로 확인된 것은 아니다**. as-02는 가상 CVE 404를 지어내지 않고 계획만 제시했다. 한글 프롬프트 인코딩 깨짐과 MITRE 조회 연결 실패가 기록됐다. 표본 4·단일 모델.
- **외부 스킬 스캐너(cisco-ai-skill-scanner 2.3.2)**: VERIFIED(탐지 기록). 9개 스킬 18건 — office-docs CRITICAL 1(고정 인자 `execFileSync("soffice"/"python3", [...])` 호출, 인자 삽입 불가 — **오탐 판정**)·LOW 3(fs 접근), rhel-cve HIGH 1(로컬 `__pycache__` 존재 — 삭제 완료, gitignore 대상)·MEDIUM 2(Hydra/EPSS 의도된 조회)·LOW 1, 전 스킬 INFO 1(`license` frontmatter 미지정, 9건 공통). 스캐너 통과는 안전 보증이 아님.
- 렌더링 게이트(LibreOffice)는 미설치로 실행하지 않았다. **NOT VERIFIED 유지, 추후 실행하기로 결정**. 설치·실행은 사용자 승인 후.

## 평가 설계 문서화 (2026-11-06, 1.11.0 이력)

- 자동 선택 평가 설계(`docs/AUTO-SELECT-EVALUATION.md`)·오피스 렌더링 게이트 설계(`docs/RENDER-GATE.md`)를 추가하고, 검증 현황에 현재 상태 요약 표를 신설했다. 실제 PPTX 생성 평가 케이스(`office-docs-real-file-03`)를 추가했다.
- 저장소 구조·버전: **VERIFIED**. `python scripts/validate_repo.py` PASS. 회귀 테스트: **VERIFIED**. `python scripts/run_tests.py` 77건, 실패 0, skip 0.
- 자동 선택 케이스 실행·판정, 렌더링 게이트 실행: **NOT VERIFIED**. 스크립트·모델 실행·렌더러 도입은 설계만 있고 수행하지 않았다.

## 기준 검증 기록 (2026-11-01, 이전 버전 이력)

아래 결과는 1.5.0 작업 당시 기록이며 현재 1.14.0의 검증을 뜻하지 않는다.

## 이전 버전에서 실행한 검증

| 항목 | 상태 | 근거 |
|---|---|---|
| 저장소 구조·버전 일치·민감 패턴 | VERIFIED | `python scripts/validate_repo.py` 3회 연속 PASS (2026-11-01) |
| 단위·통합 테스트 | VERIFIED | `python scripts/run_tests.py` 69건, 실패 0, skip 0. 2회 연속 실행에서도 동일 |
| Python 버전 매트릭스 | VERIFIED | Python 3.11·3.13·3.14에서 각각 69건, 실패 0, skip 0. 3.11에서 테스트 탐색 결함을 찾아 `run_tests.py`를 수정 |
| 경로 공백·한글 | VERIFIED | 공백과 한글이 포함된 임시 경로에서 validate PASS, 51건 통과, ZIP 생성 성공 |
| CRLF 체크아웃 | VERIFIED | 텍스트 68개를 CRLF로 바꾼 복사본에서 validate PASS, 51건 통과 |
| 패키징 시뮬레이션 | VERIFIED | 9개 스킬 ZIP 생성, 같은 입력에서 같은 SHA-256, `__pycache__`·숨김 파일 미포함 |
| ZIP 소비 시뮬레이션 | VERIFIED | 9개 ZIP을 압축 해제해 SKILL.md frontmatter와 참조 파일 존재를 확인. 결함 0건 |
| 설치 스크립트 시뮬레이션 | VERIFIED | 임시 디렉터리에서 claude·codex·grok 3개 대상 모두 9개 스킬 복사, 재설치 skip, `--force` 교체 확인 |
| 롤백 시뮬레이션 | VERIFIED(재현) | 임시 복사본에서 `git restore` + 신규 파일 삭제 후 VERSION 1.4.5, validate PASS, 25건 실패 0 확인. 이 과정에서 원복 목록 누락 1건을 찾아 수정 |
| 버전 전파 | VERIFIED | 1.5.1로 올린 복사본에서 Claude·Codex 설치 버전과 Grok 검증 버전이 1.5.1로 표시 |
| 업그레이드 | VERIFIED(격리) | Claude 1.5.1→1.5.2 `plugin update`, Codex 경로 재추가+`plugin add`로 1.5.2, Grok `plugin update`로 1.5.0→1.5.1 반영 |
| 부정 테스트 | VERIFIED | Claude·Codex가 깨진 매니페스트 JSON을 거부, Codex가 없는 source 경로를 설치 시 거부, Grok이 `name` 누락 manifest를 거부, 저장소 검증기가 `..` 경로를 거부 |
| 보안·이력 스캔 | VERIFIED | 작업트리·전체 커밋에서 이메일·실제 CVE/RHSA·IP·토큰·홈경로 0건. 실행 파일·심볼릭 링크·의심 파일명 0건, 최대 파일 13KB |
| Claude Code 마켓플레이스·플러그인 검증 | VERIFIED | `claude plugin validate .`와 `claude plugin validate ./plugins/myway` 통과 (1.5.0) |
| Claude Code 설치·스킬 인식 | VERIFIED(격리 설정) | 임시 설정 디렉터리에서 1.5.0 설치, `claude plugin list`에서 enabled, 스킬 9개 확인 |
| Codex 설치·스킬 인식 | VERIFIED(격리 설정) | 임시 `CODEX_HOME`에서 1.5.0 설치, `codex plugin list`에서 installed·enabled, 스킬 9개 확인 |
| Grok Build 설치·스킬 인식 | VERIFIED(격리 홈) | 임시 홈에서 마켓플레이스 추가·설치 성공, 플러그인 목록에 표시, 스킬 9개 확인. 실제 사용자 홈은 변경되지 않음을 전후 비교로 확인 |
| Grok Build 플러그인 검증 | VERIFIED | `grok plugin validate ./plugins/myway` 통과, 1.5.0 |
| Grok Bot 스킬 저장 | NOT VERIFIED | 공식 문서의 대화 저장 절차만 확인. 실제 저장·호출 미실행 |
| Claude 앱·ChatGPT Skills ZIP 업로드 | NOT VERIFIED | ZIP 생성·소비까지만 확인. 업로드 화면·한도는 계정·앱 버전에 따라 달라 미확인 |
| Windows·macOS CI | VERIFIED(직전 푸시 기준) | 1.4.5 커밋의 CI 3개 OS 통과. 1.5.0 CI는 3개 OS × Python 3.11·3.12·3.13 매트릭스로 확장했고, 푸시 후 확인이 필요하다 |
| 라이선스·출처 검토 | VERIFIED(파일 단위) | 대상 저장소 여섯 개의 라이선스 파일·제3자 표기·민감 자산 확인. 법적 판정은 아님 |
| 원문 복사 대조 | VERIFIED(신규 파일 기준) | 이번에 새로 작성한 파일에서 40자 이상 연속 일치 0건(공식 문서 URL 제외). 대조 중 찾은 9건은 새 표현으로 교체 |
| 잔여 일반 지침 흡수 | VERIFIED(구조 검사) | 소스 저장소의 일반 지침을 새 스킬 3개·레퍼런스 4개·문서 2개로 재작성. validate PASS, 테스트 69건 통과 |
| 기존 유래 콘텐츠 | PARTIAL | `rhel-cve` 등 이전 통합분은 같은 작성자의 저장소에서 유래. 공개 배포 전 저작자 확인 필요 |
| AI-Harness 검토·반영 | VERIFIED(문서 판정) | Apache-2.0 확인, 98파일 분석. 흡수(evidence-first·레퍼런스 3종·blind_review·문서 보강)와 제외(게이트·훅·브로커) 내역을 LICENSES·DECISIONS에 기록 |
| 블라인드 평가 도구 | VERIFIED(단위 테스트) | `scripts/blind_review.py` 8건 테스트 통과: 배정 결정성·후보 매핑·seed 재현·잘못된 입력 거부·덮어쓰기 방지 |
| 가상 평가(1단계) | VERIFIED | `scripts/simulate_eval.py` 10케이스/10스킬 PASS. 스키마·id 중복·커버리지·민감 패턴 검사, manifest 해시 기록 |
| 실제 모델 평가(2단계) | VERIFIED(자동 검사) | Claude Code 2.1.316 headless로 10/10 통과, 2회 반복에서 **20/20** 통과(케이스별 2/2). 빈 임시 디렉터리에서 실행. 형식·필수 요소만 검사하며 문장 품질은 별도 판정이다. 결과: `docs/EVALUATION-RESULTS-2026-11-01.md` |
| 교차 플랫폼 모델 실행 | PARTIAL | Codex 3케이스 3/3(샌드박스 전체 접근 필요), Grok 2케이스 2/2(출력 길이 편차 큼, 1차에서 240초 타임아웃 1건). 각 1회 실행 |
| 오피스 생성·재열기 | PARTIAL | 번들 Python으로 PPTX 3장·DOCX 제목/표·XLSX 수식 생성 후 재열기 확인. LibreOffice가 없어 시각(넘침·겹침) 검증은 미실시. 검사: `scripts/check_office.py` |
| 스킬 유무 블라인드 비교 | PARTIAL | writing·code-review·research-brief 3케이스 A/B 블라인드 패킷에서 스킬 적용 3/3 선호. **단일 평가자(에이전트) 1명**·표본 3이라 독립 평가 아님 |
| 교차 플랫폼 모델 실행 | NOT VERIFIED | Codex·Grok Build는 설치·스킬 인식만 확인. 실제 모델 실행·품질 비교는 하지 않음 |

## 스킬 품질 확인 (기존 범위)

| 항목 | 상태 | 근거 |
|---|---|---|
| writing 비교 평가 | PARTIAL | `writing-evaluation.md`의 가상 원고 1건과 사례 4건 기록. 자동 호출·반복 검증은 미실행 |
| incident-rca 보고서 | PARTIAL | 가상 예시와 구조·형식 검사만 확인. 실제 사고 자료 적용은 미검증 |
| Office 문서 생성·시각 검증 | NOT VERIFIED | 이번 변경에서 실제 산출물 생성·렌더링·잘림 확인은 하지 않음 |
| HWP/HWPX 선택 도구 읽기 | PARTIAL | 이전 확인 범위 유지. 편집·자동 호출은 미검증 |
| RHEL CVE 판정·보고서 | PARTIAL | 1.4.5 가상 예시와 구조 오류 테스트 통과. 실제 CVE·RHSB 조회와 값 대조는 미검증 |
| 입시 요강·성적 산출 | NOT VERIFIED | 저장소의 산술식 테스트만 확인. 실제 요강 해석은 미검증 |
| devlog 기록 | NOT VERIFIED | 외부 기록 서비스·로컬 기록 흐름 미실행 |

## 확인하지 못한 것

- Claude 앱·ChatGPT desktop의 Skills 업로드 화면과 파일 한도
- Grok Bot 저장·호출
- 대화 중 스킬 자동 선택과 실제 산출물의 주관적 품질
- 공개 디렉터리 제출 심사(아이콘, 정책 검토)와 1.5.0의 원격 CI 결과
- 실제 업무 문서·CVE·사고 자료에 대한 정확도

## 저장소 정리 (2026-11-02)

- 삭제 대상 6개 저장소: GitHub API와 git 접근 모두 404/불가로 삭제 확인
- 삭제 전 전체 이력 미러 6개 보존(2.7MB), 로컬 archive 브랜치 보존
- 삭제 저장소를 가리키는 git 원격 참조 0건, 분석용 클론 2개 제거
- skill-myway: validate PASS, 테스트 70건 0실패
- 삭제 후 원문 대조·출처 재감사는 백업 미러로만 가능

## 시각 증거 지침 보강 (2026-11-04, 1.7.1)

- 시각 품질에 대한 실제 모델 평가, Office 산출물 렌더·독립 리뷰 및 플랫폼별 설치·실행: **NOT VERIFIED**. 가상 평가 사례와 수동 판정표는 실제 품질 통과를 의미하지 않는다.
- 저장소 구조 검사: **VERIFIED**. `python scripts/validate_repo.py` PASS. 가상 평가 사례 스키마 검사는 12건·10개 스킬 PASS이며 모델 품질 검증이 아니다.
- 테스트: **VERIFIED**. `python scripts/run_tests.py` 최종 71건, 실패 0, skip 0. 출력 중 skip 1건과 0건은 러너 실패 조건을 시험하는 내부 테스트다.
- oil-ui 원문 대조: **VERIFIED(문자열 한정)**. 원본 SKILL과 references 18개와 수정 Markdown·신규 수동 판정표를 공백 정규화 후 40자 연속 문자열로 대조해 일치 파일 0개. 번역·의미·구조 유사성은 이 검사로 판정할 수 없다.

## 실험·협업 경계 보강 (2026-11-04, 1.8.0)

- 저장소 구조·버전: **VERIFIED**. `python scripts/validate_repo.py` PASS.
- 회귀 테스트: **VERIFIED**. `python scripts/run_tests.py` 75건, 실패 0, skip 0. 출력에 표시되는 1건 skip과 0건은 러너의 실패 조건을 확인하는 내부 시험이다.
- 가상 평가 사례: **VERIFIED(스키마만)**. `python scripts/simulate_eval.py` 14건·10개 스킬 PASS. 모델 호출이나 의미 품질 평가는 아니다.
- 독립 코드 리뷰에서 긴 사례 ID의 출력 경로 문제와 수동 판정 분모 불일치를 발견해 수정했다. 수정 후 위 검증을 다시 실행했다.
- 실제 모델을 이용한 변경 전후 paired trial, 수동 사례 판정, 플랫폼별 설치·실행, 사용자 환경의 보안 격리: **NOT VERIFIED**. 자동 검사와 가상 사례만으로 품질 향상을 입증하지 않는다.
- 새 코드와 문서의 원문 대조: **NOT VERIFIED**. 외부 저장소의 코드·자산을 가져오지 않고 개념을 재설계했으나 기계적 문자열 대조 및 법률 검토는 수행하지 않았다.

## 100회 평가 대응 (2026-11-04, 1.9.0)

- 1.8.0에서 Claude CLI 100회 시도: 정상 응답 55건, 사용량 제한 41건, 시간 초과 4건. 정상 응답의 자동 검사 통과 53건·문자열 조건 불충족 2건이며 의미 품질 합격률이 아니다. 대표 10개 사례의 반복이고 기준선 비교가 아니다.
- 구조·버전 검사: **VERIFIED**. `python scripts/validate_repo.py` PASS. 가상 평가: **VERIFIED(스키마만)**. `python scripts/simulate_eval.py` 20건·10개 스킬 PASS.
- 회귀 테스트: **VERIFIED**. `python scripts/run_tests.py` 79건, 실패 0, skip 0. 출력 속 skip 1건·0건은 러너의 실패 조건을 점검하는 내부 시험이다.
- 사용량 제한 감지·중단, 미실행 상태, 출력 끝 검사는 mock 및 단위 테스트로 확인했다. 실제 제공자의 다른 오류 문구·별도 프로세스 간 중단 전파는 확인하지 않았다.
- 변경 후 실제 모델 paired trial, 수동 품질 평가, 플랫폼별 설치와 보안 격리: **NOT VERIFIED**. 추가 지침·가상 사례만으로 환각이나 오류가 사라졌다고 주장하지 않는다.

## 방법론 보강 (2026-11-02)

- MIT 원천(superpowers·agent-skills·ponytail)의 절차를 재작성해 반영, 원문 복사 0건
- Anthropic 공식 document skills는 설치 안내만, 코드·문서 미복사
- validate PASS, 테스트 70건 0실패, 플랫폼 매니페스트 validate 통과

## AI 말투 단서 판정 보강 (2026-11-05, 1.9.1)

- 저장소 구조·버전: **VERIFIED**. `python scripts/validate_repo.py` PASS. 원본 blader/humanizer(0ef9fe5)와 새 문단의 40자 연속 문자열 대조 0건.
- 회귀 테스트: **VERIFIED**. `python scripts/run_tests.py` 통과, 실패 0, skip 0.
- 새 판정 표가 실제 모델의 편집 품질을 개선하는지, 한국어 글에서 단서 겹침 판정이 사람의 기대와 맞는지: **NOT VERIFIED**. 지침 추가만으로 품질 향상을 입증하지 않는다.

## admission-helper 제거 (2026-11-05, 1.10.0)

- 저장소 구조·버전: **VERIFIED**. `python scripts/validate_repo.py` PASS. 배포 스킬 9개, admission 참조 제거 후 매니페스트 버전 일치.
- 회귀 테스트: **VERIFIED**. `python scripts/run_tests.py` 통과, 실패 0, skip 0.
- 제거 후 실제 질문에서 스킬과 같은 답변을 제공하는지: **NOT VERIFIED**. 스킬 부재 상태의 실제 답변 품질은 별도 실행 전 미검증이다.

## rhel-cve Confluence 기록용 Markdown 개정 (2026-11-06, 1.11.0)

- 저장소 구조·버전: **VERIFIED**. `python scripts/validate_repo.py` PASS. 매니페스트 5종 버전 1.11.0 일치.
- 회귀 테스트: **VERIFIED**. `python scripts/run_tests.py` 통과, 실패 0, skip 0.
- `check_report.py --self-test`: **VERIFIED**. `kernel-0:4.18.0-553.el8` FAIL, RHSA 번호 형식·`CVSS:3.1/AV:N`·`webkit2gtk3-2.46.3-1.el8_10.x86_64` PASS. `references/report-example.md`의 `<!-- REPORT START -->` 아래 예시가 검사 PASS.
- 평가 케이스 3건(rhel-cve-02/03/04)의 실제 모델 수행 결과: **NOT VERIFIED**. 조회 시점마다 KEV·EPSS 값이 바뀌므로 assertion은 수치가 아닌 등재 여부·기준일 기재 기준이다. 실제 모델 실행은 별도 평가 전 미검증이다.

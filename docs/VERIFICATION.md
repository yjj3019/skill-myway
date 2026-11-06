# 검증 현황

기준일 2026-11-01, 버전 1.5.0. 확인한 것만 VERIFIED로 적는다. 이 표는 커밋 전 작업트리 기준이다.

## 이번 변경에서 실행한 검증

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

# skill-myway

> **English**: [README.en.md](./README.en.md)

한국어 글쓰기, 업무 문서, 보안 분석, 개발 이력, 장애 원인 분석, 코드 리뷰, 프롬프트 설계, 자료 조사, 근거 우선 검토를 위한 개인 스킬 모음입니다. 스킬 본문은 한 벌이고, Claude Code·ChatGPT(Codex)·Grok Build가 같은 `SKILL.md`를 읽습니다. Grok Bot에서는 대화에서 스킬로 저장해 씁니다.

## 스킬

| 스킬 | 주요 기능 |
| --- | --- |
| `writing` | 한국어 블로그·기술 기고·게시글·업무 문서 작성과 편집. 개인정보 점검과 실행 환경별 보정 포함 |
| `office-docs` | PPTX·DOCX·XLSX 작성 규격, 장문 DOCX 빌드, HWP/HWPX 원문 읽기 |
| `rhel-cve` | Red Hat 자료를 바탕으로 Confluence용 한국어 Markdown CVE 리포트 작성: 단건 `CVE-ID_리포트.md`, 다건/RHSB 통합, 명시적 다건 요약, 파일 없는 영향도 검증 답변 지원 |
| `devlog` | Notion에 개발 이력 기록. 연결되지 않으면 `SESSION_LOG.md`에 기록 |
| `incident-rca` | 장애·오류 원인 분석, 타임라인·가설·근거 분리, 재발 방지 대책 정리 |
| `code-review` | 코드 변경 리뷰: 심각도·근거·Validation Gap, 테스트 약화 확인 |
| `prompt-engineering` | 프롬프트 구조화·검토·평가 케이스 설계 |
| `research-brief` | 출처 등급과 기준일을 밝힌 조사·리서치 브리프 |
| `evidence-first` | 근거 우선 검토: 완료 증거, 지침 충돌·노후 판정, 독립 확인 |

## 설치

### Claude Code

```text
/plugin marketplace add yjj3019/skill-myway
/plugin install myway@skill-myway
```

명령줄에서는 `claude plugin marketplace add ./`처럼 마켓플레이스 경로를 `./`로 시작해야 합니다. 갱신은 `/plugin marketplace update skill-myway`입니다.

### Codex

```sh
codex plugin marketplace add yjj3019/skill-myway
codex plugin add myway@skill-myway
```

갱신은 `codex plugin marketplace upgrade skill-myway`, 제거는 `codex plugin remove myway@skill-myway`입니다. 설치 뒤 앱을 다시 시작하고 `codex plugin list`로 버전을 확인합니다.

### Grok Build

Grok Build는 Claude Code의 마켓플레이스·플러그인·스킬 형식을 그대로 읽습니다. Claude Code에 플러그인을 설치했다면 추가 작업이 없습니다.

```sh
grok plugin marketplace add yjj3019/skill-myway
grok plugin install myway@skill-myway --trust
```

로컬 폴더를 마켓플레이스로 추가하면 마켓플레이스 이름이 폴더명이 된다. 이때는 `grok plugin install myway --trust`처럼 이름을 생략하거나 `myway@<폴더명>`을 쓴다. 갱신은 `grok plugin update`다.

플러그인 없이 스킬만 쓰려면 아래 설치 스크립트로 `~/.grok/skills`에 복사합니다.

### Grok Bot

파일 설치가 아니라 대화에서 스킬을 저장하는 방식입니다. `SKILL.md` 내용을 한 번에 주고, 다음처럼 요청합니다.

> 이 지침을 `writing` 스킬로 저장해 줘. 입력, 검증 방법, 승인 경계를 함께 적어 줘.

팀 기능이 있으면 스킬을 게시(publish)해 공유할 수 있습니다. 저장 동작은 계정·앱 화면에 따라 다를 수 있으니 목록에서 확인합니다.

### Claude 앱·ChatGPT Skills

업로드용 ZIP을 만든 뒤 앱의 Skills 메뉴에서 설치합니다.

```sh
python3 scripts/package_skill.py --skill writing
```

`dist/myway-writing-<버전>.zip`이 생기고, ZIP 안에 `<스킬이름>/SKILL.md`와 `references/`가 들어갑니다. 업로드 메뉴와 한도는 계정·앱 버전에 따라 다릅니다.

### 스킬 직접 설치

```sh
python3 scripts/install_skills.py --target all          # Claude Code·Codex·Grok Build
python3 scripts/install_skills.py --target claude       # ~/.claude/skills
python3 scripts/install_skills.py --target grok         # ~/.grok/skills
python3 scripts/install_skills.py --dest <경로>         # 원하는 위치
```

`--link`는 복사 대신 심볼릭 링크를 만들고(Windows는 권한이 필요할 수 있음), `--force`는 기존 같은 이름의 스킬을 교체합니다. 설치한 스킬은 자동 갱신되지 않으므로 저장소를 pull한 뒤 다시 설치합니다.

## 플랫폼별 읽는 경로

| 플랫폼 | 마켓플레이스 | 플러그인 매니페스트 | 스킬 경로 |
| --- | --- | --- | --- |
| Claude Code | `.claude-plugin/marketplace.json` | `plugins/myway/.claude-plugin/plugin.json` | `plugins/myway/skills/<이름>/SKILL.md` |
| Codex | `.agents/plugins/marketplace.json` | `plugins/myway/plugin.json`(canonical), `.codex-plugin/plugin.json`(호환) | `plugins/myway/skills/` |
| Grok Build | `.grok-plugin/marketplace.json`(Claude 형식도 호환) | `plugins/myway/plugin.json`(선택) | `~/.grok/skills`, `~/.agents/skills`, 플러그인 `skills/` |

자세한 요구사항과 확인하지 못한 항목은 [플랫폼 지원 현황](docs/PLATFORMS.md)에 있습니다.

## RHEL CVE 리포트

`rhel-cve`는 CVE ID 하나 또는 Red Hat CVE URL로 단건 Markdown 리포트를 만들고, 여러 CVE/RHSB는 한 파일로 통합합니다. 사용자가 요약 목록을 명시하면 다건 요약 모드를, 단순 영향 질문이면 파일 없는 대화 답변 모드를 유지합니다. 단건·통합 리포트는 `scripts/check_report.py`로 제목·파일명·고정 섹션·패키지 표 구조를 검사합니다. 검사는 Red Hat 사실이나 출처의 진위를 확인하지 않습니다.

예시와 테스트 입력은 예약된 가상 식별자를 사용합니다. 외부 Red Hat·EPSS·CISA KEV 조회 결과의 최신성은 실제 요청 때 별도로 확인해야 합니다. HTTP 접근 실패·대체 소스·범위 축소·미확인은 리포트에 밝혀야 합니다.

## 평가와 산출물 검사

`python3 scripts/run_eval.py --help`는 평가 모드를 안내합니다. 실제 모델 평가는 호출 또는 시간 예산이 필요합니다. Codex `workspace-write` 설정은 OS/VM 격리나 네트워크 차단 증거가 아닙니다. 평가 summary에 스킬 로드 이벤트가 없으면 스킬 선택은 미확인으로 남습니다.

Codex/Grok 평가에서 생성 Office 파일 검사도 요청하려면 `--inspect-artifacts`를 사용합니다. 격리 작업 폴더에서 캡처한 PPTX/DOCX/XLSX의 기본 구조, 압축 경로, 매크로 흔적과 외부 관계를 검사합니다. XLSX 계산 캐시·오류는 구조 검사와 분리합니다. 파일 구조 검사는 수식 기대값, 렌더링, 접근성, Excel/PowerPoint 호환성을 보증하지 않습니다.

## 브랜드 프로필

`office-docs`는 요청에서 제공된 값, 작업 디렉터리의 `brand-profile.md`, `~/.claude/myway/brand-profile.md`, 중립 기본값 순서로 브랜드 설정을 찾습니다. 프로필 양식은 [brand-profile.md](plugins/myway/skills/office-docs/references/brand-profile.md)에 있습니다. 조직 고유 값은 저장소에 두지 않습니다.

## 함께 쓰는 스킬

제안서·RFP·장표 제작과 제출 검토는 [ProposalSkills](https://github.com/yjj3019/ProposalSkills)를 별도 플러그인으로 함께 씁니다. 이 저장소는 일상 글쓰기·문서·보안·장애 분석·코드 리뷰를 담당하고, 제안서 전용 콘텐츠·PPTX 빌드·제출 게이트는 ProposalSkills가 맡습니다. 두 저장소의 파일을 서로 복사하지 않습니다.

## 검증과 유지보수

```sh
python3 scripts/validate_repo.py                        # 구조·버전·민감 패턴 검사
python3 scripts/run_tests.py                            # 0건·skip을 실패로 처리
python3 scripts/package_skill.py --skill all            # 업로드용 ZIP 생성
```

검증기는 매니페스트, 버전 일치, 스킬 지침과 참조 파일, 스크립트 문법, 민감 패턴을 확인합니다. 저장소에 둘 수 없는 검사 용어는 `--terms 파일` 또는 `MYWAY_BANNED_TERMS_FILE` 환경변수로 전달하고 커밋하지 않습니다.

품질 기준은 [품질 기준](docs/QUALITY-BAR.md)에, 스킬 추가·수정 절차는 [스킬 작성 안내](docs/SKILL-AUTHORING.md)에 있습니다. 리뷰 심각도와 증거 기준은 [리뷰 계약](docs/REVIEW-CONTRACT.md)에, 스킬 변경의 품질 비교는 [스킬 평가](docs/EVALUATION.md)에 있습니다. 블라인드 비교 패킷은 `python3 scripts/blind_review.py --help`로, 가상·실제 평가는 `python3 scripts/simulate_eval.py`와 `python3 scripts/run_eval.py --help`로 실행합니다. 검증된 현재 범위와 남은 미검증 항목은 [검증 현황](docs/VERIFICATION.md)을 확인하세요. 과거 실행 결과는 [평가 결과](docs/EVALUATION-RESULTS-2026-11-01.md)에 있습니다.

스킬을 수정할 때는 `VERSION`과 각 플랫폼 매니페스트의 버전을 함께 올립니다. 확인된 항목과 미검증 항목은 [검증 현황](docs/VERIFICATION.md)에 기록합니다.

## 라이선스와 출처

이 저장소의 라이선스는 [Apache License 2.0](LICENSE)입니다. 통합 과정의 라이선스·출처 판정과 반영·제외 내역은 [라이선스·출처 검토](docs/LICENSES.md)에 있습니다. 외부 저장소의 원문을 복사하지 않고 새로 작성했으며, 실명·조직·실제 게시물 인용·내부 정보는 저장소에 넣지 않습니다.

기준은 `docs/DECISIONS.md`에, 재발 방지 교훈은 `docs/compound-log.md`에 남깁니다.

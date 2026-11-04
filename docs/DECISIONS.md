# 설계 결정

## D-001 플러그인 1개, 스킬 여러 개
관련 작업(글쓰기, 오피스 문서, CVE, 대입 요강 분석, 개발이력)을 `myway` 하나로 설치하고 업데이트하도록 묶었다. 스킬은 용도별로 나눠 트리거가 겹치지 않게 했다.

## D-002 브랜드 값은 프로필로 분리
조직 고유 색상·폰트·서명란은 저장소에 두지 않는다. 기본값은 중립 팔레트이며 조직 값은 로컬 프로필로 주입한다. 이유: 공개 저장소에 특정 기관을 드러내지 않기 위해서다.

## D-003 글쓰기는 공통 기준 + 프로필 3종
말투와 형식이 충돌하는 세 가지 글쓰기 규칙(합니다체/해요체, 이모지 유무)을 프로필로 나눴다. 사실과 개인정보 경계는 모든 프로필에 우선한다.

## D-004 devlog의 Notion 부모 페이지는 하드코딩하지 않는다
사용 여부와 목적지를 첫 기록 전에 사용자에게 확인한다. 값은 요청 또는 `PROGRESS.md`에서만 읽는다.

## D-005 AI-Harness에서 가져온 것
검증 스크립트, 테스트, CI, DECISIONS.md, compound-log.md, CLAUDE.md만 가져왔다. 훅과 서브에이전트는 이 저장소의 범위가 아니라 포함하지 않았다.

## D-006 민감어 검사는 로컬 목록으로
저장소에 금지어 목록을 두면 그 자체가 유출이므로, 일반 패턴만 저장소에 두고 금지어는 `--terms` 로컬 파일로 받는다.

## D-007 Claude Code·Codex 겸용 마켓플레이스
스킬은 `SKILL.md` 표준이라 한 벌을 공유한다. 매니페스트만 플랫폼별로 둔다: Claude는 `.claude-plugin/`, Codex는 `.agents/plugins/marketplace.json`과 `.codex-plugin/plugin.json`(호환 레이아웃, codex-cli 0.164.0에서 설치·스킬 로드 확인). Codex 문서가 권하는 루트 `plugin.json` 포터블 형식은 Claude 쪽 구조와 충돌 여부를 확인하지 못해 쓰지 않았다. 스킬별 `agents/openai.yaml`은 Codex 선택기 표시용이다. `scripts/install_skills.py`는 마켓플레이스를 못 쓰는 환경용 대체 경로로 남긴다.

## D-008 스킬 description은 짧게
Codex는 설치된 스킬이 많으면 description부터 줄이고 일부는 목록에서 뺀다. 트리거 키워드를 앞쪽에 두고 길이를 600자 안팎으로 유지한다.

## D-009 Grok Build 지원 범위
Grok Build는 `~/.grok/skills`의 SKILL.md를 읽는다(문서 확인). 플러그인 카탈로그는 xAI 공식 저장소 PR 방식이고, 임의 저장소를 마켓플레이스로 추가하는 방법은 문서에서 확인하지 못했다. `.grok-plugin/marketplace.json`은 공개된 스키마대로 두되 동작은 미검증으로 표시한다. 확실한 경로는 `install_skills.py --target grok`다. 공식 카탈로그에 올리려면 원격 plugin은 40자 commit sha 고정이 필요하다.

## D-010 rhel-manual을 office-docs에 통합
rhel-manual은 이름과 달리 RHEL 전용이 아니라 장문 DOCX 빌드 파이프라인이다. office-docs의 docx 영역과 겹쳐 트리거가 갈렸다. `references/long-manual.md`와 `scripts/long-manual/`로 옮기고 office-docs description에 매뉴얼 빌드 트리거를 넣었다. rhel-cve는 보안 분석이라 도메인이 달라 따로 둔다.

## D-011 저장소와 마켓플레이스 이름을 skill-myway로 통일
저장소 이름이 skill-myway로 바뀌었고 Claude·Codex·Grok 겸용이라 `claude-` 접두어가 맞지 않는다. 마켓플레이스 이름과 설치 ID(`myway@skill-myway`)를 맞췄다.

## D-012 예시 데이터는 가상 값만
실제 CVE로 만든 리포트 예시를 가상 ID(CVE-2099-00001)와 가상 패키지로 바꿨다. 검증기는 2099 외의 CVE·RHSA 번호를 막는다. 특정 정보는 각 스킬의 "특정 정보가 필요할 때" 절차(묶음 질문, 저장소에 되쓰지 않음)로 받는다.

## D-013 admission-helper 추가
기존 개인 스킬 univ-admission-analysis를 영어 이름 admission-helper(진학 도우미)로 통합했다. 학생 정보는 저장소에 두지 않고 빈 프로필 서식에서 질문/답변으로 받는다. grade_calc.py의 환산식은 `eval` 대신 AST 기반으로 사칙연산과 `x`만 허용한다. 연도 의존 문구(학년도, 권역 목록)는 일반화했다.

## D-014 AI-Harness 2026-10-26 업데이트 반영 범위
가져온 것: 테스트 수 검증(0건·전체 skip은 실패, `scripts/run_tests.py`), 검증 현황표(`docs/VERIFICATION.md`), CLAUDE.md의 지침 충돌·검증 의미·승인 경계 규칙, CI 최소 권한. 가져오지 않은 것: phase-gate와 attestation, ToolBroker, 지식 그래프 평가, evidence-first-harness 스킬. 이 저장소에는 Phase 흐름과 훅·서브에이전트가 없고, 선택 도구는 측정 전에 도입하지 않는다는 원본 문서의 결론을 따랐다.

## D-015 writing-style-doc 규칙 대조 보강 (1.4.1)
원본 SKILL.md §4~11을 `writing`과 항목별로 대조했다. 이미 있던 규칙이 대부분이었고, 누락된 11건(3항 나열·유행어·굵은 글씨·이모지·본문 반복 요약·마무리 범위·공개용 미확인 주장 처리·영어 표준 표기 금지·수정 후 일관성 확인·밀도·제작 도구 표기)만 옮겼다. 원본의 생성 스크립트, 평가 기록, 출처·실제 문체 자료 문서는 가져오지 않았다. 이 저장소가 SKILL.md를 직접 관리하고 특정 자료를 담지 않기 때문이다.

## D-016 글쓰기 프로필 충돌 정리 (1.4.2)
Humanizer의 문단 단위 재검토와 사실 보존 관점을 참고하되 별도 엔진을 추가하지 않는다. 숫자 없는 공식 사실, 사용자 감정과 개인 말투, 명시된 매체, 도메인 형식을 보호하도록 기존 프로필의 강제 규칙을 정리하고 가상 평가 사례를 추가한다. 참고: https://github.com/blader/humanizer/tree/8c307f367c91bd974002f10f2be2965d642c13df. 문구와 예시는 독립 작성했다.

## D-017 글쓰기 비교 평가와 패키지 검사 분리
`writing`은 자연어 지침이므로 예시나 문자열 검사를 모델 품질 테스트로 취급하지 않는다. 실제 비교가 필요하면 `writing-evaluation.md`의 독립 입력·중립 라벨·의미 보존 우선 판정을 사용하고, 가리지 못한 정보와 실행 조건을 밝힌다. 참고: https://github.com/cursor/plugins/blob/519d36aa98955bf680db01bcde5fdfba686dc901/pstack/skills/poteto-mode/playbooks/eval.md. 별도의 실행 도구나 모델 서비스는 강제하지 않는다.

## D-018 선택적 HWP/HWPX 읽기 (1.4.3)
`kordoc`의 문서 읽기를 별도 설치·자동 등록 없는 선택적 경로로 안내한다. 합성 HWPX의 본문·표·병합·경고 및 공개 HWP/HWPX 각 1건의 읽기를 시험했다. 대응 PDF와 쪽 수 차이가 있었으나 판본 일치는 미확인이다. 추출 쪽 번호와 내용은 원본에서 확인하며, 실제 편집·생성·OCR·입시 판정의 검증으로 확장하지 않는다. 참고: https://github.com/chrisryugj/kordoc/tree/c2067cfbb21a26489022880ba1db1c7e100f1a00.

## D-019 RHEL CVE Confluence 보고서 (1.4.5)
사용자가 제공한 형식과 샘플의 날짜·완화 절차를 단건·다건·RHSB 보고서에 적용한다. 별도 내부 보고서 참조는 기본적으로 제외한다. 요약 요청은 기존 요약 형식을 유지한다. 구조 검사와 원문 근거 검증을 구분하고, 확인되지 않은 완화 효과나 제품 상태는 단정하지 않는다.

## D-020 저장소 통합 검토와 반영 원칙 (1.5.0)
작성자의 공개 저장소 여섯 개(`writing-style-doc`, `blog-style`, `redhat-cve-analysis`, `claude-skills`, `ChatGPT`, `Claude`)를 검토해 이 저장소의 스킬 범위에 맞는 부분만 반영했다. 저장소별 라이선스 판정과 반영·제외 내역은 `docs/LICENSES.md`에 남겼다.
- 원칙: 원문을 복사하지 않고 새로 작성한다. 라이선스가 확인되지 않은 자료는 옮기지 않는다. 실명·조직·실제 게시물 인용·내부 정보가 있는 자산은 제외한다. 예시는 가상 값만 쓴다.
- 반영: `writing`의 게시글 공개 점검과 실행 환경별 보정, 신규 스킬 `incident-rca`, 업로드용 ZIP 패키징(`scripts/package_skill.py`), 설치 스크립트의 Claude 경로, Codex canonical `plugin.json`과 `interface` 보강.
- 제외: 에이전트·프롬프트 프레임워크, 코드 리뷰·위임 자산은 이 저장소의 스킬 범위와 맞지 않고 권리 미확정 경로가 섞여 있었다. 특정 조직·개인·실제 게시물이 포함된 문체 자료도 제외했다.
- 플랫폼: Grok Build는 Claude Code의 마켓플레이스·플러그인 형식을 그대로 읽고(공식 문서 2026-11-01 확인), Grok Bot은 대화에서 스킬을 저장하는 방식이다. `docs/PLATFORMS.md`에 경로와 미확인 항목을 적었다.
- 후속 후보: 두 대형 저장소가 제안한 검증·릴리스 거버넌스(평가 루브릭, 스킬 호출 평가 케이스, 버전 증가 강제 게이트, 릴리스 기록 형식)는 콘텐츠가 아니라 형식이라 이번 범위에서 반영하지 않고 후보로만 남겼다. 현재는 `scripts/validate_repo.py`가 매니페스트 버전 일치를 검사한다.
- 원문 대조: 여섯 저장소와 40자 이상 연속 일치를 재검사해 0건을 확인했고(공식 문서 URL 제외), 대조 중 찾은 20~49자 겹침 9건은 새 표현으로 교체했다. 라이선스 문제가 생겼을 때는 원복이 아니라 원본에서 요구사항만 확인해 다른 로직으로 재구현하는 것을 먼저 하고, 원복은 비상 수단으로 둔다. 절차와 자산별 재구현 방법은 `docs/LICENSES.md`에 있다.

## D-021 실행 버전 호환과 플랫폼 갱신 동작 (1.5.0)
시뮬레이션·실환경 검증에서 확인한 동작을 고정한다.
- `scripts/run_tests.py`는 Python 3.11 이하에서 `__init__.py`가 없는 임시 디렉터리를 테스트 대상으로 넘기면 테스트 탐색이 실패한다. `discover()`에 `top_level_dir`을 시작 폴더로 고정해 해결하고, Python 3.11·3.13·3.14에서 51건 통과를 확인했다.
- Claude Code 갱신은 `claude plugin marketplace update` + `claude plugin update`로 동작한다(1.5.1 → 1.5.2 확인). Codex 로컬 경로 마켓플레이스는 `marketplace upgrade`가 git 전용이라 경로를 다시 추가한 뒤 `plugin add`로 재설치한다. Grok 로컬 마켓플레이스 등록 이름은 폴더명이므로 `grok plugin install myway`처럼 이름을 생략하고, 갱신은 `grok plugin update`를 쓴다.
- 검증기는 플러그인 source의 `..` 경로를 거부한다. 플랫폼 검증기(Claude·Codex·Grok)는 매니페스트 JSON 오류를 거부하지만 source 디렉터리 존재는 설치 시점에 확인하므로, 저장소 검증기의 경로 검사를 함께 쓴다.

## D-022 소스 저장소 제거 대비 일반 지침 흡수 (1.5.0)
소스 저장소를 정리한 뒤에도 쓸 수 있도록, 남아 있던 일반 지침을 이 저장소로 흡수했다. 원문 복사 없이 재작성했고, 특정 대상·벤더 종속·호스트 전용·권리 미확정 자산은 제외했다.
- 흡수: 리뷰 계약(`code-review`, `docs/REVIEW-CONTRACT.md`), 프롬프트 설계(`prompt-engineering`), 조사(`research-brief`), 글 유형·임원 요약·회의록(`writing/references/`), 오피스 작업 규칙(`office-docs/references/`), 평가 루브릭(`docs/EVALUATION.md`).
- 제외: 조직·개인 실명, 실제 게시물 인용, 내부 목적지, 벤더 모델 코드명·가격·라우팅, 호스트 전용 설정, 생성 배포본, 권리 미확정 경로.
- 판정 근거와 흡수 목록은 `docs/LICENSES.md`에 있고, 흡수 후 40자 원문 대조를 다시 실행해 본문 일치 0건을 확인했다.

## D-023 AI-Harness 자산 선택 반영 (1.6.0)
AI-Harness(Apache-2.0)를 검토해 이 저장소에 맞는 검증·평가 자산만 재작성해 반영했다.
- 반영: `evidence-first` 스킬, `report-editing`·`deck-evidence`·`handoff` 레퍼런스, `scripts/blind_review.py`, `docs/REVIEW-CONTRACT.md`·`docs/EVALUATION.md` 보강.
- 제외: phase-gate 워크플로, 훅·서브에이전트, ToolBroker, attestation, 지식 그래프, 성숙도·배포 문서는 런타임 하네스 전용이라 반영하지 않는다(D-005·D-014 유지).
- 원문을 복사하지 않고 재작성했으며, 제3자 MIT 고지는 `docs/LICENSES.md`에 기록했다.

## D-024 방법론 보강과 라이선스 경계 (1.7.0)
MIT 저장소(obra/superpowers, addyosmani/agent-skills, DietrichGebert/ponytail)의 검증·디버깅·리뷰·품질 기준 개념을 재작성해 반영했다. 원문 복사는 없고 출처는 `docs/LICENSES.md`에 기록했다.
- 반영: `evidence-first` 검증 게이트, `code-review` 리뷰 워크플로·보안·최소 변경, `incident-rca` 디버깅 절차, `writing` ADR, `office-docs` PDF·공식 문서 스킬 안내, `docs/QUALITY-BAR.md`·`docs/SKILL-AUTHORING.md`.
- 경계: anthropics/skills는 라이선스상 복사 불가 → 설치 안내만. 라이선스 없는 저장소(document-specialist, ProposalSkills)는 개념·병행 안내만. superpowers·addyosmani의 전체 스킬 이식은 범위·트리거 충돌로 하지 않는다.
- 스킬 수는 10개를 유지하고, 기존 스킬의 references와 문서를 보강하는 방식으로 반영했다.

## D-025 시각 증거와 독립 평가 보강 (1.7.1)

- oil-oil/oil-ui의 시각 증거와 독립 평가 개념을 참고해 기존 스킬과 평가 문서에 맞게 재작성한다. 실제 확인한 범위와 구조 검사·렌더링을 구분하고, 평가자의 독립성과 관찰 근거를 밝힌다.
- 별도 웹 UI 스킬, 원본 코드·자산·업데이트 도구 및 상용 제품 안내는 포함하지 않는다. 모션 강제와 주관적 점수의 일반화도 제외한다.
- 테스트 사례는 지침을 평가하기 위한 입력이며, 사례가 존재하거나 자동 형식 검사를 통과한 것만으로 모델의 시각 판단 능력이 검증되는 것은 아니다.

## D-026 실험·권한·상태 경계 보강 (1.8.0)

- autoresearch, Harness², dsh-superagent의 조사에서 기준선 비교·실패 보존·근거와 권한 분리의 개념을 기존 평가 및 스킬 지침에 맞게 독립적으로 재설계한다. 이 저장소는 기존의 사람 판정과 승인 경계를 유지한다.
- 외부 저장소 코드·문서·자산, 벤치마크, 상시 감시·자동 작업·샌드박스 해제 기능을 이식하지 않는다. 평가 결과의 자동 통과는 의미 품질이나 실제 운영 성능의 증거가 아니다.
- 스킬 10개를 유지하며 사용자 자료, 이전 미커밋 변경과 실험 결과를 보존한다.

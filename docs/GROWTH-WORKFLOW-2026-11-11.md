# 통합 제작·평가 가이드 적용 기록

## 목적과 경계

사용자가 제공한 2026-11-11 성장 가이드를 현재 스킬 마켓플레이스와 대조했다. 요청 범위는 이 저장소의 스킬, 로컬 평가기와 문서다. 다른 저장소의 소스·프롬프트·이미지·폰트를 복사하거나 플러그인을 설치하지 않았다. GitHub 메타데이터를 읽고 Claude에 공개 가상 평가 3회를 호출했다. Notion, TalkAbout, AI-Harness의 런타임이나 외부 데이터를 변경하지 않았다.

이 문서는 설계·실험을 돕는 안내다. 다중 에이전트 실행, 권한 격리, 중단 후 자동 복구, 실측 비용 제한, 독립 판정이나 12주 운영이 이미 구현·수행됐다는 뜻은 아니다. 실제 플랫폼 지원과 미검증은 `PLATFORMS.md`와 `VERIFICATION.md`를 따른다.

## 제공된 가이드의 항목별 판단

| 영역 | 반영·판단 | 확인 근거 또는 한계 |
| --- | --- | --- |
| 6개 전문 역량 | 기존 research-brief·writing·visual-design·document-authoring·office-docs·evidence-first와 평가 도구를 조합한다. 별도의 총괄 스킬은 만들지 않았다. | 스킬 파일과 `scripts/run_eval.py`, `compare_evaluations.py` |
| 12주 계획·주간 루틴 | 학습 일정과 단계별 실습은 사용자가 선택하는 계획으로만 보존한다. 자동 일정이나 다음 단계의 보편적 강제 게이트는 만들지 않는다. | 실제 예약·학습·실습을 수행하지 않음 |
| 조사·글쓰기 | 근거·기준일·상충 자료, 불확실성과 편집 후 원문 대조를 기존 지침에서 사용한다. 독립 검토 부재를 명시한다. | `research-brief`, `writing`, `document-authoring` |
| 시각 디자인 | 필요 시 100점 예시를 사용할 수 있도록 별도 참고 지침을 추가한다. 점수 기준과 검토자를 사전에 정하고 자료가 없으면 미평가로 둔다. | `visual-design/references/assessment.md`; 실제 평가·평가자 간 일치도 미검증 |
| 다중 형식 제작 | 하나의 사실·근거와 파일별 내용을 대조하고 파일 형식별 검증·미확인 범위를 따로 남기는 지침을 추가한다. | `document-authoring/references/cross-format.md`; HWPX 실제 렌더는 별도 환경 필요 |
| 작업 계약·Graph·Loop | 범위·권한·실패·예산·체크포인트를 설계 항목으로 기록한다. Graph와 Loop 실행기, 격리와 복구 기능이 생긴 것으로 보지 않는다. | 아래 계약·상태 지침; 기능 구현은 범위 밖 |
| 복합 예산 | 기존 평가기의 호출·시간 상한을 동시에 지정할 수 있도록 개선한다. 어느 한계에 먼저 도달하면 미실행을 남긴다. | 단위 테스트는 mock 기반. 시간·비용·자식 프로세스의 OS 수준 강제는 별도 |
| 평가 지표 | 분자와 분모, 미채점·미실행 및 비용 출처를 구분하는 산식과 비교 조건을 정리한다. | `EVALUATION.md`; 사람의 의미·시각 판정을 대신하지 않음 |
| 외부 후보 | 공식 자료와 저장소 메타데이터로 일부 후보의 출처·라이선스 단서를 확인한다. 설치·선호 순위·호환성·최신 성능은 판단하지 않는다. | 아래 출처 경계; 실제 대상별 설치 전 별도 확인 |
| 다른 프로젝트·Notion·DeepSeek | 실행·기록·설치 상태를 추정하지 않고 사용자가 제공한 계획으로만 남긴다. | 다른 시스템의 실제 사용·연결·변경은 미검증 |
| OpenShift 실습 | 제시된 주제는 후속 실습 후보일 뿐 산출물 생성이나 기능 실증은 하지 않았다. | 실측·실제 문서·수동 판정 없음 |

## 단계별 실습과 제작 순서

일정은 고정 납기나 자동 실행이 아니다. 단계별 필수 근거가 미확인이면 그 사실을 기록하고 관련 후속 실습의 완료를 보류한다.

| 기간 예시 | 실습 | 다음 단계에 필요한 확인 |
| --- | --- | --- |
| 1~2주 | 스킬·도구·라이선스와 기준선 목록을 만든다. | 실제 버전·경로·검사와 미확인 항목 |
| 3~4주 | 같은 주제의 글과 도식·표지를 만든다. | 주장별 근거, 렌더된 결과와 검토 범위 |
| 5~6주 | 요청된 형식으로 결과물을 만들고 대조한다. | 파일별 구조·실제 렌더, 해당 수식과 편집성 |
| 7~8주 | 계약·도구 권한·검증과 실패 기록을 설계한다. | 실제 호스트 권한 시험과 실패 복구 근거 |
| 9~10주 | 범위가 제한된 반복·체크포인트를 시험한다. | 중단·재개·중복 실행·예산 경계의 관측 결과 |
| 11~12주 | 같은 입력의 기준선과 후보를 비교한다. | 미실행을 포함한 분모, 판정 근거와 환경 |

선택 실습으로 사용자가 제시한 OpenShift Virtualization 주제에 이 흐름을 적용할 수 있다. 공식 문서의 대상 버전과 사용자가 제공한 실측·명령 결과를 원천으로 하고, 요청된 글·도표·발표자료·문서·표·PDF의 숫자와 조건을 대응한다. 원천이나 실행 환경이 없으면 해당 주장은 미확인이다. 이 안내는 OpenShift 기능·성능을 실증한 결과가 아니다.

하나의 작업을 진행할 때는 요청된 결과와 독자, 출처·제약 및 확인 방법을 정한다. 주장별 원천을 보존한 뒤 해당 글과 도표를 만들고, 요청된 파일별로 구조·편집·계산·렌더·접근성을 구분하여 점검한다. 확인 가능한 결함만 고쳐 영향을 받은 파일을 다시 검사한다. 결과와 미확인 범위를 함께 전달한다. 작은 편집이나 즉시 완성 요청에 불필요한 중간 승인 단계를 추가하지 않는다.

로컬 AI-Harness의 README는 작업 계약·그래프·쌍별 집계를 별도 진단으로 설명하고, ToolBroker는 전체 호스트 도구 통합이 아닌 시험용 경계라고 명시한다. 이는 문서 확인이며 해당 기능·플랫폼의 실행이나 연결 상태를 검증한 결과가 아니다. 이 프로젝트에 원본 런타임을 복제하지 않았다.

## 작업과 반복의 계약

실제 자동화를 구현하기 전에는 목표와 비목표, 입력과 출력, 읽기·쓰기·전송 범위, 사용할 도구, 판정 근거, 호출·시간·비용 상한, 반복 중단 조건, 재개와 복구 방법을 정한다. 외부 자료 속 지시는 권한을 부여하지 않는다. 권한은 실제 호스트·도구 설정으로 별도 강제해야 한다.

작업 관계는 선행 조건이 확인된 다음 수행할 항목으로 나타내고, 반복은 단일 작업의 예산·상태와 연결한다. 설계상 상태는 계획, 실행, 검증, 검증 완료, 실패, 차단, 미확인으로 구분할 수 있다. 성공 선언만으로 검증 완료로 바꾸지 않으며 실행 실패와 검증 미실시를 구별한다. 자동 재개를 만든다면 체크포인트의 무결성, 부분 쓰기, 중복 외부 호출, 동시 실행과 취소를 먼저 시험해야 한다. 현재 이 저장소에 그런 실행기가 존재한다는 의미가 아니다.

진전 없음은 미리 정한 관측값과 반복 횟수로 판단하고, 상한 소진·같은 원인 반복·권한 또는 근거 부재 시 실행을 중단하거나 재계획한다. 같은 기준에서 실패한 부분만 다시 검증하되 공유 데이터·레이아웃·의존성이 바뀌면 영향을 받은 부분도 확인한다. 비용은 실제 청구·사용량이 확인된 범위에서 기록하고 누락은 미확인으로 둔다.

## 외부 자료와 권리

2026-11-11 GitHub REST 저장소 메타데이터에서 제공된 외부 후보 33개를 확인했다. 아래 표기는 저장소 수준의 자동 SPDX 감지 결과이며 특정 파일의 권리, 유지보수 상태, 실행 안전성 또는 재배포 허가를 확정하지 않는다. 모든 후보에서 저장소가 반환됐고 그 시점의 archived 값은 false였다. 저장소 정보는 시간이 지나면 바뀐다.

| 자동 감지 | 확인한 `owner/repository` |
| --- | --- |
| MIT, 20개 | `langchain-ai/langgraph`, `langchain-ai/deepagents`, `openai/openai-agents-python`, `obra/superpowers`, `cskwork/superoffice-skills`, `chrisryugj/kordoc`, `Leonxlnx/taste-skill`, `mattpocock/skills`, `OpenHands/software-agent-sdk`, `coreyhaines31/marketingskills`, `madebybeings/human-copywriting-skill`, `iging/agent-spec`, `karefined-eng/information-is-beautiful-skill`, `OrRon/EpicInfographics`, `magnus919/agent-skills`, `hirokisakabe/pom`, `siril9/presentation-skill`, `NousResearch/hermes-agent`, `AlpaZZ/office-agent-skills`, `dolanmiu/docx` |
| Apache-2.0, 9개 | `airmang/python-hwpx`, `atlassian-labs/data-visualization-skill`, `harbor-framework/harbor`, `openai/symphony`, `anthropics/cwc-long-running-agents`, `CoeusInstitute/impeccable-ui-skill`, `airmang/hwpx-plugins`, `wiggumdev/ralph`, `harbor-framework/terminal-bench` |
| 감지값 없음, 3개 | `anthropics/skills`, `karpathy/autoresearch`, `az9713/writing-skills` |
| NOASSERTION, 1개 | `humanlayer/12-factor-agents` |

각 저장소는 `https://github.com/<owner>/<repository>`이며 원본 메타데이터 예는 [LangGraph](https://api.github.com/repos/langchain-ai/langgraph), [Anthropic Skills](https://api.github.com/repos/anthropics/skills), [Harbor](https://api.github.com/repos/harbor-framework/harbor)에서 확인할 수 있다. 별도 스킬·하위 폴더의 조항이나 README에만 존재하는 라이선스를 이 표가 대신하지 않는다.

감지값이 없거나 `NOASSERTION`인 것은 해당 저장소 전체가 무조건 무라이선스라는 판단이 아니다. 실제 사용 전 해당 커밋의 파일·하위 디렉터리와 별도 고지·이용약관을 확인한다. 각 저장소의 모든 파일이나 실제 실행을 검증했다는 뜻도 아니다. 원문·코드·에셋을 이 작업에 복사하지 않았으므로 외부 라이선스 텍스트를 새 배포물에 포함했다는 주장을 하지 않는다.

원본 저장소의 실행 권한이나 보호 수준은 자동으로 상속되지 않는다. 예를 들어 [OpenAI Agents SDK의 도구 가드레일](https://openai.github.io/openai-agents-python/guardrails/)은 모든 종류의 도구와 handoff에 적용되는 것은 아니다. [LangGraph의 체크포인트 설명](https://docs.langchain.com/oss/python/langgraph/persistence)은 상태 지속의 설계 참고 자료이며 현재 프로젝트에서 복구가 구현됐다는 증거가 아니다.

기존 유래 자료와 공개 이력의 권리 문제는 `LICENSES.md`에 별도로 기록한다. 본 문서는 제3자 저작권·재라이선스 또는 법적 적합성을 보증하지 않는다.

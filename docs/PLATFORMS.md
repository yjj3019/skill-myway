# 플랫폼 지원 현황

기준일 2026-11-01. 공식 문서로 확인한 내용과 확인하지 못한 내용을 구분한다. 설치·호출의 실제 동작은 [검증 현황](VERIFICATION.md)에 따로 적는다.

## 요약

| 플랫폼 | 배포 방식 | 문서 확인 | 실제 동작 |
|---|---|---|---|
| Claude Code | 마켓플레이스 + 플러그인 | 공식 문서 확인 | 1.5.0 격리 설정에서 설치 성공 |
| Claude 앱 | 스킬 ZIP 업로드 | 미확인(계정·앱 버전 차이) | 미검증 |
| Codex | 마켓플레이스 + 플러그인 + 스킬 | 공식 문서 확인 | 1.5.0 격리 환경에서 설치 성공 |
| Grok Build | Claude Code 형식 호환 + 스킬 디렉터리 | 공식 문서 확인 | 1.5.0 격리 홈에서 설치 성공, 스킬 6개 인식 |
| Grok Bot | 대화에서 스킬 저장 | 공식 문서 확인 | 미검증 |
| ChatGPT Skills | 스킬 ZIP 업로드 | 미확인 | 미검증 |

## Claude Code

- 마켓플레이스 파일: `.claude-plugin/marketplace.json` (필수 필드 `name`, `owner`, `plugins`)
- 플러그인 매니페스트: `plugins/myway/.claude-plugin/plugin.json`
- 스킬: `plugins/myway/skills/<이름>/SKILL.md`
- 설치: `/plugin marketplace add <저장소>` 후 `/plugin install myway@skill-myway`
- 확인한 공식 문서: 마켓플레이스·플러그인 매니페스트 참조, 스킬 안내
- 확인하지 못한 것: 대화 중 실제 호출, Claude 앱 업로드 화면과 한도

## Codex

- 마켓플레이스 파일: `.agents/plugins/marketplace.json`
- 플러그인 매니페스트: `plugins/myway/.codex-plugin/plugin.json` (스킬 경로 `./skills/`, UI용 `interface`)
- 스킬: `plugins/myway/skills/<이름>/SKILL.md`, 스킬별 `agents/openai.yaml`은 표시용
- 설치: `codex plugin marketplace add <저장소>` 후 `codex plugin add myway@skill-myway`
- 로컬 경로 마켓플레이스는 `codex plugin marketplace upgrade`가 git 전용이라 동작하지 않는다. 새 버전을 받으려면 경로를 다시 추가하고 `codex plugin add`를 다시 실행한다(1.5.1 → 1.5.2 재설치 확인).
- 확인한 공식 문서: 플러그인 패키징 안내, Codex 스킬 안내
- 확인하지 못한 것: 대화 중 실제 호출, `interface` 필드 전체 검증

## Grok Build

- 스킬 탐색 경로: `./.grok/skills/`, `~/.grok/skills/`, 활성 플러그인의 `skills/`, `config.toml`의 추가 경로
- Claude Code 호환: Grok은 Claude Code의 마켓플레이스·플러그인·스킬·지침 파일을 별도 설정 없이 읽는다. 따라서 이 저장소의 Claude Code 설치 경로를 그대로 쓸 수 있다.
- `AGENTS.md` 계열 지침과 `~/.agents/skills/`도 함께 읽는다.
- `.grok-plugin/marketplace.json`은 Grok 마켓플레이스 색인으로 쓰인다(격리 설치로 확인). `.claude-plugin/` 등가 형식도 읽는다.
- 로컬 폴더를 마켓플레이스로 추가하면 등록 이름이 **폴더명**이 된다(JSON name이 아니다). 이때는 `grok plugin install myway --trust`처럼 이름을 생략한다. 갱신은 `grok plugin update`이며 1.5.0 → 1.5.1 반영을 확인했다.
- 확인한 공식 문서: Skills, Plugins & Marketplaces
- 확인하지 못한 것: 대화 중 실제 호출

## Grok Bot

- 파일 설치가 아니라 대화에서 스킬을 저장하는 방식이다. 스킬 내용(규칙·입력·검증·승인 경계)을 주고 "이 과정을 스킬로 저장해 달라"고 요청한다.
- 팀 기능이 있으면 스킬을 게시(publish)해 공유할 수 있다.
- 확인한 공식 문서: Skills and routines
- 확인하지 못한 것: 실제 저장·호출

## Claude 앱·ChatGPT Skills

- `python3 scripts/package_skill.py --skill <이름>`으로 업로드용 ZIP을 만든다. ZIP 안에는 `<이름>/SKILL.md`와 `references/`가 들어간다.
- 업로드 메뉴와 글자·파일 한도는 계정·앱 버전에 따라 다르므로 공식 문서로 확정하지 못했다. 화면에 해당 메뉴가 없으면 대화에 스킬 내용을 붙여 임시로 쓸 수 있다.
- 확인하지 못한 것: 실제 업로드와 적용

## 공식 문서

- Claude Code 마켓플레이스 참조: https://code.claude.com/docs/en/plugins/marketplace-reference
- Claude Code 스킬: https://code.claude.com/docs/en/skills
- Claude Code 플러그인 매니페스트: https://code.claude.com/docs/en/plugins/manifest-reference
- OpenAI Codex 플러그인 패키징: https://developers.openai.com/plugins/build/plugins
- Grok Build Skills, Plugins & Marketplaces: https://docs.x.ai/build/features/skills-plugins-marketplaces
- Grok Bot 스킬과 루틴: https://docs.x.ai/grok-bot/skills-routines-and-automations

# CLAUDE.md

이 저장소는 Claude Code·Codex·Grok Build 겸용 마켓플레이스(`skill-myway`)이며 플러그인은 `plugins/myway` 하나다.

## 규칙

- 요청 범위만 수정한다. 관련 없는 리팩터링을 하지 않는다.
- 작업 시작 전 `docs/compound-log.md`를 읽는다.
- 완료 주장에는 증거를 붙인다: `python3 scripts/validate_repo.py`가 PASS이고 `python3 scripts/run_tests.py`가 통과해야 한다. 종료 코드 0만으로 충분하지 않다. 테스트가 0건이거나 skip이 있으면 실패다.
- 민감 정보와 특정 대상(기관·고객·개인·내부 시스템)을 가리키는 내용은 저장소에 절대 넣지 않는다. 예시는 가상 값(CVE-2099-*, 예약 주소)만 쓴다.
- 특정 정보가 필요한 기능은 하드코딩하지 않고 질문/답변으로 받는다. 한 번에 묶어 묻고, 답은 로컬 프로필이나 해당 세션에만 둔다.
- 스킬을 바꾸면 `VERSION`, `.claude-plugin/marketplace.json`, `plugins/myway/.claude-plugin/plugin.json`, `plugins/myway/.codex-plugin/plugin.json`, `plugins/myway/plugin.json`, `.grok-plugin/marketplace.json`의 버전을 함께 올린다.
- SKILL.md는 500줄 이하, description은 1024자 이하, `name`은 디렉터리명과 같게 둔다. 상세 내용은 `references/`로 보낸다.
- 설계상 선택은 `docs/DECISIONS.md`에, 재발 방지 교훈은 `docs/compound-log.md`에 적는다.
- 지침 문서가 검증된 코드·테스트와 충돌하면 둘을 함께 인용하고 지침의 소유 문서를 고친다. 정상 코드를 낡은 문장에 맞추지 않는다.
- 검증하지 못한 항목은 `docs/VERIFICATION.md`에 NOT VERIFIED로 남긴다. 통과를 지어내지 않는다.
- push, 삭제, 외부 시스템 쓰기는 사용자 승인 후에 한다. 프롬프트와 셸 훅은 샌드박스가 아니다. 승인은 실제 사람의 확인과 호스트의 권한 설정으로 받는다.

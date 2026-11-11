# 스킬 추가·수정 절차

이 저장소에 스킬을 추가하거나 고칠 때의 순서다.

## 1. 설계

- 해결할 문제와 사용자가 말할 요청을 한 문장으로 적는다.
- 기존 스킬과 트리거가 겹치지 않는지 확인한다. 겹치면 새 스킬 대신 기존 스킬의 references로 넣는다.
- 범위 밖 요청(부정 트리거)을 description에 명시한다.

## 2. 파일

- `plugins/myway/skills/<이름>/SKILL.md` — 이름은 디렉터리와 같게, 소문자·하이픈.
- frontmatter: `name`, `description`(트리거 키워드를 앞쪽에, 1024자 이하).
- 본문 500줄 이하. 상세 내용은 `references/`로 보낸다.
- `agents/openai.yaml`에 `display_name`, `short_description`.
- 실행 코드는 `scripts/`, 예시는 `references/examples.md` 등으로 분리한다.

## 3. 연결

- `README.md` 스킬 표에 한 줄 추가.
- 매니페스트 description·keywords에 반영(과장 없이).
- 다른 스킬과 함께 쓰는 흐름이면 해당 SKILL.md에서 참조한다.
- `docs/QUALITY-BAR.md` 기준(줄 수·길이·참조)을 확인한다.

## 4. 평가

- `tests/eval_cases/cases.json`에 가상 케이스를 추가한다. 실제 개인·조직 정보는 쓰지 않는다.
- `python scripts/simulate_eval.py`로 스키마·커버리지·민감 패턴을 검사한다.
- 가능하면 `python scripts/run_eval.py --only <스킬> --max-calls 1`로 실제 출력 형식을 확인한다. 케이스가 여러 개면 나머지는 미실행으로 기록되므로 목적에 맞게 예산을 정한다.

## 5. 버전·기록

- `VERSION`과 매니페스트 5곳을 함께 올린다(스킬 변경 시 minor 이상).
- `docs/DECISIONS.md`에 설계 선택을, 재발 방지 교훈은 `docs/compound-log.md`에 적는다.
- 출처·라이선스가 있으면 `docs/LICENSES.md`에 기록한다. 원문 복사는 금지하고 개념만 재작성한다.

## 6. 산출물 단계

- 큰 Office 파일이나 다단계 문서 빌드는 기본적으로 핵심 구조와 대표 내용만 짧게 미리 보여주고, 명시적 확인을 받은 뒤 생성한다. 전체 본문을 별도 HTML로 복제하지 않는다.
- 사용자가 완성 파일의 즉시 생성을 분명히 요청한 경우, 읽기·검토만 하는 경우, 사소한 편집에는 추가 확인을 요구하지 않는다. 유형별 상세는 `office-docs/references/preview-first.md`를 따른다.

## 7. 검증

```sh
python3 scripts/validate_repo.py
python3 scripts/run_tests.py
```

- 실패 0, skip 0이어야 한다.
- 플랫폼 배포 전 `claude plugin validate .`, `grok plugin validate ./plugins/myway`를 확인한다.

## 트리거 설계 요령

- 좋은 description: 무엇을 하는지 + 언제 쓰는지 + 쓰지 말아야 할 때.
- 키워드는 사용자가 실제로 입력할 말("다듬어줘", "리뷰해줘")로 쓴다.
- 비슷한 스킬과 트리거가 겹치면 문구를 조정하거나 하나로 합친다.

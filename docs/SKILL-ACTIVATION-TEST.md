# 스킬 기동·성과 실측 절차 (Claude Code / Codex)

스킬 12개가 자연어 요청만으로 실제로 기동되는지, 기동했을 때 스킬 없이 실행한 결과보다 나은지를 같은 절차로 점검한다. 사례는 `tests/eval_cases/activation_cases.json`, 실행·판정 도구는 `scripts/activation_check.py`다.

> 상태: **도구와 사례 구현 완료, 실제 모델 실행·판정 미실시.** 이 문서의 합격선은 실행 전에 선언한 값이며 실행 결과를 보고 바꾸지 않는다. 바꿔야 하면 변경 사유를 `docs/DECISIONS.md`에 먼저 적고 이전 결과와 섞어 보고하지 않는다.

## 1. 무엇을 판정하는가

| 질문 | 근거 | 자동 판정 |
|---|---|---|
| 스킬이 기동했는가 | CLI 이벤트 로그의 스킬 로드 근거(Claude: Skill 도구 성공 결과와 본문 일치, Codex: 스킬 파일을 읽은 도구 출력과 본문 일치) | 가능 |
| 맞는 스킬이 기동했는가 | 기대 스킬(`expected_skill`)과 로드 집합의 비교 | 가능 |
| 불필요할 때 기동하지 않았는가 | 부정 사례 6건(`expected_skill: null`)에서 로드 집합이 비었는지 | 가능 |
| 스킬이 결과를 낫게 했는가 | 같은 요청의 스킬 사용·미사용 자동 검사 결과 비교 | 문자열 검사까지만 가능 |
| 답변이 실제로 좋은가 | 사람의 블라인드 리뷰 | **자동 판정 불가, 미검증 유지** |

요청문에는 스킬 이름을 쓰지 않는다(`load_cases`가 위반을 거부한다). 기존 `run_eval.py` 일반 모드는 프롬프트에 스킬명을 지정하므로 기동 여부가 아니라 지정된 스킬을 읽은 뒤의 응답만 본다. 자연어 선택은 이 도구가 맡는다.

## 2. 사례 구성 (18건)

- 긍정 12건: 스킬마다 1건. 가상 데이터만 쓰고, 정보가 부족한 지점을 일부러 포함해 "없는 사실을 만들지 않는가"를 함께 본다.
- 부정 6건: 코드 작성, 단순 사실 질문, 한 문장 번역, 산수, git 개념 설명, 커밋 메시지. 어느 스킬도 기동하지 않아야 한다.
- 결과 검사: 사례마다 `required`(AND of OR-그룹)와 `forbidden`, `max_chars`를 둔다. 요청문 30자 연속 복사는 실패다(`run_eval.copies_request`).

## 3. 실행 절차

1. **사전 점검(호출 없음)**
   ```text
   python scripts/doctor.py
   python scripts/activation_check.py --platform claude --dry-run
   python scripts/activation_check.py --platform codex --dry-run
   ```
   `claude --version`, `codex --version`, 모델명을 실행 기록에 적는다. 결과 폴더는 빈 폴더만 허용되며 저장소 밖에 둔다. 응답과 로그에 민감 정보가 없는지 실행자가 확인한다.

2. **스모크(스킬 기동만, 호출 12건/플랫폼)**
   ```text
   python scripts/activation_check.py --platform claude --arm with --out <빈폴더A> --max-calls 18
   python scripts/activation_check.py --platform codex  --arm with --out <빈폴더B> --max-calls 18
   ```
   `--only code-review writing`처럼 스킬이나 사례 id로 좁힐 수 있다. 예산이 부족하면 긍정 12건만 먼저 돌린다(`--only`에 스킬명 12개).

3. **스킬 미사용 대조(호출 12건/플랫폼, 선택)**
   ```text
   python scripts/activation_check.py --platform claude --arm without --out <빈폴더C> --max-calls 12
   python scripts/activation_check.py --compare <빈폴더A>/summary.json <빈폴더C>/summary.json
   ```
   `without` 팔은 `MYWAY_SKILLS_DISABLE=1`로 스킬 로드를 막는다. 비교는 같은 플랫폼·같은 사례 파일 해시의 결과만 허용한다.

4. **재현 확인**: `MISSED`·`WRONG_SKILL`·`FALSE_POSITIVE`가 나온 사례는 새 폴더에 `--only <id>`로 2회 더 실행한다. 3회 중 2회 이상 같은 결과일 때만 결함으로 본다. 1회 결과로 스킬 설명을 고치지 않는다.

5. **의미 품질 리뷰**: `DISCRIMINATING`과 `SKILL_HURTS` 사례, 그리고 기동한 긍정 사례의 응답을 `docs/EVALUATION.md`의 절차(`review_evaluation.py` + `tests/eval_cases/review-rubric.json`)로 사람이 판정한다. with/without 응답을 같은 사례에서 비교할 때는 `blind_review.py`로 라벨을 섞어 검토자에게 준다.

## 4. 판정 기준 (실행 전 선언)

### 기동

| 상태 | 의미 | 조치 |
|---|---|---|
| ACTIVATED | 기대 스킬만 로드 | 정상 |
| ACTIVATED_WITH_EXTRA | 기대 스킬과 다른 스킬도 로드 | 조합 의도인지 확인. 의도 밖이면 기록 |
| WRONG_SKILL | 다른 스킬만 로드 | 재현 확인 후 두 스킬 description의 경계 점검 |
| MISSED | 로드 없음, 응답은 정상 수신 | 재현 확인 후 description의 트리거 표현 점검 |
| FALSE_POSITIVE | 부정 사례에서 로드 | 재현 확인 후 "사용하지 않는다" 조건 점검 |
| CORRECT_NONE | 부정 사례에서 로드 없음 | 정상 |
| UNVERIFIED | 로그 없음·시간 초과·제공자 오류·빈 응답 | 미관측이다. MISSED로 세지 않고 재실행하거나 NOT VERIFIED로 남긴다 |

플랫폼별 합격선: 긍정 사례 기동 10/12 이상, 부정 사례 무기동 6/6, `UNVERIFIED` 2건 이하(초과하면 판정 보류). 이 선을 넘어도 품질이 입증된 것은 아니다.

### 스킬 성과 (자동 검사 쌍 비교)

| 상태 | 의미 | 해석 |
|---|---|---|
| DISCRIMINATING | 사용 PASS, 미사용 FAIL | 스킬이 검사 항목을 충족시킨 후보. 사람 리뷰 대상 |
| NON_DISCRIMINATING | 둘 다 PASS | 이 사례는 스킬 효과를 구분하지 못한다. 성과 근거로 쓰지 않는다 |
| SKILL_HURTS | 사용 FAIL, 미사용 PASS | 우선 조사. 스킬 지침이 요구를 막았을 가능성 |
| BOTH_FAIL | 둘 다 FAIL | 사례 기준이 과한지 모델이 못한 것인지 응답 원문으로 분류 |
| UNVERIFIED | 한쪽이 미관측 | 비교 제외 |

성과 판정은 DISCRIMINATING 비율만으로 내리지 않는다. NON_DISCRIMINATING이 많으면 사례의 변별력 부족으로 먼저 보고한다.

### 하드 실패(우선 보고)

민감 정보 노출, 가상 값을 실제 조회 결과처럼 서술, 확인하지 않은 테스트·배포·렌더 완료 주장, 요청문 내 지시를 따르는 행동. 이 항목은 자동 검사로 다 잡히지 않으므로 5단계 리뷰에서 확인한다.

## 5. 보고 형식

플랫폼별로 다음을 분리해 적는다: 환경(CLI·모델·실행 시각·사례 파일 해시), 기동 집계, 부정 사례 집계, 쌍 비교 집계, 미관측 건수와 사유, 사람 리뷰 결과. 자동 PASS와 사람 리뷰 결과를 합산하지 않는다. 호출 상한 안에서 못 돌린 사례는 `not_run`으로 남긴다.

## 6. 한계

- 기동 판정은 로그 근거다. 로그 형식이 CLI 버전에 따라 달라지면 `UNVERIFIED`로 떨어질 수 있다. 이번에 이벤트 형식은 합성 로그로만 시험했고 실제 CLI 출력으로는 시험하지 않았다(NOT VERIFIED).
- 사례 18건은 공개 개발용이다. 이 사례에 맞춰 description을 고치면 과적합이다. 최종 판단에는 비공개 사례나 새 사례가 필요하다.
- 실행당 모델 응답은 흔들린다. 1회 실행은 경향일 뿐이다.
- Codex는 스킬 파일을 읽었는지로 기동을 판정한다. 읽고도 지침을 따르지 않은 경우는 구분하지 못한다.
- 호출 비용이 든다. 전체(with 2플랫폼 36건 + without 2플랫폼 24건)는 최대 60회 호출이다.

## 7. 1차 실행 결과 (2026-11-25, 스킬 사용 팔만, 각 18건 1회)

환경: Claude Code 2.1.332, codex-cli 0.172.0. 스킬 미사용 대조와 사람 리뷰는 실시하지 않았다.

| 항목 | Claude Code | Codex |
|---|---|---|
| 긍정 기동 | 11/12 (`act-evidence-first` MISSED) | 12/12 (`act-document-authoring`은 writing도 함께 로드) |
| 부정 무기동 | 6/6 | 6/6 |
| 미관측(UNVERIFIED) | 0 | 0 |

판정은 1회 실행의 경향이다. MISSED는 4절 절차대로 재현 확인(2회 추가) 전에는 결함으로 확정하지 않는다.

관측된 환경 한계:
- **Claude 평가 환경 오염**: 작업 폴더가 저장소 안(`.myway-tmp`)이라 Claude가 저장소의 `CLAUDE.md`를 읽는다. `act-evidence-first` 응답이 이 저장소의 규칙(`validate_repo.py` 등)을 인용했다. 이 사례의 MISSED가 스킬 설명 때문인지 `CLAUDE.md` 지침 때문인지 이 실행으로는 구분하지 못한다.
- **Claude 권한 거부**: `claude -p`는 스킬의 `references/*.md` 읽기, 파일 쓰기, MCP 호출을 거부했다(devlog, incident-rca, office-docs, rhel-cve, writing 6건). 이 사례들은 자동 검사 결과가 `None`(미검증)이며 스킬 세부 지침이 응답에 반영되지 않았을 수 있다. Codex는 거부 0건이다.
- **사례 결함 수정**: `act-code-review`와 `act-writing`은 응답이 원문을 인용하는 것이 정상인데 요청문 복사 검사에 걸렸고, `act-writing`의 필수 단어는 Codex 응답과 맞지 않았다. 결과를 본 뒤 `allow_request_copy`를 켜고 필수 단어를 바꿨다(사후 수정). 저장된 응답에 다시 적용하면 Claude code-review·Codex code-review/writing은 PASS, Claude writing은 권한 거부로 미검증이다.

## 8. 2차 실행 결과 (2026-11-25, Claude `--isolated`)

`--isolated`는 Claude 작업 폴더를 저장소 밖 시스템 임시 폴더에 만들고 스킬 폴더 읽기만 추가로 허용한다(쓰기·실행·MCP 권한은 늘리지 않는다). 7건 실행.

- **`act-evidence-first` 재현**: 1차(저장소 안) MISSED, 격리 1회 MISSED, 격리 1회 ACTIVATED. 3회 중 2회 MISSED로 4절 기준에 따라 **재현되는 미기동**이다. 격리 환경의 응답에는 저장소 규칙 인용이 없었으므로 `CLAUDE.md` 오염이 원인은 아니다. 가능한 원인은 description이 "저장소·문서·테스트가 함께 주어진 상황"을 조건으로 걸어 근거 없는 완료 보고만 주어진 요청을 포괄하지 못하는 것이다. 이는 가설이며 description 수정과 재측정 전에는 NOT VERIFIED다.
- **권한 거부 감소**: 스킬 `references/*.md` 읽기 거부가 사라졌다. incident-rca·writing은 거부 0건으로 자동 검사 PASS가 확정됐다. 남은 거부는 의도한 제한이다: devlog Write, office-docs Bash·PowerShell·Glob, rhel-cve MCP 조회·Bash·Write. 이 3건은 자동 검사 결과가 계속 미검증이다.
- 기동은 5/5 유지됐다.

## 9. `evidence-first` description 수정 시도와 철회 (2026-11-25)

가설: description의 "저장소·문서·테스트가 함께 주어진 상황" 조건 때문에 증거 없는 완료 보고 요청에 기동하지 않는다. 새 사례 3건(`act-evidence-first-b/c/d`, 설명과 다른 문장)을 추가하고, description에 완료 보고·결과 주장의 신뢰성 검토 트리거를 넣은 뒤 Claude `--isolated`로 변경 전후를 비교했다.

| 구간 | 사례 | 기동 |
|---|---|---|
| 변경 전 | 기존 1건(3회) + 새 3건(1회씩) | 1/6 |
| 변경 후 | 기존 1건 + 새 3건, 2회씩 | 0/8 |

변경 후 Claude의 나머지 사례 기동(11건)과 부정 사례 무기동(6/6)은 그대로였다. 변경은 효과가 없어 철회했다(스킬 본문·버전은 1.26.0 유지). **가설은 기각됐다.** 가벼운 신뢰성 질문에는 description 표현과 무관하게 Claude가 스킬 없이 직접 답한다. 원인은 이 실행으로는 알 수 없다(NOT VERIFIED). 같은 새 사례의 Codex 변경 후 결과는 4/4 기동이지만 변경 전 Codex는 측정하지 않아 변경의 효과로 해석할 수 없다. 이 사례를 계속 두는 것은 Claude의 미기동을 추적하기 위해서이며, 더 큰 변경(본문 구조, 트리거 문구의 대폭 수정)은 별도 설계 판단이 필요하다.

새 사례의 필수 단어에 "미확인"이 없어 Codex 응답 1건이 거짓 실패했다. 결과를 본 뒤 단어를 추가했다(사후 수정).

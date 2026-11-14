# 디자인 검토 증거 무결성 검사

`scripts/design_review_gate.py`는 사용자가 준비한 원본·화면 이미지·검토 기록을 오프라인으로 읽어 파일 해시와 판정의 연결을 확인한다. 파일을 생성·수정·삭제하거나 모델을 호출하지 않는다. 디자인 품질, 원본에서 이미지가 생성됐는지, 실제로 모든 화면을 검토했는지, 검토자 신원·독립성은 확인하지 않는다.

## 입력

`python scripts/design_review_gate.py EVIDENCE_ROOT MANIFEST.json`을 실행한다. `EVIDENCE_ROOT` 아래의 비어 있지 않은 정규 파일만 사용한다. 각 파일은 최대 64 MiB이며 파일별 SHA-256은 소문자 64자리다. 경로는 루트 기준 상대 경로로 지정하고 상위 경로·심볼릭 링크·Windows 재분석 지점·대체 데이터 스트림은 거부한다. manifest는 최대 1 MiB이며 아티팩트 최대 20개, 각 화면 최대 200개다.

아래는 스키마 예시다. `...`는 실제 파일의 64자리 SHA-256으로 바꿔야 하며, 이미지 파일 생성이나 원본 렌더링은 이 도구가 하지 않는다.

```json
{
  "schema_version": 1,
  "artifacts": [{
    "id": "sample",
    "kind": "pptx",
    "source": {"path": "deck.pptx", "sha256": "..."},
    "surfaces": [{
      "index": 1,
      "render": {"path": "pages/slide-01.png", "sha256": "..."},
      "review": {
        "source_sha256": "...",
        "render_sha256": "...",
        "status": "PASS",
        "open_critical": 0,
        "open_major": 0
      }
    }]
  }]
}
```

`kind`는 `html`, `image`, `pdf`, `pptx`, `docx` 중 하나다. 화면 번호는 1부터 연속해야 하며 한 아티팩트의 여러 화면에 같은 이미지 경로를 재사용할 수 없다. `review.source_sha256`과 `review.render_sha256`은 실제로 검토했다고 기록한 원본·이미지의 해시여야 한다. 판정은 `PASS`, `FAIL`, `NOT VERIFIED` 중 하나이고 미해결 중대 결함은 음이 아닌 정수로 기록한다. 검토자가 보고 있는 항목을 수정한 경우 새 원본과 렌더로 다시 검토하고 해당 기록을 갱신한다.

원본 해시는 파일 전체를 대상으로 한다. PPTX에서 한 장만 바뀌어도 기존 원본 해시에 묶인 모든 장의 기록이 거부된다. 변경되지 않은 장의 판정을 증거와 함께 선택적으로 이어받는 기능은 제공하지 않는다. 이 보수적인 동작은 추가 검토 비용이 들 수 있다.

해시 계산의 예는 `python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())" FILE`이다. 이 예시는 검사기의 64 MiB 제한보다 큰 파일에는 사용하지 않는다. 실행 환경의 개인 경로와 민감한 자료는 공개 저장소에 기록하지 않는다.

## 결과 해석

- 해시가 일치하고 기록이 유효하면 `evidence_integrity: PASS`다. 이는 검사 시점의 파일 바이트만 뜻한다.
- `declared_status`는 각 화면의 입력된 선언과 미해결 결함을 요약한다. 중대 결함이나 `FAIL`이 있으면 아티팩트는 `FAIL`이다.
- 최종 `verdict`는 선언된 실패가 있으면 `FAIL`, 그 외에는 항상 `NOT VERIFIED`다. 정합한 자기 선언이 시각 품질 합격으로 승격되지 않도록 명령은 정합한 입력에도 종료 코드 1을 반환한다. 잘못된 입력도 종료 코드 1이므로 구조화된 결과의 유무를 함께 확인한다.
- 이미지가 실제로 해당 원본과 화면에서 생성됐는지, 목록에 모든 화면이 포함됐는지, 시각·접근성·편집성·원문 내용이 맞는지는 별도 확인한다. 검사 중 파일을 동시에 변경하는 공격을 차단하는 OS 보안 경계도 아니다.

작업 흐름·표현의 선택·매체별 확인은 `plugins/myway/skills/visual-design/references/design-harness.md`와 관련 스킬에서 다룬다. 오래된 기록이 거부되면 덮어쓰기를 강제하지 말고 현재 파일을 확인해 다시 검토한다.

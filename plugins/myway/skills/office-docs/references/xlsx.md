# XLSX 규격

내장 `xlsx` 스킬(openpyxl)로 생성하고 편집한다. 값은 brand-profile에서 가져온다. 수식 에러 0건(#REF!, #DIV/0!, #VALUE!, #N/A, #NAME?)은 필수 요건이다.

## 폰트

- 본문과 헤더는 `맑은 고딕`(폴백 Arial). Excel에서 별도 설치 폰트는 렌더가 불안정하다.
- 프로필의 폰트가 설치되어 있고 사용자가 그 사용을 요청했을 때만 적용한다.
- 숫자와 코드 셀은 mono 폰트.

## 헤더와 표

| 요소 | 규격 |
|---|---|
| 헤더 행 | primary 채움, 흰 글씨 Bold, 가운데 정렬 |
| 본문 행 | zebra 짝수행 pale |
| 테두리 | 헤더 하단 굵게, 본문은 line 색 가로선만 |
| 고정 | 헤더 행 freeze panes |
| 정렬 | 텍스트 좌측, 숫자·날짜 우측 |

```python
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# T: brand-profile 값. openpyxl 색은 앞에 FF를 붙인다.
hdr_fill = PatternFill("solid", fgColor="FF" + T["primary"])
hdr_font = Font(name=T["body"], bold=True, color="FFFFFFFF")
body_font = Font(name=T["body"], color="FF" + T["ink"])
border = Border(bottom=Side(style="thin", color="FF" + T["line"]))

for c in ws[1]:
    c.fill = hdr_fill
    c.font = hdr_font
    c.alignment = Alignment(horizontal="center", vertical="center")
ws.freeze_panes = "A2"
```

## 숫자 포맷

| 종류 | 포맷 |
|---|---|
| 통화(원) | `#,##0;(#,##0);"-"` + 헤더에 단위 명시 |
| 퍼센트 | `0.0%` |
| 배수 | `0.0"x"` |
| 연도 | 텍스트 "2026" (천단위 콤마 금지) |
| 음수 | 괄호 `(123)` |
| 0값 | `-` |

## 데이터 모델 색 규약

- 파란 글씨: 하드코딩 입력값(바꿀 가정)
- 검은 글씨: 수식과 계산
- 초록 글씨: 같은 통합문서의 다른 시트 참조
- 빨간 글씨: 외부 파일 참조
- 노란 배경: 갱신이 필요한 핵심 가정

가정값은 별도 셀로 분리하고 수식은 셀 참조를 쓴다. `=B5*(1+$B$6)`처럼 쓰고 하드코딩을 피한다.

## 차트

- 1계열 primary, 2계열 accent, 이후 deep → muted.
- 격자선은 옅게, 3D와 그림자는 쓰지 않고, 축 단위 라벨을 붙인다.

## 보안과 검증

- API 키, 토큰, `.env` 값, 자격증명을 셀(숨김 포함), 메모, 차트 제목에 넣지 않는다.
- 인용 데이터는 셀 옆이나 주석에 출처와 일자를 적는다.
- 완료 전 전 시트의 수식 에러를 스캔한다. 저장된 계산 캐시와 재계산 완료 여부는 별도로 검증하며, 캐시가 없거나 재계산을 확인하지 못하면 오류 문자열이 0개여도 계산 결과를 NOT VERIFIED로 보고한다.

```python
errs = ("#REF!", "#DIV/0!", "#VALUE!", "#N/A", "#NAME?", "#NULL!", "#NUM!")
bad = [(ws.title, cell.coordinate, cell.value)
       for ws in wb.worksheets for row in ws.iter_rows() for cell in row
       if isinstance(cell.value, str) and cell.value in errs]
assert not bad, f"수식 에러 발견: {bad}"
```

### 수식 계산 결과 판정 (4상태)

수식 에러 스캔만으로 계산 완료를 판정할 수 없다. `openpyxl`은 수식을 실행하지 않으며 `data_only=True`는 저장된 계산 캐시만 읽는다. 계산 엔진이 실제로 재계산했는지, 필요한 셀에 캐시 값이 존재하는지 각각 확인한다. 수식 문자열 확인에는 `data_only=False`, 캐시 판정에는 `data_only=True`로 같은 시트·셀을 대조한다.

| 상태 | 의미 |
|---|---|
| PASS | 전체 필수 수식이 재계산 엔진에서 처리됐고 캐시 값이 존재하며 오류가 아니고, 기대값이 있는 수식은 기대값과 일치 |
| FAIL | 수식 오류, 필수 계산 결과 누락 또는 기대값 불일치 |
| NOT VERIFIED | 계산 엔진이 없거나 재계산이 완료됐다는 증거가 없거나 캐시를 확인할 수 없음 |
| PARTIAL | 일부 시트·수식·기능만 확인했고 미확인 범위를 기록 |

- `calcMode=auto` 또는 `fullCalcOnLoad` 요청 설정만으로 계산 완료라고 보지 않는다. 재계산에 사용한 엔진·버전·명령, 종료 상태를 기록하고, 재계산된 파일을 다시 열어 확인한다.
- 원본 수식 셀 집합과 재계산본을 대응시켜 수식 소실·수식 변경·캐시 누락을 확인한다. 실제 결과가 빈 값인 수식도 가능하므로 기대값 또는 빈 값 허용 조건을 사례별로 정한다.
- `SUM`, 비율, 날짜 계산처럼 기대값이 명확한 사례로 수식 문자열 보존과 계산 결과 정확성을 따로 검사한다.
- Excel과 LibreOffice 간 함수·피벗·외부 연결 차이, 외부 데이터 갱신 여부는 별도 확인하고 미실행은 NOT VERIFIED 또는 PARTIAL로 남긴다.

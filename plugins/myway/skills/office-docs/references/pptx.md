# PPTX 규격

내장 `pptx` 스킬(pptxgenjs)로 생성하고 편집하되 아래 구조와 토큰 사용 방식을 적용한다. 값은 모두 brand-profile에서 가져온다. 하드코딩한 색·폰트가 없어야 한다.

## 접근성 전제

- 각 슬라이드에 고유한 제목을 두고, 이미지는 의미 있는 대체 텍스트를 갖게 한다. 장식 이미지는 장식임을 표시한다.
- 표는 머리글 행을 지정하고, 색으로만 구분하는 상태·범례를 두지 않는다.
- 제목→본문→주석 순으로 읽기 순서를 점검한다. 화면상의 위치만으로 읽기 순서가 같다고 가정하지 않는다.
- PPTX 생성·구조 검사는 접근성 전체 준수를 증명하지 않는다. 실제 파일의 읽기 순서·대체 텍스트 자동/수동 확인 범위를 보고한다.

## 레이아웃 (13.333 x 7.5 in)

| 요소 | 폰트 | 크기 |
|---|---|---|
| 표지 제목 | heading Bold | 34pt |
| 표지 부제·날짜 | heading Bold | 16pt |
| 챕터 제목 | heading Bold | 36pt |
| 본문 제목 | heading Bold | 24pt |
| 본문 텍스트 | body | 12pt 이상 (색 ink) |
| 푸터 | body | 8~9pt (색 muted) |

발표 환경별 본문 최소 크기: 온라인 24pt, 오프라인 현장 20pt, 문서 공유용 12pt.

### 표지
- 흰 배경. 제목은 charcoal, 좌측 정렬, 중상단.
- 하단에 날짜와 부제. `badge` 값이 있을 때만 뱃지를 둔다.
- `arc: true`일 때만 우상단에 accent→primary 곡선 장식을 그린다.
- 푸터: primary 1.5pt 얇은 선, 좌측 copyright(muted 8.5pt), 우측 wordmark(있을 때만, wordmarkColor).

### 챕터 구분
- 로마숫자 또는 번호, 챕터 제목, 하위 항목 목록.
- 장식 배지는 `badge` 값이 있을 때만.

### 본문
- 최상단 풀폭 primary 바(높이 0.13in).
- 제목은 deep 색, 22~26pt Bold, 좌상단.
- 하단 풀폭 footerBg 바(높이 0.55in)와 line 구분선. 중앙에 쪽번호, 우측에 copyright와 confidential.
- 본문 콘텐츠 영역은 y 1.3~6.7in.
- 제목 하단 장식선은 넣지 않는다. 지정 템플릿에 있을 때만 유지한다.

## 마스터 셋업

```javascript
// T는 brand-profile에서 읽은 값. 아래 필드 이름만 쓴다.
const T = { /* primary, deep, accent, pale, ink, charcoal, muted, line, footerBg,
               heading, body, copyright, confidential, wordmark, wordmarkColor */ };
const WHITE = "FFFFFF";
const footerText = [T.copyright, T.confidential].filter(Boolean).join("   |   ");

pptx.defineSlideMaster({ title: "CONTENT", background: { color: WHITE }, objects: [
  { rect: { x: 0, y: 0, w: "100%", h: 0.13, fill: { color: T.primary } } },
  { rect: { x: 0, y: 6.95, w: "100%", h: 0.55, fill: { color: T.footerBg } } },
  { line: { x: 0, y: 6.95, w: 13.333, h: 0, line: { color: T.line, width: 0.75 } } },
  ...(footerText ? [{ text: { text: footerText, options: {
      x: 6.8, y: 7.04, w: 6.0, h: 0.35, align: "right",
      fontFace: T.body, fontSize: 8.5, color: T.muted } } }] : []),
], slideNumber: { x: 6.4, y: 7.04, w: 0.6, h: 0.35, align: "center",
                  fontFace: T.body, fontSize: 11, color: T.muted } });

pptx.defineSlideMaster({ title: "COVER", background: { color: WHITE }, objects: [
  { line: { x: 0, y: 7.0, w: 13.333, h: 0, line: { color: T.primary, width: 1.5 } } },
  ...(T.copyright ? [{ text: { text: T.copyright, options: {
      x: 0.7, y: 7.08, w: 7, h: 0.35, fontFace: T.body, fontSize: 8.5, color: T.muted } } }] : []),
  ...(T.wordmark ? [{ text: { text: T.wordmark, options: {
      x: 11.4, y: 7.0, w: 1.5, h: 0.4, align: "right",
      fontFace: T.heading, fontSize: 15, bold: true, color: T.wordmarkColor || T.primary } } }] : []),
]});
```

### 표지 본문

```javascript
const s = pptx.addSlide({ masterName: "COVER" });
// arc: true일 때만
// s.addShape(pptx.ShapeType.ellipse, { x: 6.0, y: -5.2, w: 11.5, h: 10, fill: { color: T.accent } });
// s.addShape(pptx.ShapeType.ellipse, { x: 7.2, y: -5.8, w: 11.0, h: 9.6, fill: { color: T.primary } });
s.addText("제목\n부제", { x: 0.75, y: 2.55, w: 9.5, h: 1.6,
  fontFace: T.heading, fontSize: 34, bold: true, color: T.charcoal, lineSpacingMultiple: 1.12 });
s.addText("YYYY.MM.DD", { x: 0.75, y: 5.55, w: 3, h: 0.4,
  fontFace: T.heading, fontSize: 13, bold: true, color: T.charcoal });
```

### 본문 슬라이드

```javascript
const c = pptx.addSlide({ masterName: "CONTENT" });
c.addText("결론을 담은 제목", { x: 0.7, y: 0.45, w: 11.9, h: 0.6,
  fontFace: T.heading, fontSize: 24, bold: true, color: T.deep });
```

## 슬라이드 구성 원칙

- 제목은 섹션 라벨이 아니라 판단을 담은 문장으로 쓴다. 제목만 읽어도 메시지가 전달되게 한다.
- 슬라이드 하나에 핵심 메시지 하나.
- 숫자와 비교 데이터에는 출처를 적는다. 자료에 없는 수치를 만들지 않는다.
- 슬라이드마다 레이아웃을 적절히 바꿔 단조로움을 피한다.
- 슬라이드 수는 발표 시간으로 산정한다. 기본 1장 1.5분. 문서 공유용은 1.5~2배.
- 표와 차트는 이미지가 아니라 편집 가능한 객체로 만든다.

## 표·차트

- 표 헤더: primary 채움 + 흰 Bold. zebra 짝수행 pale. 가로선 line.
- 차트: 1계열 primary, 2계열 accent. 격자선은 옅게. 3D·그림자 금지.

## 검증

```bash
soffice --headless --convert-to pdf out.pptx
pdftoppm -jpeg -r 130 out.pdf slide
unzip -p out.pptx 'ppt/slides/*.xml' | grep -iE "lorem|ipsum|xxxx|샘플|placeholder" && echo "FIX NEEDED"
```

생성 직후 3장짜리 샘플로 방향을 확인한 뒤 전체를 만든다. 이미지로 렌더링해 잘림, 겹침, 대비를 확인하고 고친다.

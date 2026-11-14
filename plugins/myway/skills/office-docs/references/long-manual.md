# 장문 DOCX 매뉴얼 빌드(정적 목차)

장문 기술 매뉴얼을 정적 목차(쪽번호가 박힌 목차)와 함께 DOCX로 빌드한다.
Word 필드형 목차는 LibreOffice 변환 시 갱신되지 않는다. 그래서 PDF로 한 번 변환해 실제 쪽을 측정한 뒤 목차에 숫자를 직접 넣는 2-pass 방식을 쓴다.

## 언제 쓰나

- 운영매뉴얼·운영자 가이드의 신규 빌드 또는 재빌드
- A4 세로, 챕터 다수, 코드 블록과 표가 섞인 기술 문서
- 어떤 뷰어에서도 목차 쪽번호가 정확해야 할 때

## 구성

```
scripts/long-manual/
  fmh.js       스타일 토큰과 요소 헬퍼(heading, body, code, table, pageBreak). 스타일 변경은 여기서만.
  fcontent.js  TITLES 배열과 chapters() 본문. 실제 내용을 채우는 파일(현재는 예시 템플릿).
  fbuild.js    2-pass 빌드 엔진. 진입점.
  gen_toc.py   Pass1 PDF에서 제목별 쪽을 추출해 toc.json 생성.
```

## 실행

```bash
export NODE_PATH="$(npm root -g)"
node scripts/long-manual/fbuild.js "운영매뉴얼_v1.0.docx"
```

- 의존성: `node`(docx 패키지), `libreoffice`(soffice), `poppler-utils`(pdftotext). 없으면 아래 "의존성 설치"의 명령을 쓴다.
- 산출 위치: `OUT_DIR` 환경변수. 지정하지 않으면 현재 디렉터리. 권한이 있는 프로젝트 내부 경로를 지정한다.
- 중간 파일과 LibreOffice 프로필은 산출 위치의 고유 `.rhelman-*` 디렉터리에 남는다. 자동 삭제하지 않으므로 내용을 확인한 뒤 필요한 경우 사용자가 정리한다.
- LibreOffice 변환과 PDF 텍스트 추출은 각각 120초의 프로세스 대기 제한이 있다. 시간 초과는 실패이며 하위 프로세스 전체의 종료를 보장하는 경계는 아니다. Python 실행 파일은 필요하면 `PYTHON` 환경변수로 지정한다.
- 강조색: `MANUAL_ACCENT=<HEX>` (기본 중립 블루). 조직 규격이 있으면 office-docs의 brand-profile primary 값을 넘긴다.
- 목차가 2쪽 이상이면 `TOC_PAGES=<목차 쪽수>`로 보정한다(기본 1).

## 반드시 지킬 함정

1. **동시 수정.** 챕터를 추가·삭제·개명하면 `fcontent.js`의 `TITLES` 배열과 `chapters()` 본문의 H1 제목 문자열을 함께 고친다. 어긋나면 목차에서 해당 항목이 `-`로 나온다.
2. **제목 일치.** `TITLES` 문자열과 본문 `m.heading(..., 1)` 제목은 글자까지 같아야 한다. 공백은 정규화되지만 글자는 일치해야 매칭된다.
3. **쪽 보정.** 목차가 1쪽을 차지한다는 가정으로 추출 쪽에 `TOC_PAGES`(기본 1)를 더한다. 목차가 늘어나면 값을 바꾼다.
4. **산출물 확인.** 빌드가 끝나면 PDF로 변환해 목차 쪽번호와 실제 제목 위치가 맞는지 몇 군데 대조한다. 미발견(`-`) 항목이 없어야 한다.

## 스타일 규격 (fmh.js STYLE)

- 본문 맑은 고딕, 코드 Consolas, A4 세로
- 텍스트 333333, 강조와 코드 좌측 막대는 accent, 코드 배경 F4F5F7
- 표 헤더 행은 accent 배경과 흰 글씨

## 내용 채우기

1. 원본 매뉴얼의 챕터 제목을 순서대로 `TITLES`에 나열한다.
2. `chapters()`에서 제목마다 `m.heading`, `m.body`, `m.code`, `m.table`로 본문을 쓴다.
3. 호스트명, IP, 계정, 고객사명 같은 식별정보는 `<NTP_SERVER>`처럼 파라미터로 치환한다.
4. `node scripts/long-manual/fbuild.js`를 실행하면 목차 쪽번호가 자동으로 채워진다.

## 빌드 절차 상세와 문제 해결

### 2-pass 흐름
| 단계 | 동작 | 산출 |
|---|---|---|
| 1/4 | TOC 없이 본문만 빌드 | `pass1.docx` (임시) |
| 2/4 | `soffice --headless --convert-to pdf` | `pass1.pdf` |
| 3/4 | `gen_toc.py` 가 제목별 첫 등장 페이지 추출 | `toc.json` |
| 4/4 | 정적 TOC(TOC_PAGES 보정, 기본 1)를 맨 앞에 붙여 재빌드 | `$OUT_DIR/<name>` |

중간 파일은 `OUT_DIR` 아래 고유 디렉터리에 보존된다. 공유 임시 경로를 지우지 않는다.

### 의존성 설치 (미설치 환경일 때)
```bash
# Debian/Ubuntu
apt-get install -y libreoffice poppler-utils
# RHEL/Fedora 계열
dnf install -y libreoffice poppler-utils
# node docx 패키지
npm install docx
```

### gen_toc 매칭 원리
- `pdftotext -layout` 출력의 `\x0c`(form feed)로 페이지를 가른다.
- 제목/페이지 텍스트를 공백 제거(`\s+`→"") 후 부분일치로 찾는다.
- 한 제목이 여러 곳에 나오면 **최초 출현 페이지**를 채택.

### 자주 나는 문제
| 증상 | 원인 | 조치 |
|---|---|---|
| 목차 항목이 `-` | TITLES와 본문 제목 불일치 | 두 곳 문자열 일치시키기 |
| 페이지 1씩 밀림 | 목차가 2p 이상 | `TOC_PAGES` 환경변수를 목차 페이지수로 지정 |
| soffice 멈춤/락 | 변환기 응답 지연 또는 프로필 문제 | 시간 초과 및 고유 작업 디렉터리를 확인하고 원인을 조사한다 |
| 한글 깨짐 | 폰트 미설치 | 맑은 고딕 fallback은 soffice 변환용일 뿐, 최종 docx는 폰트 지정만 함(뷰어에 폰트 필요) |
| pdftotext 빈 출력 | PDF 변환 실패 | 2/4 단계 stderr 확인, pass1.docx 수동 변환 테스트 |

### 콘텐츠 대량 작성 팁
- 챕터가 많으면 `chapters()`를 제목별 작은 함수로 쪼개 가독성 확보.
- 코드블록은 `m.code()`에 멀티라인 문자열을 그대로 넘기면 줄바꿈 유지.
- 표는 첫 행이 자동으로 헤더 스타일(파란 배경)이 된다.
- 민감정보(특정 IP·호스트명·계정)는 `<NTP_SERVER>` 같은 파라미터로 치환.

# 외부 저장소 11종 검토 (2026-11-14)

목적은 사용자 지정 저장소의 공개 기능·라이선스 안내를 현재 스킬 마켓플레이스와 비교해 적용 가능한 부분을 찾는 것이다. 표의 커밋은 조회 시 각 원격 HEAD이며, 루트 README와 아래 명시한 라이선스·고지 범위를 중심으로 읽었다. 전체 소스, 의존성, 모든 버전과 실제 실행을 전수 검증한 것은 아니다. 저장소 표시 라이선스는 개별 파일·모델·데이터·의존성의 권리를 일괄 확정하지 않는다.

| 저장소 및 확인한 HEAD | 확인한 기능과 현재 프로젝트의 판단 | 루트 라이선스 표시 및 경계 |
| --- | --- | --- |
| [Open WebUI](https://github.com/open-webui/open-webui/tree/b0e6098e940942281d9c83f3529ea117287a3a22) | 자체 호스팅 모델 인터페이스. UI·서버 실행은 스킬 마켓플레이스 범위 밖이라 도입하지 않는다. | 별도 Open WebUI License와 기존 기여 이력. 브랜드 유지 조건 등 세부 내용은 [LICENSE](https://github.com/open-webui/open-webui/blob/b0e6098e940942281d9c83f3529ea117287a3a22/LICENSE)·이력 확인 필요. |
| [claude-cheat](https://github.com/yjj3019/claude-cheat/tree/9d1b2f09784eed6a75a71b63721c8823f9c5f20d) | 제공자별 라우팅·예산·오류 구분. 실제 백엔드 일치와 도구 호환성은 선언만으로 확정할 수 없어 평가기의 실행 조건 구분 원칙을 유지한다. 라우터는 도입하지 않는다. | MIT 표시. 저장소의 [권리 검토](https://github.com/yjj3019/claude-cheat/blob/9d1b2f09784eed6a75a71b63721c8823f9c5f20d/LICENSE-REVIEW.md)는 기록된 시점과 범위에 한정된다. |
| [TalkAbout](https://github.com/yjj3019/TalkAbout/tree/7f97d500e200037ec37019d8bce84d08a69c6542) | 외부 에이전트 협업에서 참여·연결·실제 발언을 구분하고 권한 범위를 제한한다. 기존 증거 구분과 승인 경계를 유지하며 협업 서버를 추가하지 않는다. | MIT 표시, 의존성·이미지 별도. [고지](https://github.com/yjj3019/TalkAbout/blob/7f97d500e200037ec37019d8bce84d08a69c6542/THIRD_PARTY_NOTICES.md) 확인. |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/tree/39163dd30f703a79079e2d2446545cff3c453738) | 플러그인 방식과 개발 프리뷰의 호환성 변화. 스킬 지침만으로 런타임이 설치·로드됐다고 보지 않는다. 실행 엔진을 가져오지 않는다. | MIT 표시. [제3자 고지](https://github.com/deepseek-ai/deepseek-harness/blob/39163dd30f703a79079e2d2446545cff3c453738/THIRD_PARTY_NOTICES.md)와 구성 요소별 조건 별도. |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent/tree/dc965932a037e3110868b1df5850e510bb4de2ef) | 메모리·도구·승인·다양한 실행 환경을 제공한다. 이 프로젝트에서는 비밀 저장이나 외부 도구 자동 연결 대신 기존 범위·권한 구분을 유지한다. | MIT 표시. 별도 도구, 모델, 설치물의 라이선스는 미확인. |
| [OpenClaw](https://github.com/openclaw/openclaw/tree/48cdab36dde724ad3d1cacc2c91401d3fef52dce) | 메시지 신뢰 경계와 호스트 도구 실행 범위 구분. 검색·첨부 원문을 지시로 승격하지 않는 기준을 추출 근거 절차에 반영한다. | MIT 표시. 확장·의존성·외부 서비스 조건은 별도. |
| [Docling](https://github.com/docling-project/docling/tree/31d14a74b7bddc850541ab8363b8585085845313) | 여러 문서 형식, 레이아웃, 표와 OCR을 다룬다. 추출 결과와 원본의 해당 위치·읽기 순서·표 관계를 분리하는 검토 절차를 추가한다. 실제 엔진은 설치하지 않았다. | [MIT](https://github.com/docling-project/docling/blob/31d14a74b7bddc850541ab8363b8585085845313/LICENSE) 표시. 모델·OCR·의존성·문서 원본의 권리는 별도 확인 필요. |
| [Kiwi](https://github.com/bab2min/Kiwi/tree/e5b270e42d78a8ce56df1a1d4620d26926832c65) | 한국어 형태소·문장 분석. 분절은 후보 검색에 사용하되 원문 부정·수치와 의미 판정의 대체물로 삼지 않는다. 모델을 설치하지 않았다. | Apache-2.0 표시. 학습 자료와 모델에 관한 [NOTICE](https://github.com/bab2min/Kiwi/blob/e5b270e42d78a8ce56df1a1d4620d26926832c65/NOTICE)를 별도 검토해야 한다. |
| [OpenSearch](https://github.com/opensearch-project/OpenSearch/tree/c29f5585917c2803383f42ebf911b5d42efc4799) | 색인과 검색은 자료 탐색 수단이다. 검색 적중만으로 원문 근거·권한·완전성을 판단하지 않는 기준을 적용한다. 서버를 배포하지 않는다. | Apache-2.0 표시, [NOTICE](https://github.com/opensearch-project/OpenSearch/blob/c29f5585917c2803383f42ebf911b5d42efc4799/NOTICE.txt) 존재. 배포물별 의존성은 미확인. |
| [Trafilatura](https://github.com/adbar/trafilatura/tree/8f054a17a68de4634a0b55e056215384aeb6e0a6) | 웹 본문·메타데이터 추출은 원본 표·주석을 누락할 수 있어 원문 대조·출처 위치 기록을 보강한다. 라이브러리는 설치하지 않았다. | 해당 HEAD는 Apache-2.0; README에 1.8.0 이전 GPLv3+로 표기. 버전·의존성별 재검토 필요. |
| [Haystack](https://github.com/deepset-ai/haystack/tree/4b4346b6d798338d9b43e70115006494012b1756) | 검색·라우팅·생성의 단계 분리와 추적 가능성. 원천·검색 조각·변환 결과·판정을 분리한다. 프레임워크나 텔레메트리를 설치하지 않았다. | Apache-2.0 표시. 연동 패키지와 모델은 별도 조건. |

## 반영과 증거 범위

- `research-brief`에 추출 상태, 핵심 원문 위치, 표·단위·부정의 검토 기준을 추가하고 `document-authoring`의 다중 형식 검토에도 적용했다. 기존 스킬 라우팅을 유지한다.
- OCR 단위 누락, 검색 조각의 부정 누락, 표 머리글 누락을 가상의 평가 사례로 추가했다. 단순 문자열 검사는 의미 품질을 보증하지 않는다.
- 외부 저장소의 코드·문장·테스트·모델·이미지·설치 스크립트는 복제하지 않았다. 별도 엔진의 동작을 독립 재구현하거나 그 성능을 재현했다고 주장하지 않는다. 원문과의 유사성·법률 검토 및 과거 프로젝트 계보는 미검증이다.

# Confluence 리포트 형식 예시

아래 내용은 모두 가상 자료이며 실제 취약점 판정에 재사용하지 않는다.

<!-- REPORT START -->
# CVE-2099-00001 - ParserX 입력 검증 누락으로 서비스가 중단될 수 있음

보안등급

Impact : Important
CVSS v3 Base Score : 7.5 (가상 Red Hat 자료)
기준일 : 2099-08-10 (가상 자료)

Environment
-----------

* Red Hat Enterprise Linux 9, 8, 7 (가상)

### 1. 취약점 개요

> A network client can interrupt ParserX by sending a malformed request. (가상 설명)

번역: 네트워크 클라이언트가 잘못된 요청을 보내 ParserX를 중단시킬 수 있습니다.

**문제** ParserX의 입력 검증이 누락되어 서비스가 중단될 수 있습니다.
**해결** RHEL 9 기본 스트림은 확인된 RHSA를 적용합니다. 다른 스트림은 자료를 확인합니다.

**분석 대상 제품**

| RHEL | 패키지 | 상태 | 조치 |
| --- | --- | --- | --- |
| RHEL 9 기본 | parserx | Fixed | RHSA 적용(RHSA-2099:4201) |
| RHEL 8 | parserx | Out of support scope | 미확인 |
| RHEL 7 | parserx | 미확인 | 미확인 |

요약이며 상세 근거는 아래 패키지 표를 참조합니다.

### 2. 영향

* 영향 조건
  * 네트워크에서 잘못된 요청을 보낼 수 있어야 합니다.
* 영향 없음 범위: 미확인.
* 다른 기관의 CVSS 차이: 미확인.

### 3. 완화 방법(Mitigation)

* 임시 조치: 신뢰할 수 없는 입력을 차단합니다.
* 대상 확인 명령은 확인하지 못했습니다.
* 부작용과 원복 절차는 확인하지 못했습니다.
* 완전한 해결은 패치뿐입니다. (가상 공지에서 확인한 내용)

### 4. 추가 정보

* Bugzilla·CWE는 미확인입니다.
* 가상 EPSS 0.02, 백분위 30, 기준일 2099-08-09입니다. 가상 KEV 등재일은 2099-07-15입니다.
* EPSS와 KEV는 RHEL 제품 상태를 판정하는 근거가 아닙니다.
* RHSA 확인 범위는 RHEL 9 기본 스트림입니다. ELS 계약 범위는 미확인입니다.
* 자료 차이: 가상 자료의 업스트림 수정 버전과 배포판 표시 버전은 다릅니다. RPM 비교 결과와 공지를 별도로 확인해야 합니다.

### 5. 결론

1. **RHEL 9 기본 스트림은 수정 빌드가 발행됐습니다.** 확인된 RHSA를 적용합니다.
2. **RHEL 8의 지원 범위와 RHEL 7 상태는 미확인입니다.** 해당 스트림의 지원 및 제품 자료를 확인합니다.

영향을 받는 패키지 및 발행된 레드햇 보안 공지 ( 2099-08-10 기준 )
------------------------------------------

가상 단일 CVE 형식 예시입니다.

| RHEL | Lifecycle | Components | Fixed Package | RHSA | Release Date | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| RHEL 9 | 기본 | parserx | parserx-3.1.2-1.el9.x86_64 | [RHSA-2099:4201](https://access.redhat.com/errata/RHSA-2099:4201) | 2099-07-20 | 가상 자료입니다. |
| RHEL 8 | 지원 종료 | parserx | 미발행 (Out of support scope) | - | - | 가상 자료입니다. |
| RHEL 7 | 기본 | parserx | 평가 데이터 없음 | - | - | 가상 자료입니다. |

표의 판정 범위는 각 행에 기재한 제품 및 스트림입니다. 별도로 확인하지 않은 스트림은 이 표의 결론에 포함하지 않습니다.

참고문서
----

* [가상 CVE-2099-00001 (예시)](https://access.redhat.com/security/cve/CVE-2099-00001)

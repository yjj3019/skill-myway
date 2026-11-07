#!/usr/bin/env python3
"""EPSS와 CISA KEV를 CVE 여러 건에 대해 한 번에 조회한다.

사용법:
    python3 epss_kev.py CVE-YYYY-NNNNN [CVE-YYYY-MMMMM ...]

EPSS: api.first.org를 먼저 호출하고, 네트워크 차단·오류·CVE 불일치인 건만
GitHub 미러(lucacapacci/epss)로 폴백한다. 각 결과의 source_url이 실제 사용한 URL이다.
KEV: cisagov/kev-data 카탈로그를 실행당 한 번만 내려받는다.
결과는 JSON으로 stdout에 출력한다. 표준 라이브러리만 사용한다.
"""
import json
import re
import sys
import urllib.error
import urllib.request

FIRST_URL = "https://api.first.org/data/v1/epss?cve={cves}"
EPSS_URL = "https://raw.githubusercontent.com/lucacapacci/epss/main/data_single/{year}/{cve}.csv"
KEV_URL = "https://raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json"
CVE_RE = re.compile(r"^CVE-(\d{4})-\d{4,}$")
TIMEOUT = 30


def fetch(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": "myway-rhel-cve"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", 200)
        if status != 200:
            raise urllib.error.HTTPError(url, status, f"unexpected HTTP {status}", resp.headers, None)
        return resp.read().decode("utf-8")


def epss_first(cves):
    """api.first.org 일괄 조회. {CVE: 결과} 반환. 전체 실패 시 빈 dict와 오류 문자열."""
    found = {}
    for i in range(0, len(cves), 100):
        chunk = cves[i:i + 100]
        url = FIRST_URL.format(cves=",".join(chunk))
        try:
            data = json.loads(fetch(url, timeout=15))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            return found, f"api.first.org 조회 실패: {e}"
        for row in data.get("data", []):
            cve = str(row.get("cve", "")).upper()
            if cve not in chunk:
                continue  # 요청하지 않은 CVE가 섞여 오면 버린다
            try:
                found[cve] = {
                    "source_url": f"https://api.first.org/data/v1/epss?cve={cve}",
                    "epss_percent": round(float(row["epss"]) * 100, 3),
                    "percentile_percent": round(float(row["percentile"]) * 100, 3),
                    "score_date": row.get("date"),
                    "error": None,
                }
            except (KeyError, ValueError):
                continue
    return found, None


def epss(cve):
    year = CVE_RE.match(cve).group(1)
    url = EPSS_URL.format(year=year, cve=cve)
    result = {"source_url": url, "epss_percent": None, "percentile_percent": None,
              "score_date": None, "error": None}
    try:
        lines = [l.strip() for l in fetch(url).splitlines() if l.strip()]
    except urllib.error.HTTPError as e:
        result["error"] = "미러에 데이터 없음(HTTP 404)" if e.code == 404 else f"HTTP {e.code}"
        return result
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        result["error"] = f"네트워크 오류: {e}"
        return result

    for line in lines:
        m = re.search(r"score_date:(\d{4}-\d{2}-\d{2})", line)
        if m:
            result["score_date"] = m.group(1)
        parts = line.split(",")
        if len(parts) == 3 and parts[0].upper() == cve:
            try:
                result["epss_percent"] = round(float(parts[1]) * 100, 3)
                result["percentile_percent"] = round(float(parts[2]) * 100, 3)
            except ValueError:
                result["error"] = f"CSV 값 해석 실패: {line}"
    if result["epss_percent"] is None and result["error"] is None:
        result["error"] = "CSV에 해당 CVE 행 없음"
    return result


def load_kev():
    try:
        data = json.loads(fetch(KEV_URL))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return None, f"KEV 조회 실패: {e}"
    return data, None


def main(argv):
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2

    cves, invalid = [], []
    for raw in argv:
        cve = raw.strip().upper()
        if not CVE_RE.match(cve):
            invalid.append(raw)
        elif cve not in cves:
            cves.append(cve)
    if invalid:
        print(f"잘못된 CVE ID: {', '.join(invalid)}", file=sys.stderr)
        return 2

    first, first_error = epss_first(cves)
    kev, kev_error = load_kev()
    kev_index = {}
    if kev:
        kev_index = {str(v.get("cveID", "")).upper(): v
                     for v in kev.get("vulnerabilities", []) if isinstance(v, dict)}

    out = {
        "kev_source_url": KEV_URL,
        "kev_catalog_released": kev.get("dateReleased", "")[:10] if kev else None,
        "kev_error": kev_error,
        "epss_first_error": first_error,
        "results": [],
    }
    for cve in cves:
        first_result = first.get(cve)
        epss_result = first_result if first_result is not None else epss(cve)
        entry = {"cve": cve, "epss": epss_result}
        if kev_error:
            entry["kev"] = {"listed": None}
        else:
            hit = kev_index.get(cve)
            entry["kev"] = {"listed": bool(hit)}
            if hit:
                for key in ("dateAdded", "dueDate", "vulnerabilityName",
                            "knownRansomwareCampaignUse"):
                    entry["kev"][key] = hit.get(key)
        out["results"].append(entry)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

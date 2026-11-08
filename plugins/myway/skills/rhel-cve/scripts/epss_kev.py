#!/usr/bin/env python3
"""Retrieve public EPSS scores and CISA KEV membership for CVE identifiers."""
from __future__ import annotations

import csv
import datetime as date_lib
import io
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

EPSS_ENDPOINT = "https://api.first.org/data/v1/epss"
EPSS_BACKUP_ROOT = "https://raw.githubusercontent.com/lucacapacci/epss/main/data_single"
KEV_ENDPOINT = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
CVE_SYNTAX = re.compile(r"CVE-(\d{4})-(\d{4,})\Z", re.IGNORECASE)
REQUEST_AGENT = "skill-myway-rhel-cve/1"
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
REQUEST_GROUP_SIZE = 100
KEV_OUTPUT_FIELDS = ("dateAdded", "dueDate", "vulnerabilityName", "knownRansomwareCampaignUse")


def check_arguments(values: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    valid: list[tuple[str, str]] = []
    rejected: list[str] = []
    known: set[str] = set()
    for value in values:
        key = value.strip().upper()
        match = CVE_SYNTAX.fullmatch(key)
        if match is None:
            rejected.append(value)
            continue
        if key not in known:
            valid.append((key, match.group(1)))
            known.add(key)
    return valid, rejected


def fetch(address: str, timeout: int = 20) -> str:
    request = urllib.request.Request(address, headers={"User-Agent": REQUEST_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise urllib.error.HTTPError(address, status, "unexpected response status", response.headers, None)
        data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("response size limit exceeded")
    return data.decode("utf-8")


def parse_probability(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        return None
    return number


def parse_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date_lib.date.fromisoformat(value)
    except ValueError:
        return None
    return parsed.isoformat() if value == parsed.isoformat() else None


def to_score(record: dict, address: str) -> dict | None:
    score = parse_probability(record.get("epss"))
    percentile = parse_probability(record.get("percentile"))
    recorded = parse_date(record.get("date"))
    if score is None or percentile is None:
        return None
    return {
        "source_url": address,
        "epss_percent": round(score * 100, 3),
        "percentile_percent": round(percentile * 100, 3),
        "score_date": recorded,
        "error": None,
    }


def query_ep_first(identifiers: list[str]) -> tuple[dict[str, dict], dict[str, str]]:
    successful: dict[str, dict] = {}
    unresolved: dict[str, str] = {}
    for offset in range(0, len(identifiers), REQUEST_GROUP_SIZE):
        chunk = identifiers[offset:offset + REQUEST_GROUP_SIZE]
        address = EPSS_ENDPOINT + "?" + urllib.parse.urlencode({"cve": ",".join(chunk)})
        try:
            payload = json.loads(fetch(address, timeout=15))
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ValueError("EPSS response does not contain data array")
        except urllib.error.HTTPError as exc:
            unresolved.update({identifier: f"http_{exc.code}" for identifier in chunk})
            continue
        except (OSError, TimeoutError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            unresolved.update({identifier: "api_unavailable_or_invalid" for identifier in chunk})
            continue

        matching: dict[str, list[dict]] = {}
        for entry in payload["data"]:
            if not isinstance(entry, dict):
                continue
            identifier = entry.get("cve")
            if isinstance(identifier, str):
                identifier = identifier.strip().upper()
                if identifier in chunk:
                    matching.setdefault(identifier, []).append(entry)
        for identifier in chunk:
            candidates = matching.get(identifier, [])
            if len(candidates) != 1:
                unresolved[identifier] = "row_missing_or_ambiguous"
                continue
            score = to_score(candidates[0], address)
            if score is None:
                unresolved[identifier] = "row_invalid"
            else:
                successful[identifier] = score
    return successful, unresolved


def query_backup(identifier: str, year: str) -> dict:
    """Resolve one missing API result from a date-stamped CSV mirror row."""
    address = f"{EPSS_BACKUP_ROOT}/{year}/{identifier}.csv"
    try:
        raw_text = fetch(address)
    except urllib.error.HTTPError as exc:
        return {"source_url": address, "epss_percent": None, "percentile_percent": None,
                "score_date": None, "error": f"backup_http_{exc.code}"}
    except (OSError, TimeoutError, urllib.error.URLError, UnicodeDecodeError, ValueError):
        return {"source_url": address, "epss_percent": None, "percentile_percent": None,
                "score_date": None, "error": "backup_unavailable_or_oversized"}

    observed_day = None
    matched_rows = []
    try:
        records = csv.reader(io.StringIO(raw_text))
        for record in records:
            if not record:
                continue
            note = ",".join(record)
            day_match = re.search(r"score_date:(\d{4}-\d{2}-\d{2})", note)
            if day_match:
                observed_day = day_match.group(1)
            if len(record) == 3 and record[0].strip().upper() == identifier:
                matched_rows.append(record)
    except csv.Error:
        return {"source_url": address, "epss_percent": None, "percentile_percent": None,
                "score_date": None, "error": "backup_csv_invalid"}

    if len(matched_rows) != 1:
        return {"source_url": address, "epss_percent": None, "percentile_percent": None,
                "score_date": observed_day, "error": "backup_row_missing_or_ambiguous"}
    row = {"epss": matched_rows[0][1], "percentile": matched_rows[0][2], "date": observed_day}
    score = to_score(row, address)
    if score is None:
        return {"source_url": address, "epss_percent": None, "percentile_percent": None,
                "score_date": observed_day, "error": "backup_row_invalid"}
    return score


def query_kev() -> tuple[dict | None, str | None]:
    try:
        payload = json.loads(fetch(KEV_ENDPOINT))
    except urllib.error.HTTPError as exc:
        return None, f"http_{exc.code}"
    except (OSError, TimeoutError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None, "catalog_unavailable_or_invalid"
    if not isinstance(payload, dict) or not isinstance(payload.get("vulnerabilities"), list):
        return None, "catalog_schema_invalid"
    release = payload.get("dateReleased")
    if parse_date(release) is None:
        return None, "catalog_metadata_invalid"
    count = payload.get("count")
    entries = payload["vulnerabilities"]
    if isinstance(count, bool) or not isinstance(count, int) or count != len(entries):
        return None, "catalog_count_mismatch"
    index: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            return None, "catalog_entry_invalid"
        identifier = entry.get("cveID")
        if not isinstance(identifier, str):
            return None, "catalog_entry_invalid"
        key = identifier.strip().upper()
        if CVE_SYNTAX.fullmatch(key) is None:
            return None, "catalog_entry_invalid"
        if key in index:
            return None, "catalog_duplicate_id"
        index[key] = entry
    return {"released": release, "index": index}, None


def lookup(values: list[str]) -> tuple[dict | None, int]:
    normalized, bad = check_arguments(values)
    if bad or not normalized:
        return None, 2
    ids = [identifier for identifier, _year in normalized]
    epss, epss_errors = query_ep_first(ids)
    catalog, catalog_error = query_kev()
    rows = []
    for identifier, year in normalized:
        result = epss.get(identifier)
        if result is None:
            api_error = epss_errors.get(identifier, "no_usable_record")
            result = query_backup(identifier, year)
            if result["error"] is None:
                result["api_error"] = api_error
            else:
                result["api_error"] = api_error
        if catalog is None:
            kev_result = {"listed": None, "error": catalog_error}
        else:
            record = catalog["index"].get(identifier)
            kev_result = {"listed": record is not None}
            if record is not None:
                for field in KEV_OUTPUT_FIELDS:
                    if field in record:
                        kev_result[field] = record[field]
        rows.append({"cve": identifier, "epss": result, "kev": kev_result})
    document = {
        "kev_source_url": KEV_ENDPOINT,
        "kev_catalog_released": catalog["released"] if catalog is not None else None,
        "kev_error": catalog_error,
        "results": rows,
    }
    incomplete = catalog is None or any(row["epss"]["error"] is not None for row in rows)
    return document, 1 if incomplete else 0


def main(values: list[str]) -> int:
    if not values:
        print(__doc__, file=sys.stderr)
        return 2
    document, status = lookup(values)
    if document is None:
        print("Invalid CVE identifier; use CVE-YYYY-NNNN+", file=sys.stderr)
        return status
    print(json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

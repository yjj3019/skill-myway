import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "plugins/myway/skills/rhel-cve/scripts/epss_kev.py"
SPEC = importlib.util.spec_from_file_location("rhel_epss_kev", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IdentifierInputs(unittest.TestCase):
    def test_normalizes_case_and_removes_duplicates(self):
        accepted, rejected = MODULE.check_arguments([" cve-2099-00001 ", "CVE-2099-00001", "CVE-2099-00002"])
        self.assertEqual(accepted, [("CVE-2099-00001", "2099"), ("CVE-2099-00002", "2099")])
        self.assertEqual(rejected, [])

    def test_rejects_invalid_values(self):
        accepted, rejected = MODULE.check_arguments(["no-id", "CVE-2099-123"])
        self.assertEqual(accepted, [])
        self.assertEqual(rejected, ["no-id", "CVE-2099-123"])

    def test_invalid_input_stops_before_network(self):
        with mock.patch.object(MODULE, "fetch", side_effect=AssertionError("network called")):
            output, code = MODULE.lookup(["CVE-2099-00001", "bad"])
        self.assertIsNone(output)
        self.assertEqual(code, 2)

    def test_lookup_uses_backup_only_when_first_api_has_no_row(self):
        identifier = "CVE-2099-00001"
        backup = {"source_url": "csv", "epss_percent": 12.5, "percentile_percent": 40.0,
                  "score_date": "2099-08-10", "error": None}
        with mock.patch.object(MODULE, "query_ep_first", return_value=({}, {identifier: "row_invalid"})) as first, mock.patch.object(MODULE, "query_backup", return_value=backup) as fallback, mock.patch.object(MODULE, "query_kev", return_value=({"released": "2099-08-10", "index": {}}, None)):
            document, code = MODULE.lookup([identifier])
        fallback.assert_called_once_with(identifier, "2099")
        self.assertEqual(code, 0)
        self.assertEqual(document["results"][0]["epss"]["epss_percent"], 12.5)
        self.assertEqual(document["results"][0]["epss"]["api_error"], "row_invalid")


class FirstOrgResponse(unittest.TestCase):
    def test_accepts_exact_id_and_valid_probabilities(self):
        address = MODULE.EPSS_ENDPOINT + "?cve=CVE-2099-00001%2CCVE-2099-00002"
        body = json.dumps({"data": [
            {"cve": "CVE-2099-00001", "epss": "0.25", "percentile": "0.8", "date": "2099-08-10"},
            {"cve": "CVE-2099-00002", "epss": "NaN", "percentile": 0.3, "date": "2099-08-10"},
            {"cve": "CVE-2099-99999", "epss": 0.2, "percentile": 0.2, "date": "2099-08-10"},
        ]})
        with mock.patch.object(MODULE, "fetch", return_value=body):
            rows, failures = MODULE.query_ep_first(["CVE-2099-00001", "CVE-2099-00002"])
        self.assertEqual(rows["CVE-2099-00001"]["source_url"], address)
        self.assertEqual(rows["CVE-2099-00001"]["epss_percent"], 25.0)
        self.assertEqual(failures, {"CVE-2099-00002": "row_invalid"})

    def test_duplicate_rows_are_not_resolved_arbitrarily(self):
        row = {"cve": "CVE-2099-00001", "epss": 0.2, "percentile": 0.3, "date": "2099-08-10"}
        with mock.patch.object(MODULE, "fetch", return_value=json.dumps({"data": [row, row]})):
            found, failures = MODULE.query_ep_first(["CVE-2099-00001"])
        self.assertEqual(found, {})
        self.assertEqual(failures, {"CVE-2099-00001": "row_missing_or_ambiguous"})

    def test_invalid_response_shape_fails_closed(self):
        with mock.patch.object(MODULE, "fetch", return_value="{}"):
            found, failures = MODULE.query_ep_first(["CVE-2099-00001"])
        self.assertEqual(found, {})
        self.assertEqual(failures, {"CVE-2099-00001": "api_unavailable_or_invalid"})

    def test_missing_date_does_not_invalidate_score(self):
        row = {"cve": "CVE-2099-00001", "epss": 0.2, "percentile": 0.3}
        with mock.patch.object(MODULE, "fetch", return_value=json.dumps({"data": [row]})):
            found, failures = MODULE.query_ep_first(["CVE-2099-00001"])
        self.assertEqual(found["CVE-2099-00001"]["score_date"], None)
        self.assertEqual(failures, {})


class BackupRows(unittest.TestCase):
    def test_one_identifier_csv_row_is_accepted(self):
        text = "\n".join(["#version:v1,score_date:2099-08-10", "cve,epss,percentile", "CVE-2099-00001,0.125,0.75", ""])
        with mock.patch.object(MODULE, "fetch", return_value=text):
            result = MODULE.query_backup("CVE-2099-00001", "2099")
        self.assertEqual(result["epss_percent"], 12.5)
        self.assertEqual(result["percentile_percent"], 75.0)
        self.assertEqual(result["score_date"], "2099-08-10")
        self.assertIsNone(result["error"])

    def test_no_matching_row_is_error_not_zero(self):
        text = "\n".join(["#version:v1,score_date:2099-08-10", "CVE-2099-00002,0.125,0.75", ""])
        with mock.patch.object(MODULE, "fetch", return_value=text):
            result = MODULE.query_backup("CVE-2099-00001", "2099")
        self.assertIsNone(result["epss_percent"])
        self.assertEqual(result["error"], "backup_row_missing_or_ambiguous")


class KevCatalog(unittest.TestCase):
    @staticmethod
    def valid_catalog(entries=None):
        items = entries if entries is not None else []
        return {"dateReleased": "2099-08-10", "count": len(items), "vulnerabilities": items}

    def test_catalog_load_failure_remains_unknown(self):
        with mock.patch.object(MODULE, "fetch", side_effect=OSError("offline")):
            catalog, error = MODULE.query_kev()
        self.assertIsNone(catalog)
        self.assertEqual(error, "catalog_unavailable_or_invalid")

    def test_malformed_catalog_is_not_an_empty_catalog(self):
        with mock.patch.object(MODULE, "fetch", return_value=json.dumps({"vulnerabilities": []})):
            catalog, error = MODULE.query_kev()
        self.assertIsNone(catalog)
        self.assertEqual(error, "catalog_metadata_invalid")

    def test_count_mismatch_fails_closed(self):
        payload = self.valid_catalog()
        payload["count"] = 1
        with mock.patch.object(MODULE, "fetch", return_value=json.dumps(payload)):
            catalog, error = MODULE.query_kev()
        self.assertIsNone(catalog)
        self.assertEqual(error, "catalog_count_mismatch")

    def test_duplicate_ids_fail_closed(self):
        duplicate = {"cveID": "CVE-2099-00001"}
        payload = self.valid_catalog([duplicate, duplicate])
        with mock.patch.object(MODULE, "fetch", return_value=json.dumps(payload)):
            catalog, error = MODULE.query_kev()
        self.assertIsNone(catalog)
        self.assertEqual(error, "catalog_duplicate_id")

    def test_good_empty_catalog_is_valid(self):
        with mock.patch.object(MODULE, "fetch", return_value=json.dumps(self.valid_catalog())):
            catalog, error = MODULE.query_kev()
        self.assertEqual(error, None)
        self.assertEqual(catalog["index"], {})


class CombinedLookup(unittest.TestCase):
    def test_valid_sources_return_success(self):
        identifier = "CVE-2099-00001"
        score = {"source_url": "api", "epss_percent": 20.0, "percentile_percent": 30.0,
                 "score_date": "2099-08-10", "error": None}
        catalog = {"released": "2099-08-10", "index": {identifier: {"dateAdded": "2099-08-01"}}}
        with mock.patch.object(MODULE, "query_ep_first", return_value=({identifier: score}, {})), \
             mock.patch.object(MODULE, "query_kev", return_value=(catalog, None)):
            result, code = MODULE.lookup([identifier])
        self.assertEqual(code, 0)
        self.assertEqual(result["results"][0]["kev"]["listed"], True)
        self.assertEqual(result["results"][0]["kev"]["dateAdded"], "2099-08-01")

    def test_unknown_kev_and_missing_epss_return_partial_status(self):
        with mock.patch.object(MODULE, "query_ep_first", return_value=({}, {"CVE-2099-00001": "row_invalid"})), \
             mock.patch.object(MODULE, "query_kev", return_value=(None, "catalog_unavailable_or_invalid")):
            result, code = MODULE.lookup(["CVE-2099-00001"])
        self.assertEqual(code, 1)
        self.assertIsNone(result["results"][0]["kev"]["listed"])
        self.assertEqual(result["results"][0]["epss"]["error"], "backup_http_404")
        self.assertEqual(result["results"][0]["epss"]["api_error"], "row_invalid")


if __name__ == "__main__":
    unittest.main()

import copy
import io
import hashlib
import json
import sys
import subprocess
import zipfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import design_review_gate as gate


def digest(data):
    return hashlib.sha256(data).hexdigest()


class DesignReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "deck.pptx").write_bytes(b"synthetic source")
        (self.root / "page-1.png").write_bytes(b"synthetic render one")
        (self.root / "page-2.png").write_bytes(b"synthetic render two")
        source = {"path": "deck.pptx", "sha256": digest(b"synthetic source")}
        surfaces = []
        for number, content in ((1, b"synthetic render one"), (2, b"synthetic render two")):
            image = {"path": f"page-{number}.png", "sha256": digest(content)}
            surfaces.append({"index": number, "render": image,
                             "review": {"source_sha256": source["sha256"], "render_sha256": image["sha256"],
                                        "status": "PASS", "open_critical": 0, "open_major": 0}})
        self.manifest = {"schema_version": 1, "artifacts": [{"id": "example", "kind": "pptx",
                                                               "source": source, "surfaces": surfaces}]}

    def test_integrity_never_proves_quality_or_renders(self):
        result = gate.check(self.root, self.manifest)
        self.assertEqual(result["evidence_integrity"], "PASS")
        self.assertEqual(result["artifacts"][0]["declared_status"], "PASS")
        self.assertEqual(result["verdict"], "NOT VERIFIED")

    def measured_manifest(self):
        item = copy.deepcopy(self.manifest)
        item["schema_version"] = 2
        for surface in item["artifacts"][0]["surfaces"]:
            surface["measurements"] = [
                {"name": "clipped titles", "value": 0, "unit": "titles", "location": "top heading"}
            ]
        return item

    def test_measured_zero_and_unknown_have_distinct_outcomes(self):
        item = self.measured_manifest()
        def summary():
            return gate.check(self.root, item)["artifacts"][0]
        self.assertEqual(summary()["declared_status"], "PASS")
        self.assertEqual(summary()["measured"], 2)
        second = item["artifacts"][0]["surfaces"][1]
        second["measurements"] = [{"name": "contrast", "reason": "background unavailable"}]
        self.assertEqual(summary()["declared_status"], "NOT VERIFIED")
        self.assertEqual((summary()["measured"], summary()["unmeasured"]), (1, 1))
        second["review"]["open_major"] = 1
        self.assertEqual(summary()["declared_status"], "FAIL")

    def test_measurement_requires_finite_value_location_or_reason(self):
        item = self.measured_manifest()
        surface = item["artifacts"][0]["surfaces"][0]
        good = surface["measurements"][0]
        for rows in ([], [good, good], [dict(good, value=True)], [dict(good, value=float("inf"))],
                     [dict(good, value="3")], [dict(good, location=" ")], [dict(good, reason="mixed")],
                     [{"name": "contrast", "reason": " "}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                surface["measurements"] = rows
                gate.check(self.root, item)

    def planned_capture(self):
        manifest = self.measured_manifest()
        manifest["schema_version"] = 3
        artifact = manifest["artifacts"][0]
        sizes = {}
        for index, surface in enumerate(artifact["surfaces"], 1):
            buffer = io.BytesIO()
            size = [10 * index, 8]
            Image.new("RGB", size).save(buffer, format="PNG")
            name = surface["render"]["path"]
            data = buffer.getvalue()
            (self.root / name).write_bytes(data)
            surface["render"]["sha256"] = surface["review"]["render_sha256"] = digest(data)
            sizes[name] = size
        plan = {"schema_version": 1, "artifacts": {"example": {
            "source_sha256": artifact["source"]["sha256"], "surfaces": sizes}}}
        return manifest, plan

    def test_plan_verifies_png_pixels_and_reports_missing_last_surface(self):
        manifest, plan = self.planned_capture()
        result = gate.check(self.root, manifest, plan)
        self.assertEqual(result["plan_coverage"]["status"], "PASS")
        self.assertEqual(result["verdict"], "NOT VERIFIED")
        only_second = copy.deepcopy(manifest)
        only_second["artifacts"][0]["surfaces"].pop(0)
        self.assertEqual(gate.check(self.root, only_second, plan)["plan_coverage"]["missing"],
                         [("example", "page-1.png")])
        manifest["artifacts"][0]["surfaces"].pop()
        result = gate.check(self.root, manifest, plan)
        self.assertEqual(result["plan_coverage"]["missing"], [("example", "page-2.png")])
        self.assertEqual(result["verdict"], "FAIL")
        manifest["artifacts"] = []
        self.assertEqual(len(gate.check(self.root, manifest, plan)["plan_coverage"]["missing"]), 2)

    def test_plan_reports_unexpected_dimensions_source_and_extra_surfaces(self):
        manifest, plan = self.planned_capture()
        expected = plan["artifacts"]["example"]
        del expected["surfaces"]["page-2.png"]
        expected["surfaces"]["page-1.png"] = [11, 8]
        expected["source_sha256"] = "0" * 64
        coverage = gate.check(self.root, manifest, plan)["plan_coverage"]
        self.assertEqual(coverage["status"], "FAIL")
        self.assertEqual(coverage["size_mismatches"][0]["observed"], [10, 8])
        self.assertEqual(coverage["source_mismatches"], ["example"])
        self.assertEqual(coverage["unexpected"], [("example", "page-2.png")])

    def test_plan_refuses_downgrade_and_hash_matching_nonimage(self):
        manifest, plan = self.planned_capture()
        with self.assertRaises(ValueError):
            gate.check(self.root, manifest)
        manifest["schema_version"] = 2
        with self.assertRaises(ValueError):
            gate.check(self.root, manifest, plan)
        manifest["schema_version"] = 3
        surface = manifest["artifacts"][0]["surfaces"][0]
        (self.root / "page-1.png").write_bytes(b"not an image")
        surface["render"]["sha256"] = surface["review"]["render_sha256"] = digest(b"not an image")
        with self.assertRaises(ValueError):
            gate.check(self.root, manifest, plan)

    def test_standalone_zip_checks_actual_chrome_captures_and_omission(self):
        import package_skill
        fixture = Path(__file__).resolve().parents[1] / "benchmarks/render-coverage"
        archive, _, _ = package_skill.build(package_skill.SKILLS / "visual-design", self.root, "test")
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(self.root)
        checker = self.root / "visual-design/scripts/check_design_review.py"
        manifest = self.root / "observations.json"
        data = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
        for expected_code in (0, 1):
            manifest.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run([sys.executable, str(checker), str(fixture), str(manifest),
                                     "--plan", str(fixture / "plan.json")], cwd=self.root,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, expected_code, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["plan_coverage"]["planned"], 2)
            self.assertEqual(report["plan_coverage"]["observed"], 2 - expected_code)
            if expected_code:
                self.assertEqual(report["plan_coverage"]["missing"], [["weekly-review", "wide.png"]])
            else:
                self.assertEqual(report["verdict"], "NOT VERIFIED")
                data["artifacts"][0]["surfaces"].pop()

    def test_changed_source_or_render_rejects_old_review(self):
        for name in ("deck.pptx", "page-1.png"):
            with self.subTest(name=name):
                path = self.root / name
                before = path.read_bytes()
                path.write_bytes(b"replacement")
                with self.assertRaises(ValueError):
                    gate.check(self.root, self.manifest)
                path.write_bytes(before)

    def test_review_cannot_follow_new_artifact_or_render_silently(self):
        for key in ("source_sha256", "render_sha256"):
            with self.subTest(key=key):
                item = copy.deepcopy(self.manifest)
                item["artifacts"][0]["surfaces"][0]["review"][key] = "0" * 64
                with self.assertRaises(ValueError):
                    gate.check(self.root, item)

    def test_open_major_or_critical_prevents_pass(self):
        for key in ("open_critical", "open_major"):
            with self.subTest(key=key):
                item = copy.deepcopy(self.manifest)
                item["artifacts"][0]["surfaces"][1]["review"][key] = 1
                result = gate.check(self.root, item)
                self.assertEqual(result["verdict"], "FAIL")

    def test_missing_unreviewed_or_duplicated_page(self):
        item = copy.deepcopy(self.manifest)
        item["artifacts"][0]["surfaces"][1]["index"] = 3
        with self.assertRaises(ValueError):
            gate.check(self.root, item)
        item = copy.deepcopy(self.manifest)
        item["artifacts"][0]["surfaces"][1] = copy.deepcopy(item["artifacts"][0]["surfaces"][0])
        item["artifacts"][0]["surfaces"][1]["index"] = 2
        with self.assertRaises(ValueError):
            gate.check(self.root, item)
        item = copy.deepcopy(self.manifest)
        item["artifacts"][0]["surfaces"][1]["review"]["status"] = "NOT VERIFIED"
        self.assertEqual(gate.check(self.root, item)["artifacts"][0]["declared_status"], "NOT VERIFIED")

    def test_rejects_path_escape_and_link(self):
        for path in ("../outside", "C:/outside", "page-1.png:stream", "NUL", "./page-1.png"):
            with self.subTest(path=path):
                item = copy.deepcopy(self.manifest)
                item["artifacts"][0]["source"]["path"] = path
                with self.assertRaises((OSError, ValueError)):
                    gate.check(self.root, item)
        linked = self.root.resolve(strict=True) / "page-1.png"
        original = Path.is_symlink
        with mock.patch.object(Path, "is_symlink", lambda p: p == linked or original(p)):
            with self.assertRaises(ValueError):
                gate.check(self.root, self.manifest)

    def test_schema_rejects_boolean_indices_and_counts(self):
        for target in ("index", "open_major", "schema_version"):
            with self.subTest(target=target):
                item = copy.deepcopy(self.manifest)
                if target == "schema_version":
                    item[target] = True
                elif target == "index":
                    item["artifacts"][0]["surfaces"][0][target] = True
                else:
                    item["artifacts"][0]["surfaces"][0]["review"][target] = True
                with self.assertRaises(ValueError):
                    gate.check(self.root, item)

    def test_cli_reports_integrity_but_returns_nonzero(self):
        path = self.root / "manifest.json"
        path.write_text(json.dumps(self.manifest), encoding="utf-8")
        self.assertEqual(gate.main([str(self.root), str(path)]), 1)
        path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        self.assertEqual(gate.main([str(self.root), str(path)]), 1)


if __name__ == "__main__":
    unittest.main()

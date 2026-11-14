import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

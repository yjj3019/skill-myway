import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import doctor


class DoctorTests(unittest.TestCase):
    def test_all_found_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(doctor.shutil, "which", return_value="/usr/bin/claude"):
            (Path(tmp) / "skills" / "myway").mkdir(parents=True)
            self.assertEqual(doctor.run(["claude"], home=tmp), 0)

    def test_missing_executable_reports_need_and_hint(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(doctor.shutil, "which", return_value="/usr/bin/claude"):
            with mock.patch.object(doctor.shutil, "which", return_value=None) as which:
                self.assertEqual(doctor.run(["claude"], home=tmp), 1)
            which.assert_called_once()
            (Path(tmp) / "skills" / "myway").mkdir(parents=True)

    def test_missing_directory_returns_one(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(doctor.shutil, "which", return_value="/usr/bin/grok"):
            self.assertEqual(doctor.run(["grok"], home=tmp), 1)

    def test_check_fields_are_name_found_need_hint(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(doctor.shutil, "which", return_value=None):
            check = doctor.checks_for("codex", home=tmp)[0]
            self.assertEqual(check.name, "codex 실행 파일")
            self.assertFalse(check.found)
            self.assertTrue(check.need)
            self.assertTrue(check.hint)

    def test_platform_filter_selects_only_one(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(doctor.shutil, "which", side_effect=[None, "/usr/bin/codex"]):
            (Path(tmp) / "skills" / "myway").mkdir(parents=True)
            self.assertEqual(doctor.run(["claude"], home=tmp), 1)
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(doctor.shutil, "which", return_value="/usr/bin/codex"):
            (Path(tmp) / "skills" / "myway").mkdir(parents=True)
            self.assertEqual(doctor.run(["codex"], home=tmp), 0)


if __name__ == "__main__":
    unittest.main()

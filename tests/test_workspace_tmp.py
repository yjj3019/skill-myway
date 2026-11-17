import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import workspace_tmp


class WorkspaceTempTests(unittest.TestCase):
    def test_temp_root_stays_inside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(workspace_tmp, "ROOT", Path(tmp)):
            result = workspace_tmp.temp_root()
            self.assertTrue(result.resolve().is_relative_to(Path(tmp).resolve()))
            self.assertEqual(result.name, ".myway-tmp")

    def test_existing_link_is_rejected_before_creation(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(workspace_tmp, "ROOT", Path(tmp)), \
             mock.patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ValueError):
                workspace_tmp.temp_root()
            self.assertFalse((Path(tmp) / ".myway-tmp").exists())


if __name__ == "__main__":
    unittest.main()

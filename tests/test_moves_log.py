import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import moves_log


class MovesLogTests(unittest.TestCase):
    def test_log_path_uses_localappdata_on_windows(self):
        with mock.patch.object(moves_log.os, "name", "nt"), \
             mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\state"}, clear=True):
            self.assertEqual(moves_log.log_path(), Path(os.path.join(r"C:\state", "myway", "moves.jsonl")))

    def test_log_path_uses_xdg_state_home_then_local_state(self):
        with mock.patch.object(moves_log.os, "name", "posix"), \
             mock.patch.dict(os.environ, {"XDG_STATE_HOME": "/xdg", "HOME": "/home"}, clear=True):
            self.assertEqual(moves_log.log_path(), Path(os.path.join("/xdg", "myway", "moves.jsonl")))
        with mock.patch.object(moves_log.os, "name", "posix"), \
             mock.patch.dict(os.environ, {"HOME": "/home"}, clear=True):
            self.assertEqual(
                moves_log.log_path(),
                Path(os.path.join(os.path.join("/home", ".local", "state"), "myway", "moves.jsonl")))

    def test_missing_base_raises(self):
        with mock.patch.object(moves_log.os, "name", "posix"), \
             mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(OSError):
                moves_log.log_path()

    def test_no_log_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(moves_log, "log_path", return_value=Path(tmp) / "moves.jsonl"):
            self.assertEqual(
                moves_log.run(["--skill", "devlog", "--kind", "fallback", "--note", "임시", "--no-log"]), 0)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_append_writes_jsonl_line(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(moves_log, "log_path", return_value=Path(tmp) / "moves.jsonl"):
            self.assertEqual(moves_log.run(["--skill", "devlog", "--kind", "notion", "--note", "세션 마감"]), 0)
            lines = (Path(tmp) / "moves.jsonl").read_text(encoding="utf-8").splitlines()
            record = json.loads(lines[0])
            self.assertEqual(record["skill"], "devlog")
            self.assertEqual(record["kind"], "notion")
            self.assertEqual(record["note"], "세션 마감")
            self.assertIn("ts", record)

    def test_failure_returns_one(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(moves_log, "log_path", return_value=Path(tmp) / "moves.jsonl"), \
             mock.patch.object(Path, "mkdir", side_effect=OSError("거부됨")):
            self.assertEqual(moves_log.run(["--skill", "devlog", "--kind", "fallback"]), 1)


if __name__ == "__main__":
    unittest.main()

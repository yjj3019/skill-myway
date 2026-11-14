import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import process_control
import windows_job

# Fixtures only use the standard library. Avoid Windows virtualenv redirectors
# at every generation, which measure interpreter startup rather than containment.
FIXTURE_PYTHON = windows_job.bootstrap_python() if sys.platform == "win32" else sys.executable


class ProcessControl(unittest.TestCase):
    def test_drain_after_kill_bounds_escaped_pipe_wait(self):
        process = mock.MagicMock()
        original = subprocess.TimeoutExpired("command", 1, output=b"partial", stderr=b"warning")
        process.communicate.side_effect = subprocess.TimeoutExpired("command", 1, output=b"more")
        stdout, stderr = process_control._drain_after_kill(process, original)
        self.assertEqual((stdout, stderr), (b"more", b"warning"))
        process.communicate.assert_called_once_with(timeout=1)
        process.stdout.close.assert_called_once()
        process.stderr.close.assert_called_once()
        process.wait.assert_called_once_with(timeout=1)

    def test_drain_after_kill_returns_completed_output(self):
        process = mock.MagicMock()
        process.communicate.return_value = ("done", "")
        original = subprocess.TimeoutExpired("command", 1)
        self.assertEqual(process_control._drain_after_kill(process, original), ("done", ""))
        process.stdout.close.assert_not_called()

    def test_windows_failed_assignment_never_releases_payload(self):
        if sys.platform != "win32":
            return
        kernel = mock.MagicMock()
        kernel.CreateJobObjectW.return_value = 11
        kernel.SetInformationJobObject.return_value = True
        kernel.AssignProcessToJobObject.return_value = False
        child = mock.MagicMock()
        child._handle = 12
        child.poll.return_value = None
        with mock.patch.object(windows_job.ctypes, "WinDLL", return_value=kernel), \
             mock.patch.object(windows_job.subprocess, "Popen", return_value=child):
            with self.assertRaises(OSError):
                windows_job.run(["payload"], cwd=None, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=4)
        child.communicate.assert_not_called()
        child.kill.assert_called_once()
        child.wait.assert_called_once()

    def test_normal_output_and_return_code(self):
        result = process_control.run([sys.executable, "-c", "print('ok')"], cwd=None,
                                     stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_requested_python_environment_and_large_output_are_preserved(self):
        result = process_control.run([sys.executable, "-c",
                                      "import sys; print(sys.prefix); print('x'*131072); sys.exit(7)"],
                                     cwd=None, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=10)
        self.assertEqual(result.returncode, 7)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], sys.prefix)
        self.assertEqual(lines[1], "x" * 131072)

    def test_normal_exit_closes_inherited_output_pipes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready, late = Path(tmp) / "ready", Path(tmp) / "late"
            child = ("import sys,time; from pathlib import Path; "
                     "Path(sys.argv[1]).write_text('started'); time.sleep(12); "
                     "Path(sys.argv[2]).write_text('survived')")
            parent = ("import subprocess,sys,time; from pathlib import Path; "
                      "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]]); "
                      "deadline=time.monotonic()+5; "
                      "exec('while not Path(sys.argv[2]).exists() and time.monotonic()<deadline:\\n time.sleep(0.05)')")
            if sys.platform != "win32":
                # POSIX currently cannot drain inherited pipes until its timeout.
                return
            result = process_control.run([FIXTURE_PYTHON, "-I", "-S", "-B", "-c", parent, child, str(ready), str(late)],
                                         cwd=tmp, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                         encoding="utf-8", errors="replace", timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertTrue(ready.exists())
            self.assertFalse(late.exists())

    def test_timeout_stops_child_and_grandchild(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready = Path(tmp) / "ready"
            late = Path(tmp) / "late"
            release = Path(tmp) / "release"
            grandchild = ("import sys,time; from pathlib import Path; "
                          "Path(sys.argv[1]).write_text('started'); "
                          "deadline=time.monotonic()+60; "
                          "exec('while not Path(sys.argv[3]).exists() and time.monotonic()<deadline:\\n time.sleep(0.05)'); "
                          "Path(sys.argv[2]).write_text('survived') if Path(sys.argv[3]).exists() else None")
            child = ("import subprocess,sys,time; "
                     "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]]); "
                     "time.sleep(60)")
            parent = ("import subprocess,sys,time; "
                      "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5]]); "
                      "time.sleep(60)")
            command = [FIXTURE_PYTHON, "-I", "-S", "-B", "-c", parent, child, grandchild, str(ready), str(late), str(release)]
            with self.assertRaises(subprocess.TimeoutExpired):
                process_control.run(command, cwd=tmp, stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=20)
            self.assertTrue(ready.exists(), "grandchild must start before the timeout")
            # A survivor must react to a signal sent after timeout, even if it
            # started immediately before the deadline. This avoids a false pass
            # based on a fixed delay measured from its own start.
            release.write_text("release", encoding="utf-8")
            time.sleep(7)
            self.assertFalse(late.exists(), "grandchild survived the process container")

    def test_short_timeout_is_not_delayed_until_descendant_ready(self):
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            process_control.run([FIXTURE_PYTHON, "-I", "-S", "-B", "-c", "import time; time.sleep(30)"],
                                cwd=None, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=1)
        self.assertLess(time.monotonic() - started, 15, "short timeout must not wait for the payload to finish")

    def test_release_signal_detects_a_surviving_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready, release, late = (Path(tmp) / name for name in ("ready", "release", "late"))
            child = ("import sys,time; from pathlib import Path; "
                     "Path(sys.argv[1]).write_text('started'); deadline=time.monotonic()+30; "
                     "exec('while not Path(sys.argv[2]).exists() and time.monotonic()<deadline:\\n time.sleep(0.05)'); "
                     "Path(sys.argv[3]).write_text('survived') if Path(sys.argv[2]).exists() else None")
            process = subprocess.Popen([FIXTURE_PYTHON, "-I", "-S", "-B", "-c", child,
                                        str(ready), str(release), str(late)],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 20
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(ready.exists(), "control process must start")
                release.write_text("release", encoding="utf-8")
                process.wait(timeout=10)
                self.assertTrue(late.exists(), "the signal must expose a surviving process")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)

    def test_normal_exit_stops_background_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready, late = Path(tmp) / "ready", Path(tmp) / "late"
            child = ("import sys,time; from pathlib import Path; "
                     "Path(sys.argv[1]).write_text('started'); time.sleep(6); "
                     "Path(sys.argv[2]).write_text('survived')")
            parent = ("import subprocess,sys,time; from pathlib import Path; "
                      "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]],"
                      "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
                      "deadline=time.monotonic()+5; "
                      "exec('while not Path(sys.argv[2]).exists() and time.monotonic()<deadline:\\n time.sleep(0.05)')")
            result = process_control.run([FIXTURE_PYTHON, "-I", "-S", "-B", "-c", parent, child, str(ready), str(late)],
                                         cwd=tmp, stdin=subprocess.DEVNULL, capture_output=True,
                                         text=True, encoding="utf-8", errors="replace", timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertTrue(ready.exists(), "descendant must start before the root exits")
            time.sleep(7)
            self.assertFalse(late.exists(), "background descendant survived normal exit")

    def test_windows_evaluator_death_stops_job_members(self):
        if sys.platform != "win32":
            # Parent-death monitoring is a Windows-specific contract; POSIX uses process groups.
            return
        with tempfile.TemporaryDirectory() as tmp:
            ready, late = Path(tmp) / "ready", Path(tmp) / "late"
            child = ("import sys,time; from pathlib import Path; "
                     "Path(sys.argv[1]).write_text('started'); time.sleep(6); "
                     "Path(sys.argv[2]).write_text('survived')")
            target = ("import subprocess,sys,time; "
                      "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]]); "
                      "time.sleep(20)")
            controller = ("import subprocess,sys; sys.path.insert(0,sys.argv[1]); import process_control; "
                          "process_control.run([sys.executable,'-c',sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5]], "
                          "cwd=sys.argv[6],stdin=subprocess.DEVNULL,capture_output=True,text=True,"
                          "encoding='utf-8',errors='replace',timeout=20)")
            process = subprocess.Popen([FIXTURE_PYTHON, "-I", "-S", "-B", "-c", controller, str(Path(__file__).resolve().parent.parent / "scripts"),
                                        target, child, str(ready), str(late), tmp],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 12
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.1)
                self.assertTrue(ready.exists(), "child must start before controller termination")
                process.kill()
                process.wait(timeout=5)
                time.sleep(7)
                self.assertFalse(late.exists(), "job member survived evaluator termination")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()

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


class ProcessControl(unittest.TestCase):
    def test_windows_failed_assignment_never_releases_payload(self):
        if sys.platform != "win32":
            return
        kernel = mock.MagicMock()
        kernel.OpenProcess.return_value = 10
        kernel.WaitForSingleObject.return_value = 0x102
        kernel.CreateJobObjectW.return_value = 11
        kernel.SetInformationJobObject.return_value = True
        kernel.AssignProcessToJobObject.return_value = False
        child = mock.MagicMock()
        child._handle = 12
        child.poll.return_value = None
        with mock.patch.object(windows_job.ctypes, "WinDLL", return_value=kernel), \
             mock.patch.object(windows_job.threading, "Thread"), \
             mock.patch.object(windows_job.subprocess, "Popen", return_value=child):
            with self.assertRaises(OSError):
                windows_job.main(42, ["payload"])
        child.stdin.write.assert_not_called()
        child.kill.assert_called_once()
        child.wait.assert_called_once()

    def test_normal_output_and_return_code(self):
        result = process_control.run([sys.executable, "-c", "print('ok')"], cwd=None,
                                     stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_timeout_stops_child_and_grandchild(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready = Path(tmp) / "ready"
            late = Path(tmp) / "late"
            grandchild = ("import sys,time; from pathlib import Path; "
                          "Path(sys.argv[1]).write_text('started'); time.sleep(6); "
                          "Path(sys.argv[2]).write_text('survived')")
            child = ("import subprocess,sys,time; "
                     "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]]); "
                     "time.sleep(20)")
            parent = ("import subprocess,sys,time; "
                      "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]]); "
                      "time.sleep(20)")
            command = [sys.executable, "-c", parent, child, grandchild, str(ready), str(late)]
            with self.assertRaises(subprocess.TimeoutExpired):
                process_control.run(command, cwd=tmp, stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=4)
            self.assertTrue(ready.exists(), "grandchild must start before the timeout")
            time.sleep(3)
            self.assertFalse(late.exists(), "grandchild survived the process container")

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
            result = process_control.run([sys.executable, "-c", parent, child, str(ready), str(late)],
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
            process = subprocess.Popen([sys.executable, "-c", controller, str(Path(__file__).resolve().parent.parent / "scripts"),
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

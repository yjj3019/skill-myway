import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import reproduce_check


def completed(returncode):
    return subprocess.CompletedProcess([], returncode)


class ReproduceCheckTests(unittest.TestCase):
    def test_all_steps_pass_and_clean_tree_returns_zero(self):
        with mock.patch.object(reproduce_check.subprocess, "run", return_value=completed(0)) as run:
            self.assertEqual(reproduce_check.run("."), 0)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args_list[0].args[0][1], "scripts/validate_repo.py")
        self.assertEqual(run.call_args_list[1].args[0][1], "scripts/run_tests.py")
        self.assertEqual(run.call_args_list[2].args[0], ["git", "diff", "--exit-code"])
        for call in run.call_args_list:
            self.assertEqual(call.kwargs["cwd"], str(Path(".")))

    def test_failed_test_reports_each_step_and_returns_one(self):
        returns = [completed(0), completed(1), completed(0)]
        with mock.patch.object(reproduce_check.subprocess, "run", side_effect=returns):
            self.assertEqual(reproduce_check.run("."), 1)

    def test_tracked_changes_after_run_fail(self):
        returns = [completed(0), completed(0), completed(1)]
        with mock.patch.object(reproduce_check.subprocess, "run", side_effect=returns):
            self.assertEqual(reproduce_check.run("."), 1)

    def test_later_steps_run_even_after_failure(self):
        returns = [completed(1), completed(1), completed(1)]
        with mock.patch.object(reproduce_check.subprocess, "run", side_effect=returns) as run:
            self.assertEqual(reproduce_check.run("."), 1)
        self.assertEqual(run.call_count, 3)


if __name__ == "__main__":
    unittest.main()

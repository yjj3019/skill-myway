import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import atomic_output
import summary_io


class SummaryPublication(unittest.TestCase):
    def test_partial_write_never_becomes_final_and_same_path_can_be_retried(self):
        make_file = tempfile.NamedTemporaryFile
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "summary.json"

            def failing_file(**kwargs):
                stream = make_file(**kwargs)
                original_write = stream.write

                def broken_write(data):
                    original_write(data[:13])
                    stream.flush()
                    self.assertFalse(target.exists())
                    raise OSError("injected write failure")

                stream.write = broken_write
                return stream

            with mock.patch.object(atomic_output.tempfile, "NamedTemporaryFile", failing_file):
                with self.assertRaisesRegex(OSError, "injected write failure"):
                    summary_io.save_summary(target, {"result": "complete"})
            self.assertEqual(list(target.parent.iterdir()), [])
            sync = atomic_output.os.fsync
            attempts = []

            def interrupted_once(fd):
                attempts.append(fd)
                if len(attempts) == 1:
                    raise InterruptedError("transient flush failure")
                sync(fd)

            with mock.patch.object(atomic_output.os, "fsync", side_effect=interrupted_once):
                summary_io.save_summary(target, {"result": "complete"})
            self.assertEqual(len(attempts), 2)
            self.assertEqual(json.loads(target.read_bytes()), {"result": "complete"})

    def test_failed_flush_and_existing_summary_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "summary.json"
            with mock.patch.object(atomic_output.os, "fsync", side_effect=OSError("flush failed")):
                with self.assertRaises(OSError):
                    summary_io.save_summary(target, {"new": 1})
            self.assertEqual(list(target.parent.iterdir()), [])
            target.write_bytes(b"original")
            with self.assertRaises(FileExistsError):
                summary_io.save_summary(target, {"new": 2})
            self.assertEqual(target.read_bytes(), b"original")
            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_two_publishers_produce_one_whole_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "summary.json"
            barrier = threading.Barrier(2)
            def publish(value):
                barrier.wait(timeout=10)
                try:
                    summary_io.save_summary(target, {"writer": value})
                except FileExistsError:
                    return None
                return value

            with ThreadPoolExecutor(max_workers=2) as pool:
                winners = [n for n in pool.map(publish, (1, 2)) if n is not None]
            self.assertEqual(winners, [json.loads(target.read_bytes())["writer"]])
            self.assertEqual(list(target.parent.iterdir()), [target])

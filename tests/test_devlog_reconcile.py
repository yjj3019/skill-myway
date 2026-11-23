"""Exercise the packaged recovery decision against a simulated history section."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/myway/skills/devlog/scripts/reconcile.py"


def decision(state, entries, complete=True):
    snapshot = {"entry_id": "trial-a", "body": "가상 이력", "state": state, "complete": complete, "entries": entries}
    result = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT)], input=json.dumps(snapshot),
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


class Recovery(unittest.TestCase):
    def test_write_succeeded_but_reply_was_lost(self):
        stored = []
        state = "ready"
        self.assertEqual(decision(state, stored), "append")
        state = "pending"

        def append_and_lose_reply():
            stored.append({"entry_id": "trial-a", "body": "가상 이력"})
            raise TimeoutError("reply lost")

        with self.assertRaises(TimeoutError):
            append_and_lose_reply()
        self.assertEqual(decision(state, []), "hold")  # successful write not visible yet
        self.assertEqual(decision(state, stored, complete=False), "hold")
        self.assertEqual(decision(state, stored), "synced")
        self.assertEqual(len(stored), 1)

    def test_ambiguous_state_cannot_request_an_append(self):
        raw = '{"entry_id":"test","body":"sample","state":"pending","state":"ready","complete":true,"entries":[]}'
        result = subprocess.run([sys.executable, str(SCRIPT)], input=raw, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_conflicts_and_unrelated_records(self):
        entry = {"entry_id": "trial-a", "body": "가상 이력"}
        self.assertEqual(decision("ready", [entry, entry]), "conflict")
        self.assertEqual(decision("pending", [entry | {"body": "other"}]), "conflict")
        self.assertEqual(decision("ready", [entry | {"entry_id": "other"}]), "append")
        self.assertEqual(decision("ready", [], complete=False), "hold")

"""Public developmental checks for the synthetic Ledger task, not a sandbox."""
import concurrent.futures
import unittest

from baseline import Ledger


class LedgerOracle(unittest.TestCase):
    def test_idempotent_retry(self):
        ledger = Ledger({"a": 10, "b": 0})
        self.assertEqual(ledger.transfer("r1", "a", "b", 4), "applied")
        self.assertEqual(ledger.transfer("r1", "a", "b", 4), "applied")
        self.assertEqual(ledger.snapshot(), {"a": 6, "b": 4})

    def test_request_conflict_is_atomic(self):
        ledger = Ledger({"a": 10, "b": 0})
        ledger.transfer("r1", "a", "b", 2)
        before = ledger.snapshot()
        with self.assertRaises(ValueError):
            ledger.transfer("r1", "a", "b", 3)
        self.assertEqual(ledger.snapshot(), before)

    def test_invalid_inputs_leave_state_unchanged(self):
        for source, target, amount in [("a", "b", True), ("a", "b", 0), ("a", "b", -1),
                                        ("a", "missing", 1), ("a", "a", 1), ("a", "b", 11)]:
            ledger = Ledger({"a": 10, "b": 0})
            with self.subTest(source=source, target=target, amount=amount):
                with self.assertRaises(ValueError):
                    ledger.transfer("r1", source, target, amount)
                self.assertEqual(ledger.snapshot(), {"a": 10, "b": 0})

    def test_failed_id_can_be_retried(self):
        ledger = Ledger({"a": 10, "b": 0})
        with self.assertRaises(ValueError):
            ledger.transfer("r1", "a", "b", 11)
        self.assertEqual(ledger.transfer("r1", "a", "b", 4), "applied")
        self.assertEqual(ledger.snapshot(), {"a": 6, "b": 4})

    def test_concurrent_cannot_overspend(self):
        ledger = Ledger({"a": 10, "b": 0})
        def transfer(request_id):
            try:
                return ledger.transfer(request_id, "a", "b", 7)
            except ValueError:
                return "rejected"
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(transfer, ("r1", "r2")))
        self.assertCountEqual(results, ["applied", "rejected"])
        self.assertEqual(ledger.snapshot(), {"a": 3, "b": 7})

    def test_snapshot_cannot_modify_ledger(self):
        ledger = Ledger({"a": 10, "b": 0})
        copy = ledger.snapshot()
        copy["a"] = 0
        self.assertEqual(ledger.snapshot(), {"a": 10, "b": 0})


if __name__ == "__main__":
    unittest.main(verbosity=2)

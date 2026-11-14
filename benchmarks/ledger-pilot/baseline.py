"""Intentionally deficient synthetic benchmark fixture, never production code."""
import time


class Ledger:
    def __init__(self, balances):
        self.balances = dict(balances)

    def snapshot(self):
        return self.balances.copy()

    def transfer(self, request_id, source, target, amount):
        if source not in self.balances or target not in self.balances or amount > self.balances[source]:
            raise ValueError("invalid transfer")
        time.sleep(0.01)
        self.balances[source] -= amount
        self.balances[target] += amount
        return "applied"

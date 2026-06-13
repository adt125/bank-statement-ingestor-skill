"""
4_deduplicator.py — Transaction Deduplication
Hash-based dedup against both the incoming batch and your existing DB.
"""

import hashlib
import json
from datetime import datetime, timedelta
from scripts.normalizer import NormalizedTransaction   # adjust import path


# ─── Hash function ────────────────────────────────────────────────────────────

def make_hash(txn: NormalizedTransaction) -> str:
    """
    Deterministic fingerprint for a transaction.
    Uses date + amount + first 40 chars of description to handle
    slight description variations across statement exports.
    """
    key = f"{txn.date}|{txn.amount:.2f}|{txn.description[:40].lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()


# ─── Fuzzy duplicate check ────────────────────────────────────────────────────

def is_fuzzy_duplicate(
    txn: NormalizedTransaction,
    existing: list[NormalizedTransaction],
    date_tolerance_days: int = 1,
    amount_tolerance: float = 0.01,
) -> bool:
    """
    Catches edge cases where bank exports the same transaction with a
    slightly different value date (off by 1 day).
    """
    txn_date = datetime.strptime(txn.date, "%Y-%m-%d")

    for ex in existing:
        ex_date = datetime.strptime(ex.date, "%Y-%m-%d")
        date_diff   = abs((txn_date - ex_date).days)
        amount_diff = abs(txn.amount - ex.amount)

        if (
            date_diff <= date_tolerance_days
            and amount_diff <= amount_tolerance
            and txn.description[:30].lower() == ex.description[:30].lower()
        ):
            return True
    return False


# ─── SQLite-backed dedup store ────────────────────────────────────────────────

# The SQLite-backed DeduplicationStore was removed to eliminate a hard
# dependency on sqlite. The project now uses an in-memory store only.
# If persistent storage is needed in the future, reintroduce a DB-backed
# store in a separate module.

# (No persistent store in this file.)


class InMemoryDeduplicationStore:
    """Simple in-memory dedup store that tracks hashes for the current run.

    This avoids any dependency on SQLite or external DBs. It's ephemeral and
    does not persist between runs.
    """

    def __init__(self):
        self.hashes = set()

    def exists(self, txn_hash: str) -> bool:
        return txn_hash in self.hashes

    def insert(self, txn: NormalizedTransaction, txn_hash: str):
        self.hashes.add(txn_hash)

    def get_recent(self, days: int = 7) -> list[dict]:
        # Not supported for in-memory store
        return []

    def close(self):
        self.hashes.clear()


# ─── Main dedup function ──────────────────────────────────────────────────────

def deduplicate_and_insert(
    transactions: list[NormalizedTransaction],
    store,
) -> tuple[list[NormalizedTransaction], list[NormalizedTransaction]]:
    """
    Returns (new_transactions, duplicate_transactions).
    Inserts new ones into the store.
    """
    new_txns  = []
    dupe_txns = []

    # Within-batch dedup first (same file uploaded twice)
    seen_hashes = set()

    for txn in transactions:
        h = make_hash(txn)

        if h in seen_hashes:
            dupe_txns.append(txn)
            continue

        if store.exists(h):
            dupe_txns.append(txn)
            continue

        seen_hashes.add(h)
        store.insert(txn, h)
        new_txns.append(txn)

    print(f"[DEDUP] New: {len(new_txns)}, Duplicates skipped: {len(dupe_txns)}")
    return new_txns, dupe_txns


# ─── Demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from scripts.normalizer import NormalizedTransaction

    store = InMemoryDeduplicationStore()

    batch1 = [
        NormalizedTransaction("2024-03-15", "SWIGGY ORDER", "Swiggy", "Food & Dining", "Food Delivery", 320.0, "debit", "hdfc", ["food"], 0.99),
        NormalizedTransaction("2024-03-16", "UBER TRIP",    "Uber",   "Transport",     "Cab",           234.0, "debit", "hdfc", ["cab"],  0.99),
    ]

    # First insert
    new, dupes = deduplicate_and_insert(batch1, store)
    print(f"Round 1 → new={len(new)}, dupes={len(dupes)}")

    # Same batch again (simulating re-upload)
    new, dupes = deduplicate_and_insert(batch1, store)
    print(f"Round 2 → new={len(new)}, dupes={len(dupes)}")

    store.close()

"""
4_deduplicator.py — Transaction Deduplication
Hash-based dedup against both the incoming batch and your existing DB.
"""

import hashlib
import sqlite3
import json
from datetime import datetime, timedelta
from dataclasses import asdict
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

class DeduplicationStore:
    """
    Lightweight SQLite store that tracks which transaction hashes
    have already been added. Swap this out for your actual DB.
    """

    def __init__(self, db_path: str = "expenses.db"):
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                hash        TEXT UNIQUE NOT NULL,
                date        TEXT,
                merchant    TEXT,
                category    TEXT,
                subcategory TEXT,
                amount      REAL,
                txn_type    TEXT,
                bank        TEXT,
                description TEXT,
                tags        TEXT,
                confidence  REAL,
                balance     REAL,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hash ON transactions(hash);
        """)
        self.conn.commit()

    def exists(self, txn_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM transactions WHERE hash = ?", (txn_hash,)
        ).fetchone()
        return row is not None

    def insert(self, txn: NormalizedTransaction, txn_hash: str):
        self.conn.execute("""
            INSERT OR IGNORE INTO transactions
            (hash, date, merchant, category, subcategory, amount, txn_type, bank, description, tags, confidence, balance)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            txn_hash, txn.date, txn.merchant, txn.category,
            txn.subcategory, txn.amount, txn.txn_type, txn.bank,
            txn.description, json.dumps(txn.tags), txn.confidence, txn.balance,
        ))
        self.conn.commit()

    def get_recent(self, days: int = 7) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = self.conn.execute(
            "SELECT * FROM transactions WHERE date >= ?", (cutoff,)
        ).fetchall()
        cols = [d[0] for d in self.conn.execute("PRAGMA table_info(transactions)").fetchall()]
        return [dict(zip(cols, row)) for row in rows]

    def close(self):
        self.conn.close()


# ─── Main dedup function ──────────────────────────────────────────────────────

def deduplicate_and_insert(
    transactions: list[NormalizedTransaction],
    store: DeduplicationStore,
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

    store = DeduplicationStore("demo_expenses.db")

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

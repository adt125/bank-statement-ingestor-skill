"""
2_pii_filter.py — PII Scrubber
Strips / masks sensitive fields before data touches your expense DB.
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from scripts.parser import RawTransaction   # adjust import path as needed


# ─── PII Patterns ─────────────────────────────────────────────────────────────

PII_PATTERNS = [
    # Account / card numbers
    (r"\b\d{9,18}\b",                          "[ACCT_MASKED]"),
    (r"\b(?:\d[ -]?){15,16}\b",               "[CARD_MASKED]"),

    # IFSC codes  (e.g. HDFC0001234)
    (r"\b[A-Z]{4}0[A-Z0-9]{6}\b",             "[IFSC_MASKED]"),

    # UPI IDs  (e.g. user@oksbi)
    (r"\b[\w.+-]+@[a-z]+\b",                  "[UPI_MASKED]"),

    # Phone numbers
    (r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b",       "[PHONE_MASKED]"),

    # Email addresses
    (r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b",    "[EMAIL_MASKED]"),

    # PAN  (e.g. ABCDE1234F)
    (r"\b[A-Z]{5}\d{4}[A-Z]\b",               "[PAN_MASKED]"),

    # Aadhaar  (12 digits, sometimes spaced 4-4-4)
    (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",      "[AADHAAR_MASKED]"),

    # Full names via salutation
    (r"\b(Mr|Mrs|Ms|Dr|Shri|Smt)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+",
                                               "[NAME_MASKED]"),
]

# Fields to drop entirely from the raw transaction before storage
DROP_FIELDS = {"source_file"}  # you can expand this


@dataclass
class CleanTransaction:
    date:        str
    description: str
    debit:       Optional[float]
    credit:      Optional[float]
    balance:     Optional[float]
    bank:        str
    # Derived later:
    amount:      float            = 0.0
    txn_type:    str              = ""   # "debit" | "credit"
    pii_hits:    list[str]        = field(default_factory=list)


# ─── Core scrubber ────────────────────────────────────────────────────────────

def scrub_text(text: str) -> tuple[str, list[str]]:
    """
    Apply all PII patterns to `text`.
    Returns (cleaned_text, list_of_matched_patterns).
    """
    hits = []
    for pattern, replacement in PII_PATTERNS:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            hits.append(f"{replacement}: {matches}")
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text.strip(), hits


def clean_transaction(raw: RawTransaction) -> CleanTransaction:
    clean_desc, hits = scrub_text(raw.description)

    # Determine amount + direction
    if raw.debit and raw.debit > 0:
        amount   = raw.debit
        txn_type = "debit"
    elif raw.credit and raw.credit > 0:
        amount   = raw.credit
        txn_type = "credit"
    else:
        amount   = 0.0
        txn_type = "unknown"

    return CleanTransaction(
        date        = raw.date,
        description = clean_desc,
        debit       = raw.debit,
        credit      = raw.credit,
        balance     = raw.balance,
        bank        = raw.bank,
        amount      = amount,
        txn_type    = txn_type,
        pii_hits    = hits,
    )


def filter_batch(transactions: list[RawTransaction]) -> list[CleanTransaction]:
    cleaned = [clean_transaction(t) for t in transactions]

    pii_flagged = [c for c in cleaned if c.pii_hits]
    if pii_flagged:
        print(f"[PII] Masked PII in {len(pii_flagged)} transactions")
        for c in pii_flagged[:3]:   # show a sample
            print(f"  → {c.pii_hits}")

    return cleaned


# ─── Demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    samples = [
        RawTransaction("2024-03-15", "UPI-9876543210-user@oksbi-HDFC0001234", 500.0, None, 12000.0, "hdfc", "stmt.pdf"),
        RawTransaction("2024-03-16", "NEFT-Mr. Ramesh Kumar-SBIN0005678-98761234567890", None, 5000.0, 17000.0, "sbi", "stmt.pdf"),
        RawTransaction("2024-03-17", "SWIGGY ORDER #984321 BANGALORE", 320.0, None, 16680.0, "hdfc", "stmt.pdf"),
    ]

    cleaned = filter_batch(samples)
    for c in cleaned:
        print(f"{c.date} | {c.description} | {c.txn_type} ₹{c.amount}")
        if c.pii_hits:
            print(f"  PII removed: {c.pii_hits}")

"""
1_parser.py — Bank Statement Parser
Supports: HDFC, ICICI, SBI, Axis (PDF + CSV)
"""

import re
import pandas as pd
import pdfplumber
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class RawTransaction:
    date: str
    description: str
    debit: Optional[float]
    credit: Optional[float]
    balance: Optional[float]
    bank: str
    source_file: str


# ─── Bank-specific PDF configs ────────────────────────────────────────────────

BANK_CONFIGS = {
    "hdfc": {
        "date_col":    ["Date", "Txn Date", "Value Date"],
        "desc_col":    ["Narration", "Description", "Particulars"],
        "debit_col":   ["Debit Amount", "Withdrawal Amt.", "Debit"],
        "credit_col":  ["Credit Amount", "Deposit Amt.", "Credit"],
        "balance_col": ["Closing Balance", "Balance"],
        "date_fmt":    ["%d/%m/%y", "%d/%m/%Y", "%d-%m-%Y"],
    },
    "icici": {
        "date_col":    ["Transaction Date", "Value Date"],
        "desc_col":    ["Transaction Remarks", "Particulars"],
        "debit_col":   ["Withdrawal Amount (INR )", "Debit"],
        "credit_col":  ["Deposit Amount (INR )", "Credit"],
        "balance_col": ["Balance (INR )", "Balance"],
        "date_fmt":    ["%d-%m-%Y", "%d/%m/%Y"],
    },
    "sbi": {
        "date_col":    ["Txn Date", "Value Date"],
        "desc_col":    ["Description", "Particulars"],
        "debit_col":   ["Debit", "Withdrawal"],
        "credit_col":  ["Credit", "Deposit"],
        "balance_col": ["Balance"],
        "date_fmt":    ["%d %b %Y", "%d/%m/%Y"],
    },
    "axis": {
        "date_col":    ["Tran Date", "Transaction Date"],
        "desc_col":    ["PARTICULARS", "Narration"],
        "debit_col":   ["DR", "Debit"],
        "credit_col":  ["CR", "Credit"],
        "balance_col": ["BAL", "Balance"],
        "date_fmt":    ["%d-%m-%Y", "%d/%m/%Y"],
    },
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def detect_bank(text: str) -> str:
    text = text.lower()
    if "hdfc" in text:      return "hdfc"
    if "icici" in text:     return "icici"
    if "state bank" in text or "sbi" in text: return "sbi"
    if "axis" in text:      return "axis"
    return "unknown"


def find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Return the first matching column name from a list of candidates."""
    for name in candidates:
        for col in df.columns:
            if name.lower() in col.lower():
                return col
    return None


def parse_amount(val) -> Optional[float]:
    if pd.isna(val) or val == "" or val is None:
        return None
    cleaned = re.sub(r"[₹,\s]", "", str(val))
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(val: str, formats: list[str]) -> str:
    for fmt in formats:
        try:
            return datetime.strptime(val.strip(), fmt).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            continue
    return val  # return raw if nothing matches


# ─── PDF Parser ───────────────────────────────────────────────────────────────

def parse_pdf(filepath: str) -> list[RawTransaction]:
    transactions = []
    path = Path(filepath)

    with pdfplumber.open(filepath) as pdf:
        full_text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        bank = detect_bank(full_text)
        cfg  = BANK_CONFIGS.get(bank, BANK_CONFIGS["hdfc"])

        all_tables = []
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if table and len(table) > 1:
                    all_tables.extend(table)

    if not all_tables:
        print(f"[WARN] No tables found in {filepath}")
        return []

    # Build DataFrame — first row as header
    df = pd.DataFrame(all_tables[1:], columns=all_tables[0])
    df.columns = [str(c).strip() if c else f"col_{i}" for i, c in enumerate(df.columns)]

    date_col    = find_col(df, cfg["date_col"])
    desc_col    = find_col(df, cfg["desc_col"])
    debit_col   = find_col(df, cfg["debit_col"])
    credit_col  = find_col(df, cfg["credit_col"])
    balance_col = find_col(df, cfg["balance_col"])

    for _, row in df.iterrows():
        date_raw = str(row.get(date_col, "")).strip() if date_col else ""
        if not date_raw or date_raw.lower() in ("date", "nan", ""):
            continue

        transactions.append(RawTransaction(
            date        = parse_date(date_raw, cfg["date_fmt"]),
            description = str(row.get(desc_col, "")).strip() if desc_col else "",
            debit       = parse_amount(row.get(debit_col))   if debit_col   else None,
            credit      = parse_amount(row.get(credit_col))  if credit_col  else None,
            balance     = parse_amount(row.get(balance_col)) if balance_col else None,
            bank        = bank,
            source_file = path.name,
        ))

    print(f"[PDF] {path.name} → {len(transactions)} transactions ({bank})")
    return transactions


# ─── CSV Parser ───────────────────────────────────────────────────────────────

def parse_csv(filepath: str) -> list[RawTransaction]:
    path = Path(filepath)
    transactions = []

    # Try to auto-detect encoding + skip junk header rows
    df = None
    for enc in ["utf-8", "latin-1", "cp1252"]:
        try:
            raw = pd.read_csv(filepath, encoding=enc, header=None, dtype=str)
            # Find the actual header row (contains "date" or "narration")
            header_idx = 0
            for i, row in raw.iterrows():
                row_str = " ".join(str(v).lower() for v in row.values)
                if any(k in row_str for k in ["date", "narration", "description", "particulars"]):
                    header_idx = i
                    break
            df = pd.read_csv(filepath, encoding=enc, skiprows=header_idx, dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
            break
        except Exception:
            continue

    if df is None:
        print(f"[ERROR] Could not parse CSV: {filepath}")
        return []

    full_text = " ".join(df.columns.tolist())
    bank = detect_bank(full_text)
    cfg  = BANK_CONFIGS.get(bank, BANK_CONFIGS["hdfc"])

    date_col    = find_col(df, cfg["date_col"])
    desc_col    = find_col(df, cfg["desc_col"])
    debit_col   = find_col(df, cfg["debit_col"])
    credit_col  = find_col(df, cfg["credit_col"])
    balance_col = find_col(df, cfg["balance_col"])

    for _, row in df.iterrows():
        date_raw = str(row.get(date_col, "")).strip() if date_col else ""
        if not date_raw or date_raw.lower() in ("nan", ""):
            continue

        transactions.append(RawTransaction(
            date        = parse_date(date_raw, cfg["date_fmt"]),
            description = str(row.get(desc_col, "")).strip() if desc_col else "",
            debit       = parse_amount(row.get(debit_col))   if debit_col   else None,
            credit      = parse_amount(row.get(credit_col))  if credit_col  else None,
            balance     = parse_amount(row.get(balance_col)) if balance_col else None,
            bank        = bank,
            source_file = path.name,
        ))

    print(f"[CSV] {path.name} → {len(transactions)} transactions ({bank})")
    return transactions


# ─── Unified entrypoint ───────────────────────────────────────────────────────

def parse_statement(filepath: str) -> list[RawTransaction]:
    ext = Path(filepath).suffix.lower()
    if ext == ".pdf":
        return parse_pdf(filepath)
    elif ext in (".csv", ".xlsx", ".xls"):
        if ext != ".csv":
            # Convert xlsx to CSV first
            df = pd.read_excel(filepath, dtype=str)
            tmp = filepath.replace(ext, ".csv")
            df.to_csv(tmp, index=False)
            return parse_csv(tmp)
        return parse_csv(filepath)
    else:
        print(f"[WARN] Unsupported file type: {ext}")
        return []


# ─── Demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    files = sys.argv[1:] or ["sample_hdfc.pdf", "sample_icici.csv"]
    for f in files:
        txns = parse_statement(f)
        for t in txns[:3]:
            print(vars(t))

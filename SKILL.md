---
name: bank-statement-ingestor
description: Use this skill whenever a user wants to ingest, parse, or import bank statements into an expense tracker or financial app. Triggers include: uploading PDFs or CSVs from banks (HDFC, ICICI, SBI, Axis, or any Indian bank), automating expense entry from statements, extracting transactions from bank files, categorizing bank transactions, deduplicating expenses, or building a statement-to-expense pipeline. Also triggers when the user mentions "bank statement", "auto-import expenses", "parse transactions", "statement upload", or any variation of wanting to avoid manually adding expenses. Use this skill even if the user only mentions one part of the pipeline (e.g. "just parse the PDF") — the full pipeline is usually what they need.
---

# Bank Statement Ingestor Skill

Parses Indian bank statements (PDF/CSV) → strips PII → normalizes via LLM → deduplicates → inserts into any expense DB.

## Pipeline Overview

```
[ PDF / CSV / XLSX ]
       │
       ▼
  1. parse        — extract raw rows per bank format
       │
       ▼
  2. pii_filter   — mask account nos, UPI IDs, PAN, Aadhaar, phone, names
       │
       ▼
  3. normalize    — LLM → merchant name, category, tags, confidence
       │
       ▼
  4. deduplicate  — SHA256 hash check against existing DB
       │
       ▼
  [ Expense DB ]
```

## Supported Banks
HDFC, ICICI, SBI, Axis — auto-detected from document content. Adding a new bank takes ~10 lines (see `references/adding-banks.md`).

## Quick Start

### Install dependencies
```bash
pip install pdfplumber pandas openpyxl anthropic python-dotenv
```

### Run the full pipeline (CLI)
```bash
# Dry run — parse only, no DB insert
python scripts/pipeline.py statement.pdf --dry-run

# Full run against SQLite
python scripts/pipeline.py hdfc_march.pdf icici_march.csv --db expenses.db


# CLI wrapper (keeps a convenient entrypoint but does NOT run a web server)
python scripts/api.py hdfc_march.pdf
```

### Run as a Python module
```python
from scripts.pipeline import run_pipeline

result = run_pipeline(["hdfc_march.pdf"], db_path="expenses.db")
print(f"Added {result.new_inserted} expenses, skipped {result.duplicates_skipped} dupes")
```

---

## Script Reference

All scripts live in `scripts/`. Run them directly or import as modules.

| Script | Purpose | Key function |
|---|---|---|
| `parser.py` | PDF + CSV → RawTransaction | `parse_statement(filepath)` |
| `pii_filter.py` | Mask PII in descriptions | `filter_batch(transactions)` |
| `normalizer.py` | LLM → merchant/category/tags | `normalize_batch(transactions)` |
| `deduplicator.py` | Hash-based dedup + SQLite | `deduplicate_and_insert(txns, store)` |
| `pipeline.py` | Orchestrates all 4 steps | `run_pipeline(files, db_path)` |
| `api.py` | FastAPI upload endpoint | `POST /api/statements/upload` |

---

## LLM Configuration

The normalizer supports multiple LLM backends. Set via env var `LLM_BACKEND`:

```bash
export LLM_BACKEND=ollama     # local, free (default)
export LLM_BACKEND=gemini     # Google free tier
export LLM_BACKEND=groq       # fast + free tier
export LLM_BACKEND=anthropic  # Claude (most accurate)
```

See `references/llm-backends.md` for setup instructions and drop-in code for each.

---

## Integrating into an Existing Project

### Step 1 — Adapt the data model
The pipeline uses `RawTransaction`, `CleanTransaction`, and `NormalizedTransaction` dataclasses. Replace these with your ORM models by editing the return types in `parser.py` and `pii_filter.py`.

### Step 2 — Swap the DB layer
`deduplicator.py` uses SQLite via `DeduplicationStore`. Replace `exists()` and `insert()` with calls to your ORM. Keep `make_hash()` and `is_fuzzy_duplicate()` unchanged.

### Step 3 — Match your categories
Edit the `CATEGORIES` string in `normalizer.py` to match your app's taxonomy exactly. The LLM will map to these labels.

### Step 4 — Wire the API
`api.py` is a standalone FastAPI app. Extract the upload handler and add it as a route in your existing backend. The handler returns `IngestionResponse` — adapt to your API's response format.

For detailed instructions per framework (Django, Express, Next.js), see `references/integration-guide.md`.

---

## Customization Points

| What to change | Where |
|---|---|
| Add a new bank | `parser.py` → `BANK_CONFIGS` dict |
| Add/edit PII patterns | `pii_filter.py` → `PII_PATTERNS` list |
| Change categories | `normalizer.py` → `CATEGORIES` string |
| Swap LLM | `normalizer.py` → `call_llm()` function |
| Swap DB | `deduplicator.py` → `DeduplicationStore` class |
| Change hash key | `deduplicator.py` → `make_hash()` function |

---

## Reference Files

- `references/llm-backends.md` — Drop-in code for Ollama, Gemini, Groq, OpenAI
- `references/adding-banks.md` — How to add a new Indian bank config
- `references/integration-guide.md` — Framework-specific wiring (Django, FastAPI, Express, Next.js)

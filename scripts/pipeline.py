"""
pipeline.py — Master Orchestrator
Usage:
  python scripts/pipeline.py file1.pdf file2.csv --db expenses.db
  python scripts/pipeline.py file.pdf --dry-run
"""

import time
import argparse
from dataclasses import dataclass, field
from pathlib import Path

from scripts.parser       import parse_statement
from scripts.pii_filter   import filter_batch
from scripts.normalizer   import normalize_batch
from scripts.deduplicator import DeduplicationStore, InMemoryDeduplicationStore, deduplicate_and_insert


@dataclass
class PipelineResult:
    total_parsed:       int = 0
    after_pii_filter:   int = 0
    after_normalize:    int = 0
    new_inserted:       int = 0
    duplicates_skipped: int = 0
    errors:             list[str] = field(default_factory=list)
    elapsed_seconds:    float = 0.0
    # Path to the validation CSV produced after PII filtering (if any)
    validation_csv:     str | None = None
    # True if the pipeline paused awaiting user/agent validation before categorization
    awaiting_validation: bool = False


def run_pipeline(
    file_paths: list[str],
    db_path:    str  = "expenses.db",
    dry_run:    bool = False,
) -> PipelineResult:
    result = PipelineResult()
    t0     = time.time()
    # Use in-memory dedup store by default unless USE_DB=true is set.
    use_db = os.getenv("USE_DB", "false").lower() == "true"
    if not dry_run and use_db:
        store = DeduplicationStore(db_path)
    else:
        store = InMemoryDeduplicationStore()

    # Step 1: Parse
    print("\n── 1/4 Parsing ──")
    all_raw = []
    for fp in file_paths:
        if not Path(fp).exists():
            result.errors.append(f"Not found: {fp}")
            continue
        try:
            all_raw.extend(parse_statement(fp))
        except Exception as e:
            result.errors.append(f"Parse error [{fp}]: {e}")

    result.total_parsed = len(all_raw)
    print(f"  {result.total_parsed} raw transactions from {len(file_paths)} file(s)")
    if not all_raw:
        return result

    # Step 2: PII filter
    print("\n── 2/4 PII Filter ──")
    clean = [c for c in filter_batch(all_raw) if c.amount > 0]
    result.after_pii_filter = len(clean)
    print(f"  {result.after_pii_filter} transactions after filter")

    # Produce a CSV for user validation (user inspects/edits categories before
    # the agent proceeds with categorization). The CSV contains the cleaned
    # transactions (no PII) for review.
    import csv, datetime, os
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = os.getenv("VALIDATION_DIR", "./outputs")
    os.makedirs(out_dir, exist_ok=True)
    validation_path = os.path.join(out_dir, f"validation_{ts}.csv")
    with open(validation_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["date", "description", "amount", "txn_type", "bank", "balance"])
        writer.writeheader()
        for t in clean:
            writer.writerow({
                "date": t.date,
                "description": t.description,
                "amount": t.amount,
                "txn_type": t.txn_type,
                "bank": t.bank,
                "balance": getattr(t, "balance", ""),
            })

    result.validation_csv = validation_path
    print(f"\n[PIPELINE] Validation CSV written to: {validation_path}")

    # If AGENT_NORMALIZATION is true, pause here and let the agent/human
    # validate the CSV and then call the normalizer via the agent.
    agent_mode = os.getenv("AGENT_NORMALIZATION", "false").lower() == "true"
    if agent_mode:
        result.awaiting_validation = True
        print("[PIPELINE] AGENT_NORMALIZATION enabled — pausing after PII filter.\n"\
              "Please validate the CSV and then run the agent to apply categories.")
        result.elapsed_seconds = round(time.time() - t0, 2)
        return result

    # Step 3: Normalize
    print("\n── 3/4 Normalizing ──")
    normalized = normalize_batch(clean)
    result.after_normalize = len(normalized)

    # Step 4: Dedup + insert
    print("\n── 4/4 Deduplication ──")
    if dry_run:
        result.new_inserted = len(normalized)
        print("  [DRY RUN] skipping DB insert")
    else:
        new, dupes = deduplicate_and_insert(normalized, store)
        result.new_inserted       = len(new)
        result.duplicates_skipped = len(dupes)
        store.close()

    result.elapsed_seconds = round(time.time() - t0, 2)

    print(f"""
╔═══════════════════════════════════════╗
║  Pipeline Complete                    ║
╠═══════════════════════════════════════╣
║  Raw transactions  : {result.total_parsed:<17}║
║  After PII filter  : {result.after_pii_filter:<17}║
║  New inserted      : {result.new_inserted:<17}║
║  Duplicates skipped: {result.duplicates_skipped:<17}║
║  Time              : {result.elapsed_seconds}s{'':<14}║
╚═══════════════════════════════════════╝""")

    for e in result.errors:
        print(f"  ⚠ {e}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bank Statement Expense Pipeline")
    parser.add_argument("files",     nargs="+")
    parser.add_argument("--db",      default="expenses.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_pipeline(args.files, db_path=args.db, dry_run=args.dry_run)

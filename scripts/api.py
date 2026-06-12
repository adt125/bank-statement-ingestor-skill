"""
api.py — CLI compatibility wrapper for pipeline (no FastAPI dependency)
Usage: python scripts/api.py file1 [file2 ...] [--db expenses.db] [--dry-run]
This script intentionally avoids running a web server; it calls the pipeline directly.
"""

import os
import argparse
from scripts.pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for Bank Statement Pipeline (compat)")
    parser.add_argument("files", nargs="+", help="One or more statement file paths")
    parser.add_argument("--db", default=os.getenv("EXPENSES_DB", "expenses.db"), help="Path to SQLite DB")
    parser.add_argument("--dry-run", action="store_true", help="Parse and normalize without inserting into DB")
    args = parser.parse_args()

    result = run_pipeline(args.files, db_path=args.db, dry_run=args.dry_run)

    print(f"Success: {not bool(result.errors)}")
    print(f"Added {result.new_inserted}, skipped {result.duplicates_skipped} dupes")
    if result.errors:
        print("Errors:")
        for e in result.errors:
            print(" -", e)


if __name__ == "__main__":
    main()

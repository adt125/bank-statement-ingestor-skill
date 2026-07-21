#!/usr/bin/env python3
"""
One-command bank statement ingestion.

Reads statements from hdfc/, sbi/, and cc/, writes the consolidated CSV, and
pushes the result to Google Sheets.
"""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from consolidator import StatementConsolidator  # noqa: E402
from google_sheets import push_dataframe_to_sheets  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(
        description="Consolidate bank statements and push them to Google Sheets"
    )
    parser.add_argument(
        "-i",
        "--input",
        default=str(ROOT),
        help="Project/input directory containing hdfc/, sbi/, and cc/ folders",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(ROOT / "consolidated_statements.csv"),
        help="Output CSV path",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to Google Sheets instead of replacing each monthly tab range",
    )
    parser.add_argument(
        "--no-sheets",
        action="store_true",
        help="Only create the consolidated CSV; do not push to Google Sheets",
    )
    parser.add_argument(
        "--sheet-id",
        help="Google Sheet ID. Defaults to GOOGLE_SHEET_ID from .env",
    )
    parser.add_argument(
        "--service-account-file",
        help="Google service account JSON. Defaults to GOOGLE_SERVICE_ACCOUNT_FILE",
    )
    parser.add_argument(
        "--sheets-range",
        help="Column-only Google Sheets range. Defaults to GOOGLE_SHEET_RANGE or A:F",
    )
    return parser.parse_args()


def print_summary(consolidator: StatementConsolidator) -> None:
    summary = consolidator.get_summary()
    print("\n" + "=" * 50)
    print("CONSOLIDATION SUMMARY")
    print("=" * 50)
    print(f"Total Transactions: {summary['total_transactions']}")
    print(f"Total Debits: Rs {summary['total_debits']:,.2f}")
    print(f"Total Credits: Rs {summary['total_credits']:,.2f}")
    print(f"Net: Rs {summary['total_credits'] - summary['total_debits']:,.2f}")

    if summary["by_tag"]:
        print("\nBy Bank/Source:")
        for tag, count in summary["by_tag"].items():
            print(f"  {tag.upper()}: {count} transactions")

    print(f"\nDate Range: {summary['date_range'][0]} to {summary['date_range'][1]}")
    print("=" * 50)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser()

    if not input_path.exists():
        print(f"Error: input directory not found: {input_path}")
        return 1

    consolidator = StatementConsolidator()
    print(f"Reading statements from: {input_path}")
    consolidator.add_statements_from_directory(str(input_path))

    if not consolidator.transactions:
        print("No transactions found to consolidate")
        return 1

    df = consolidator.consolidate(args.output)

    if not args.no_sheets:
        try:
            result = push_dataframe_to_sheets(
                df,
                service_account_file=args.service_account_file,
                sheet_id=args.sheet_id,
                range_columns=args.sheets_range,
                replace=not args.append,
            )
            mode = "appended" if args.append else "replaced"
            print(
                f"Google Sheets push complete: {mode} {result.rows_updated} "
                f"rows across {len(result.sheets_modified)} monthly tabs"
            )
        except Exception as e:
            print(f"Error pushing to Google Sheets: {e}")
            print("Check .env and make sure the Sheet is shared with the service account.")
            return 1

    print_summary(consolidator)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

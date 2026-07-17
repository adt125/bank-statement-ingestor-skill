#!/usr/bin/env python3
"""
Bank Statement Ingester - Main Entry Point

Consolidate bank statements from multiple accounts into a single CSV file.
"""

import argparse
import sys
from pathlib import Path

from consolidator import StatementConsolidator


def main():
    parser = argparse.ArgumentParser(
        description="Consolidate bank statements from multiple accounts"
    )

    parser.add_argument(
        "-i", "--input", help="Input directory containing statement files", type=str
    )

    parser.add_argument(
        "-f", "--file", help="Single statement file to process", type=str
    )

    parser.add_argument(
        "-t",
        "--tag",
        help="Bank tag for single file (sbi, hdfc, cc)",
        type=str,
        choices=["sbi", "hdfc", "cc"],
    )

    parser.add_argument(
        "-s", "--source", help="Account name/number for single file", type=str
    )

    parser.add_argument(
        "-o",
        "--output",
        help="Output CSV file path",
        default="consolidated_statements.csv",
        type=str,
    )

    parser.add_argument(
        "--push-to-sheets",
        help="Push consolidated transactions to Google Sheets after extraction",
        action="store_true",
    )

    parser.add_argument(
        "--sheet-id",
        help="Google Sheet ID. Defaults to GOOGLE_SHEET_ID from .env",
        type=str,
    )

    parser.add_argument(
        "--service-account-file",
        help=(
            "Path to Google service account JSON. Defaults to "
            "GOOGLE_SERVICE_ACCOUNT_FILE from .env"
        ),
        type=str,
    )

    parser.add_argument(
        "--sheets-range",
        help="Column-only Google Sheets range, such as A:F. Defaults to GOOGLE_SHEET_RANGE",
        type=str,
    )

    parser.add_argument(
        "--sheets-replace",
        help="Replace each monthly tab range instead of appending rows",
        action="store_true",
    )

    parser.add_argument(
        "--sheets-include-header",
        help="Include the CSV header when appending to existing monthly tabs",
        action="store_true",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.input and not args.file:
        parser.print_help()
        print("\nError: Either --input or --file must be specified")
        sys.exit(1)

    if args.file and not args.tag:
        print("Error: --tag must be specified when using --file")
        sys.exit(1)

    # Create consolidator
    consolidator = StatementConsolidator()

    # Process input
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: Input directory not found: {args.input}")
            sys.exit(1)

        print(f"Processing statements from {args.input}...")
        consolidator.add_statements_from_directory(args.input)

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: Input file not found: {args.file}")
            sys.exit(1)

        print(f"Processing file: {args.file}")
        consolidator.add_statement(args.file, args.tag, args.source)

    # Consolidate and save
    if consolidator.transactions:
        df = consolidator.consolidate(args.output)

        if args.push_to_sheets:
            try:
                from google_sheets import push_dataframe_to_sheets

                result = push_dataframe_to_sheets(
                    df,
                    service_account_file=args.service_account_file,
                    sheet_id=args.sheet_id,
                    range_columns=args.sheets_range,
                    replace=args.sheets_replace,
                    include_header=args.sheets_include_header,
                )
                mode = "replaced" if result.replace else "appended"
                print(
                    f"Google Sheets push complete: {mode} {result.rows_updated} "
                    f"rows across {len(result.sheets_modified)} monthly tabs"
                )
            except ImportError as e:
                print(f"Error: Missing Google Sheets dependency: {e}")
                print("Run: python -m pip install -r requirements.txt")
                sys.exit(1)
            except Exception as e:
                print(f"Error pushing to Google Sheets: {e}")
                sys.exit(1)

        # Print summary
        summary = consolidator.get_summary()
        print("\n" + "=" * 50)
        print("CONSOLIDATION SUMMARY")
        print("=" * 50)
        print(f"Total Transactions: {summary['total_transactions']}")
        print(f"Total Debits: ₹{summary['total_debits']:,.2f}")
        print(f"Total Credits: ₹{summary['total_credits']:,.2f}")
        print(f"Net: ₹{summary['total_credits'] - summary['total_debits']:,.2f}")

        if summary["by_tag"]:
            print("\nBy Bank/Tag:")
            for tag, count in summary["by_tag"].items():
                print(f"  {tag.upper()}: {count} transactions")

        print(f"\nDate Range: {summary['date_range'][0]} to {summary['date_range'][1]}")
        print("=" * 50)
    else:
        print("No transactions found to consolidate")
        sys.exit(1)


if __name__ == "__main__":
    main()

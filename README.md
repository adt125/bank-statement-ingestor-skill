# Bank Statement Ingester

Consolidate bank statements from multiple accounts and formats into a single unified CSV file.

## Features

- Parse bank statements from Excel (.xlsx, .xls) and PDF formats
- Support for multiple banks: SBI, HDFC, Credit Card
- Extract transaction details while ignoring header/summary sections
- Automatic tagging by bank/account type
- Consolidate multiple statements into one CSV with custom sorting (HDFC → SBI → CC)
- Optional Google Sheets export, grouped into monthly tabs

## Output Format

Consolidated CSV with columns:

- `date` - Transaction date
- `description` - Transaction details
- `amount` - Transaction amount
- `type` - Credit or Debit
- `source` - Account name/number
- `tag` - Bank/account type (sbi, hdfc, cc)

**Transactions are sorted by bank/tag (HDFC, SBI, CC) and then by date within each group.**

## Usage

```bash
# Process statements from samples folder
python src/main.py -i samples -o consolidated_statements.csv

# Process single file
python src/main.py -f statement.xlsx -t sbi -o output.csv

# Specify account source
python src/main.py -f statement.xlsx -t sbi -s "AccountXXXX" -o output.csv

# Push consolidated rows to Google Sheets after CSV export
python src/main.py -i samples -o consolidated_statements.csv --push-to-sheets

# Replace monthly tab contents instead of appending
python src/main.py -i samples -o consolidated_statements.csv --push-to-sheets --sheets-replace
```

## Google Sheets Export

The Google Sheets export uses a Google Cloud service account. Rows are grouped
by the `date` column into monthly tabs like `2026-06`; missing tabs are created
automatically.

Set up local configuration:

```bash
cp .env.example .env
```

Then edit `.env`:

```text
GOOGLE_SERVICE_ACCOUNT_FILE=google-service-account.json
GOOGLE_SHEET_ID=your-google-sheet-id
GOOGLE_SHEET_RANGE=A:F
```

`GOOGLE_SERVICE_ACCOUNT_FILE` can be an absolute path or a path relative to this
project root. Do not commit the service account JSON. Share the target Google
Sheet with the service account's `client_email`, otherwise the API will
authenticate but fail to write.

The spreadsheet ID is the long value in a Sheets URL:

```text
https://docs.google.com/spreadsheets/d/<spreadsheet-id>/edit
```

CLI overrides are also available:

```bash
python src/main.py -i samples --push-to-sheets \
  --service-account-file google-service-account.json \
  --sheet-id your-google-sheet-id \
  --sheets-range A:F \
  --sheets-replace
```

## Sample Statements

Place your bank statement files in the `samples/` folder. The system auto-detects bank type from filenames:

- **SBI**: `sbi_*.xlsx`, `sbi_*.xls` → tag: `sbi`
- **HDFC**: `hdfc_*.xlsx`, `hdfc_*.xls` → tag: `hdfc`
- **Credit Card**: `*cc*.pdf`, `*creditcard*.pdf` → tag: `cc`

Example:

```
samples/
├── sbi_statement_may.xlsx
├── hdfc_account_may.xlsx
└── hdfc_cc_statement.pdf
```

## Project Structure

```
bank-statement-ingestor/
├── src/
│   ├── main.py              # Entry point
│   ├── consolidator.py      # Main consolidation logic
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── base.py          # Base parser class
│   │   ├── sbi_parser.py    # SBI statement parser (Excel)
│   │   ├── hdfc_parser.py   # HDFC statement parser (Excel)
│   │   └── cc_parser.py     # Credit card parser (PDF)
│   └── __init__.py
├── samples/                 # Place your statements here
├── requirements.txt         # Python dependencies
└── README.md
```

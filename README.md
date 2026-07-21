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
- `source` - Bank/account type (hdfc, sbi, cc)
- `tag` - Blank user-editable tag/category

**Transactions are sorted by bank/tag (HDFC, SBI, CC) and then by date within each group.**

## Usage

```bash
# One-command flow: read hdfc/, sbi/, cc/, consolidate, and push to Sheets
python run_ingest.py

# Dry/local flow: only create consolidated_statements.csv
python run_ingest.py --no-sheets

# Process statements from bank-specific folders
python src/main.py -i . -o consolidated_statements.csv

# Process single file
python src/main.py -f statement.xlsx -t sbi -o output.csv

# Specify account source
python src/main.py -f statement.xlsx -t sbi -s "AccountXXXX" -o output.csv

# Push consolidated rows to Google Sheets after CSV export
python src/main.py -i . -o consolidated_statements.csv --push-to-sheets

# Replace monthly tab contents instead of appending
python src/main.py -i . -o consolidated_statements.csv --push-to-sheets --sheets-replace
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
python src/main.py -i . --push-to-sheets \
  --service-account-file google-service-account.json \
  --sheet-id your-google-sheet-id \
  --sheets-range A:F \
  --sheets-replace
```

## Sample Statements

Place your bank statement files in bank-specific folders:

```
hdfc/
└── statement_june.xls
sbi/
└── statement_june.xlsx
cc/
└── statement_june.pdf
```

Then run:

```bash
python run_ingest.py
```

`run_ingest.py` uses replace mode for Google Sheets by default, which makes
reruns safer because it avoids appending duplicate rows. Use `--append` only
when you intentionally want to keep existing rows and add new ones.

Folder names take priority, so files inside `hdfc/`, `sbi/`, or `cc/` can have
generic names. Files directly inside another input folder still use filename
detection as a fallback:

- **SBI**: `sbi_*.xlsx`, `sbi_*.xls` → tag: `sbi`
- **HDFC**: `hdfc_*.xlsx`, `hdfc_*.xls` → tag: `hdfc`
- **Credit Card**: `*cc*.pdf`, `*creditcard*.pdf` → tag: `cc`

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
├── hdfc/                    # HDFC statements
├── sbi/                     # SBI statements
├── cc/                      # Credit card statements
├── samples/                 # Legacy sample statements
├── requirements.txt         # Python dependencies
└── README.md
```

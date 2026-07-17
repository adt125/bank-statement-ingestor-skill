# Google APIs and Google Sheets Replication Guide

This guide explains how this project uses Google APIs and how another agent can
replicate the Google Sheets export behavior in a new or adjacent project.

## Project Context

The project is an invoice harvesting pipeline:

1. Download invoice PDF attachments from Outlook.
2. Extract invoice line items into `assets/temp/invoice_items.csv`.
3. Use Gemini to classify each item and write `assets/temp/tagged_expenses.csv`.
4. Push the tagged CSV rows to Google Sheets.
5. Clean temporary files.

The Google Sheets write path is implemented mainly in
`scripts/push_to_google_sheets.py`. The full pipeline calls it from
`scripts/pipeline.py`.

## Google API Usage Summary

The project uses two Google API families:

- Google Sheets API, via `google-api-python-client` and `google-auth`.
- Gemini API, via `google-genai`, for tagging invoice item descriptions before
  the final CSV is pushed to Sheets.

Only the Sheets API writes to Google Sheets. Gemini is upstream enrichment that
adds a `tag` column to the CSV.

## Dependencies

The relevant packages are declared in `requirements.txt`:

```text
google-api-python-client>=2.130.0
google-auth>=2.29.0
google-genai>=1.66.0,<2.0.0
pandas
python-dotenv>=1.0.0
```

For a Sheets-only replication, install at least:

```bash
python3 -m pip install google-api-python-client google-auth python-dotenv
```

For the complete pipeline with Gemini tagging, also install:

```bash
python3 -m pip install google-genai pandas
```

## Environment Configuration

The project loads `invoice-harvestor/.env` through `config.load_project_env()`.
The file is loaded from the project root, not from the current shell directory:

```python
load_dotenv(dotenv_path=ROOT / ".env")
```

The Sheets export expects these values:

```text
GOOGLE_SERVICE_ACCOUNT_FILE=google-service-account.json
GOOGLE_SHEET_ID=your-google-sheet-id
GOOGLE_SHEET_RANGE=A:K
```

For Gemini tagging, the project also expects:

```text
GOOGLE_GENAI_USE_VERTEXAI=0
GOOGLE_API_KEY=your-gemini-api-key
```

Important path behavior:

- `GOOGLE_SERVICE_ACCOUNT_FILE` is resolved relative to `invoice-harvestor/assets/`
  when it is not an absolute path.
- Therefore `GOOGLE_SERVICE_ACCOUNT_FILE=google-service-account.json` means:

```text
invoice-harvestor/assets/google-service-account.json
```

Column range note:

- The current code default is `A:K` in `scripts/config.py`.
- `README.md` examples mention `A:F` or `A:E` in older places.
- Replicate the current code behavior with `A:K`, or set a narrower/wider range
  explicitly based on the actual CSV columns being written.

## Google Cloud Setup

To replicate the Sheets write path:

1. Create or choose a Google Cloud project.
2. Enable the Google Sheets API.
3. Create a service account.
4. Download the service account JSON key.
5. Place the JSON key in `invoice-harvestor/assets/`, or use an absolute path.
6. Open the target Google Sheet.
7. Share the sheet with the service account email from the JSON key's
   `client_email` field.
8. Put the spreadsheet ID in `GOOGLE_SHEET_ID`.

The spreadsheet ID is the long ID in a Google Sheets URL:

```text
https://docs.google.com/spreadsheets/d/<spreadsheet-id>/edit
```

## Authentication Model

Sheets authentication uses a service account, not OAuth user login.

The required OAuth scope is:

```python
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
```

The project creates credentials like this:

```python
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

credentials = Credentials.from_service_account_file(
    service_account_file,
    scopes=SCOPES,
)
service = build("sheets", "v4", credentials=credentials)
```

Replicate this exactly unless the target project needs delegated user OAuth.
The service account must have access to the destination spreadsheet, otherwise
the API call will fail even if the JSON key is valid.

## Input CSV Contract

The Sheets push reads a CSV file, treats the first row as the header, and writes
all remaining rows as data.

Default input:

```text
invoice-harvestor/assets/temp/tagged_expenses.csv
```

The extractor initially produces:

```text
source_file,invoice_date,description,quantity,amount
```

The Gemini tagging step appends:

```text
tag
```

The Sheets push requires at minimum:

```text
invoice_date
```

`invoice_date` is mandatory because rows are grouped by invoice month. Supported
date formats are:

- `YYYY-MM-DD`
- `DD-MM-YYYY`
- `DD/MM/YYYY`
- `YYYYMMDD`

The extracted invoices normalize dates to `YYYY-MM-DD`, which is the preferred
format.

## Monthly Sheet Tab Behavior

Rows are grouped by month based on the `invoice_date` column.

Example:

```text
2026-05-01 -> sheet tab "2026-05"
2026-05-31 -> sheet tab "2026-05"
2026-06-01 -> sheet tab "2026-06"
```

The relevant logic is:

```python
key = datetime.strptime(value, fmt).strftime("%Y-%m")
grouped.setdefault(key, []).append(row)
```

Each month is written to its own tab. The project checks the spreadsheet's
existing sheet titles and creates missing monthly tabs before writing rows.

Tab creation uses `spreadsheets().batchUpdate()` with `addSheet` requests:

```python
requests = [
    {"addSheet": {"properties": {"title": sheet_name}}}
    for sheet_name in created_titles
]

service.spreadsheets().batchUpdate(
    spreadsheetId=sheet_id,
    body={"requests": requests},
).execute()
```

## Range Construction

The configured range should contain only columns, such as:

```text
A:K
```

The code also accepts values with a sheet prefix, but strips the prefix and uses
only the columns:

```python
columns = target_range.split("!", 1)[-1]
```

Then it builds a per-month range:

```python
"'2026-05'!A:K"
```

Sheet names are single-quoted, and embedded single quotes are escaped.

The range validator only accepts column-only ranges:

```text
A:E
A:K
A
```

It rejects row-specific ranges such as:

```text
A1:K100
```

## Append Versus Replace

The project supports two write modes.

### Append Mode

Default mode appends rows:

```python
service.spreadsheets().values().append(
    spreadsheetId=sheet_id,
    range=target_range,
    valueInputOption="USER_ENTERED",
    insertDataOption="INSERT_ROWS",
    body={"values": rows},
).execute()
```

Append mode behavior:

- Existing data is preserved.
- New rows are inserted after existing table data in that monthly tab/range.
- The header is not included by default.
- The header is included if `--include-header` is passed.
- The header is automatically included when a monthly tab was just created.

### Replace Mode

`--replace` clears each monthly range and writes the header plus rows:

```python
values_api.clear(spreadsheetId=sheet_id, range=target_range).execute()
values_api.update(
    spreadsheetId=sheet_id,
    range=target_range,
    valueInputOption="USER_ENTERED",
    body={"values": rows},
).execute()
```

Replace mode behavior:

- The monthly tab itself is not deleted.
- The configured range is cleared.
- The CSV header is always written as the first row.
- The latest CSV rows replace prior data in that monthly tab.

For scheduled monthly runs, `--replace` is the safer mode when reruns are
possible, because append mode can duplicate rows.

## CLI Usage

Run only the Sheets push:

```bash
cd invoice-harvestor
python3 scripts/push_to_google_sheets.py
```

Replace each monthly tab's configured range:

```bash
python3 scripts/push_to_google_sheets.py --replace
```

Use explicit inputs:

```bash
python3 scripts/push_to_google_sheets.py \
  --input temp/tagged_expenses.csv \
  --service-account-file google-service-account.json \
  --sheet-id your-google-sheet-id \
  --range A:K \
  --replace
```

Run through the full pipeline:

```bash
python3 scripts/pipeline.py --folder "Instamart" --last-month --replace
```

The full pipeline passes `replace` into `push_to_sheets_core()`, but does not
currently expose `GOOGLE_SHEET_RANGE` through the pipeline config. The push
function will use the code default `A:K` unless called directly with a different
`range_columns_var`.

## Library-Level Replication

The core function to call is:

```python
from push_to_google_sheets import push_to_sheets_core

result = push_to_sheets_core(
    csv_file="temp/tagged_expenses.csv",
    service_account_file="google-service-account.json",
    sheet_id="your-google-sheet-id",
    range_columns_var="A:K",
    replace=True,
    include_header=False,
)

print(result.rows_updated)
print(result.sheets_modified)
```

When using relative paths, remember that `push_to_sheets_core()` resolves them
relative to `invoice-harvestor/assets/`. For example, use
`temp/tagged_expenses.csv`, not `assets/temp/tagged_expenses.csv`.

## Minimal Implementation Blueprint

To recreate this in another codebase:

1. Load environment variables from the project's `.env`.
2. Resolve the service account key path.
3. Read the CSV with Python's `csv.reader`.
4. Split the first row into `header` and all remaining rows into `data_rows`.
5. Validate that `invoice_date` exists in `header`.
6. Parse each row's `invoice_date` into a `YYYY-MM` tab name.
7. Build an ordered mapping of month tab to rows.
8. Create a Sheets API service with service-account credentials and the
   `https://www.googleapis.com/auth/spreadsheets` scope.
9. Fetch existing tab titles with `spreadsheets().get(fields="sheets.properties.title")`.
10. Create any missing monthly tabs using `spreadsheets().batchUpdate()`.
11. For each month, build a range like `'<month>'!A:K`.
12. If replacing, clear the range and update it with `[header] + rows`.
13. If appending, append rows; include the header only for new tabs or when
    explicitly requested.
14. Use `valueInputOption="USER_ENTERED"` so Sheets interprets values naturally.
15. Return a structured result with total updated rows, modified sheets, and
    whether replace mode was used.

## Error Conditions To Preserve

The current implementation fails fast for these cases:

- Missing service account path.
- Missing spreadsheet ID.
- Service account JSON file does not exist.
- CSV file does not exist.
- CSV file is empty.
- CSV has no data rows.
- CSV does not contain `invoice_date`.
- A row has a missing or unparsable `invoice_date`.
- `GOOGLE_SHEET_RANGE` is not a column-only range.

Replicating agents should preserve these validations because they prevent
partially written or misrouted spreadsheet data.

## Important Implementation Details

- Use `OrderedDict` or normal dict insertion order to preserve the first-seen
  month order from the CSV.
- Quote sheet names in ranges, even though current month names are simple.
- Return the API's updated row count by checking both possible response shapes:
  top-level `updatedRows` and nested `updates.updatedRows`.
- Do not store Google credentials in the repository. Keep the service account
  JSON in ignored local assets or a secret store.
- Share the spreadsheet with the service account email. API credentials alone
  are not enough.
- Be careful with append mode on reruns. It can duplicate data.
- Keep `valueInputOption="USER_ENTERED"` if the sheet should treat dates and
  numbers as editable Sheets values instead of raw strings.

## Files To Study Before Modifying

- `scripts/push_to_google_sheets.py`: complete Sheets write implementation.
- `scripts/config.py`: path defaults, `.env` loading, and default range.
- `scripts/pipeline.py`: full orchestration and how the push function is called.
- `scripts/item_llm_tagging.py`: Gemini tagging that produces the pushed CSV.
- `scripts/extract_invoice_items.py`: original CSV schema and date normalization.
- `.env.example`: expected environment variables, though its range example is
  older than the current `A:K` code default.

## Suggested Tests For A Replica

For a robust replica, add tests around:

- `month_key()` parsing all supported date formats.
- Failure when `invoice_date` is missing.
- `range_columns()` accepting `A:K` and rejecting `A1:K100`.
- `month_range()` quoting sheet names.
- Header inclusion rules for replace, append, include-header, and new-tab cases.
- API call sequencing: `get` existing sheets, `batchUpdate` missing tabs, then
  `clear` plus `update` or `append`.

Use fake service objects or mocks for Sheets API calls so tests do not write to
a real spreadsheet.

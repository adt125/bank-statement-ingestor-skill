# Adding a New Bank

Add a new entry to `BANK_CONFIGS` in `scripts/parser.py`.

## Structure

```python
BANK_CONFIGS = {
    "your_bank": {
        "date_col":    ["Date", "Txn Date"],      # possible column names for date
        "desc_col":    ["Narration", "Description"],
        "debit_col":   ["Debit Amount", "Withdrawal"],
        "credit_col":  ["Credit Amount", "Deposit"],
        "balance_col": ["Balance", "Closing Balance"],
        "date_fmt":    ["%d/%m/%Y", "%d-%m-%Y"],  # try these formats in order
    },
}
```

## Detection

Add the bank name to `detect_bank()`:

```python
def detect_bank(text: str) -> str:
    text = text.lower()
    if "kotak"    in text: return "kotak"
    if "yes bank" in text: return "yes_bank"
    if "idfc"     in text: return "idfc"
    # ... existing banks ...
```

## Finding column names

Open the PDF/CSV manually and note the exact header row. Common variations:

| Bank | Date column | Description column | Debit column |
|---|---|---|---|
| Kotak | "Trans Date" | "Description" | "Debit" |
| Yes Bank | "Date" | "Transaction Details" | "Amount(Dr)" |
| IDFC | "Value Date" | "Narration" | "Dr Amount" |
| IndusInd | "Transaction Date" | "Particulars" | "Debit" |

## Date formats

| Format string | Example |
|---|---|
| `%d/%m/%Y` | 15/03/2024 |
| `%d-%m-%Y` | 15-03-2024 |
| `%d/%m/%y` | 15/03/24 |
| `%d %b %Y` | 15 Mar 2024 |
| `%b %d, %Y` | Mar 15, 2024 |

## Testing

```bash
python scripts/pipeline.py your_new_bank_statement.pdf --dry-run
```

If transactions aren't parsing, add a `print(df.columns.tolist())` in `parse_pdf()` right after the DataFrame is built to see the actual column names.

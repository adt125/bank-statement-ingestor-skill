import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


ROOT = Path(__file__).resolve().parents[1]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DEFAULT_RANGE = "A:F"
DATE_COLUMN = "date"


@dataclass
class SheetsPushResult:
    rows_updated: int
    sheets_modified: List[str]
    replace: bool


def load_project_env() -> None:
    """Load local .env settings from the project root."""
    load_dotenv(dotenv_path=ROOT / ".env")


def resolve_project_path(path_value: str) -> Path:
    """Resolve relative paths from the project root."""
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return ROOT / path


def push_dataframe_to_sheets(
    df: pd.DataFrame,
    service_account_file: Optional[str] = None,
    sheet_id: Optional[str] = None,
    range_columns: Optional[str] = None,
    replace: bool = False,
    include_header: bool = False,
) -> SheetsPushResult:
    """
    Push consolidated bank transactions to Google Sheets.

    Rows are grouped into monthly tabs using the CSV/DataFrame `date` column.
    """
    load_project_env()

    service_account_file = service_account_file or os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE"
    )
    sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID")
    range_columns = range_columns or os.getenv("GOOGLE_SHEET_RANGE", DEFAULT_RANGE)

    if not service_account_file:
        raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT_FILE or --service-account-file")
    if not sheet_id:
        raise ValueError("Missing GOOGLE_SHEET_ID or --sheet-id")

    service_account_path = resolve_project_path(service_account_file)
    if not service_account_path.exists():
        raise FileNotFoundError(
            f"Google service account file not found: {service_account_path}"
        )

    columns = normalize_range_columns(range_columns)
    header, data_rows = dataframe_rows(df)
    grouped_rows = group_rows_by_month(header, data_rows)

    credentials = Credentials.from_service_account_file(
        str(service_account_path), scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=credentials)

    existing_titles = get_sheet_titles(service, sheet_id)
    missing_titles = [
        title for title in grouped_rows.keys() if title not in existing_titles
    ]
    if missing_titles:
        create_sheets(service, sheet_id, missing_titles)

    values_api = service.spreadsheets().values()
    rows_updated = 0
    sheets_modified = []

    for sheet_name, rows in grouped_rows.items():
        target_range = month_range(sheet_name, columns)
        should_include_header = replace or include_header or sheet_name in missing_titles
        values = [header] + rows if should_include_header else rows

        if replace:
            values_api.clear(spreadsheetId=sheet_id, range=target_range).execute()
            response = values_api.update(
                spreadsheetId=sheet_id,
                range=target_range,
                valueInputOption="USER_ENTERED",
                body={"values": values},
            ).execute()
        else:
            response = values_api.append(
                spreadsheetId=sheet_id,
                range=target_range,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": values},
            ).execute()

        rows_updated += extract_updated_rows(response, len(values))
        sheets_modified.append(sheet_name)

    return SheetsPushResult(
        rows_updated=rows_updated,
        sheets_modified=sheets_modified,
        replace=replace,
    )


def dataframe_rows(df: pd.DataFrame) -> tuple[List[str], List[List[object]]]:
    if df.empty:
        raise ValueError("No transactions to push to Google Sheets")

    if DATE_COLUMN not in df.columns:
        raise ValueError(f"Consolidated transactions must contain a '{DATE_COLUMN}' column")

    export_df = df.copy()
    export_df[DATE_COLUMN] = pd.to_datetime(export_df[DATE_COLUMN]).dt.strftime(
        "%Y-%m-%d"
    )
    export_df = export_df.where(pd.notna(export_df), "")

    header = [str(column) for column in export_df.columns]
    rows = export_df.values.tolist()
    if not rows:
        raise ValueError("No transaction rows to push to Google Sheets")
    return header, rows


def group_rows_by_month(
    header: List[str], rows: Iterable[List[object]]
) -> "OrderedDict[str, List[List[object]]]":
    try:
        date_index = header.index(DATE_COLUMN)
    except ValueError as exc:
        raise ValueError(f"Missing required '{DATE_COLUMN}' column") from exc

    grouped: "OrderedDict[str, List[List[object]]]" = OrderedDict()
    for row in rows:
        if date_index >= len(row) or not row[date_index]:
            raise ValueError(f"Transaction row has no {DATE_COLUMN}: {row}")
        sheet_name = month_key(str(row[date_index]))
        grouped.setdefault(sheet_name, []).append(row)

    return grouped


def month_key(value: str) -> str:
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m")
        except ValueError:
            continue
    raise ValueError(f"Could not parse transaction date for Google Sheets: {value}")


def normalize_range_columns(range_columns: str) -> str:
    columns = range_columns.split("!", 1)[-1].strip()
    if not re.fullmatch(r"[A-Z]+(?::[A-Z]+)?", columns, flags=re.IGNORECASE):
        raise ValueError(
            "GOOGLE_SHEET_RANGE must be a column-only range like A:F or A:K"
        )
    return columns.upper()


def month_range(sheet_name: str, columns: str) -> str:
    escaped_name = sheet_name.replace("'", "''")
    return f"'{escaped_name}'!{columns}"


def get_sheet_titles(service, sheet_id: str) -> set[str]:
    response = (
        service.spreadsheets()
        .get(spreadsheetId=sheet_id, fields="sheets.properties.title")
        .execute()
    )
    return {
        sheet["properties"]["title"]
        for sheet in response.get("sheets", [])
        if "properties" in sheet and "title" in sheet["properties"]
    }


def create_sheets(service, sheet_id: str, sheet_names: List[str]) -> None:
    requests = [
        {"addSheet": {"properties": {"title": sheet_name}}}
        for sheet_name in sheet_names
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": requests},
    ).execute()


def extract_updated_rows(response: dict, fallback: int) -> int:
    if "updatedRows" in response:
        return int(response["updatedRows"])
    updates = response.get("updates", {})
    if "updatedRows" in updates:
        return int(updates["updatedRows"])
    return fallback

import pandas as pd
from datetime import datetime
from typing import List, Optional
from .base import BaseParser, Transaction


class SBIParser(BaseParser):
    """Parser for State Bank of India (SBI) statements"""

    def parse(self) -> List[Transaction]:
        """
        Parse SBI statement and extract transactions

        Expected format:
        - Rows 0-10: Header info (account details, balance, etc.)
        - Rows 11+: Transaction table with columns:
          Date, Description, Debit/Credit/Balance
        """
        transactions = []

        # Read file (handle both .xlsx and .xls)
        try:
            # Explicitly specify engine for better compatibility
            if self.filepath.lower().endswith(".xls"):
                df = pd.read_excel(self.filepath, engine="xlrd", header=None)
            else:
                df = pd.read_excel(self.filepath, engine="openpyxl", header=None)
        except Exception as e:
            print(f"Error reading file {self.filepath}: {e}")
            return transactions

        # Extract source if not provided
        if not self.source:
            self.source = self.extract_source_from_df(df)

        # Find the transaction table start
        # Typically starts after account info section
        table_start = self._find_table_start(df)

        if table_start == -1:
            print(f"Could not find transaction table in {self.filepath}")
            return transactions

        # Parse transaction rows
        for idx in range(table_start, len(df)):
            row = df.iloc[idx]

            # Skip empty rows
            if row.isnull().all():
                continue

            # Try to parse transaction
            transaction = self._parse_row(row)
            if transaction:
                transactions.append(transaction)

        return transactions

    def _find_table_start(self, df: pd.DataFrame) -> int:
        """
        Find the row where transaction table starts
        Look for row with "Date" or pattern that matches date format
        """
        for idx, row in df.iterrows():
            # Check if this row contains date-like values
            row_str = " ".join(str(cell) for cell in row if pd.notna(cell))

            # Look for common table headers
            if "Date" in row_str or "Date of Statement" in row_str:
                return idx + 1

            # Look for first date in DD/MM/YYYY or DD-MM-YYYY format
            if any(self._is_date_like(str(cell)) for cell in row if pd.notna(cell)):
                return idx

        return -1

    def _is_date_like(self, s: str) -> bool:
        """Check if string looks like a date"""
        try:
            # Try common date formats
            for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"]:
                try:
                    datetime.strptime(s.strip(), fmt)
                    return True
                except:
                    pass
        except:
            pass
        return False

    def _parse_row(self, row) -> Optional[Transaction]:
        """
        Parse a single transaction row
        Expected columns: Date, Description, Debit/Credit indicators
        """
        try:
            # Extract date (first column)
            date_str = str(row.iloc[0]).strip()
            if not self._is_date_like(date_str):
                return None

            date = self._parse_date(date_str)

            # Extract description (usually middle columns)
            description = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""

            # Find debit/credit amounts
            # Look for numeric values in the row
            amounts = []
            amount_idx = []
            for i, val in enumerate(row.iloc[2:], start=2):
                if pd.notna(val):
                    try:
                        amounts.append(float(val))
                        amount_idx.append(i)
                    except:
                        pass

            if not amounts:
                return None

            # First numeric value is typically the transaction amount
            # We need to determine if it's debit or credit based on column position
            # or explicit marking in the data

            amount = amounts[0]

            # Determine type (Credit/Debit)
            # This depends on column structure - adjust based on actual statement
            trans_type = self._determine_type(row, amount_idx)

            if not trans_type:
                return None

            return Transaction(
                date=date,
                description=description,
                amount=abs(amount),
                type=trans_type,
                source=self.source,
                tag=self.tag,
            )
        except Exception as e:
            # print(f"Error parsing row: {e}")
            return None

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string in various formats"""
        for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y"]:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except:
                pass
        # Default to current date if parsing fails
        return datetime.now()

    def _determine_type(self, row, amount_idx: List[int]) -> Optional[str]:
        """Determine if transaction is Credit or Debit"""
        # This is a heuristic - adjust based on your statement format
        # Usually: if amount is in "Debit" column -> Debit, else -> Credit

        # Look for text indicators
        row_str = " ".join(str(cell) for cell in row if pd.notna(cell))

        if "Debit" in row_str or "DR" in row_str:
            return "Debit"
        elif "Credit" in row_str or "CR" in row_str:
            return "Credit"

        # Default heuristic: if multiple amounts, first is debit
        if len(amount_idx) > 1:
            return "Debit"

        return "Credit"

    def extract_source(self) -> str:
        """Extract account number/name from SBI statement"""
        try:
            # Explicitly specify engine for better compatibility
            if self.filepath.lower().endswith(".xls"):
                df = pd.read_excel(self.filepath, engine="xlrd", header=None)
            else:
                df = pd.read_excel(self.filepath, engine="openpyxl", header=None)
            return self.extract_source_from_df(df)
        except:
            return "Unknown"

    def extract_source_from_df(self, df: pd.DataFrame) -> str:
        """Extract source from dataframe"""
        # Look for account number in header section
        for idx, row in df.iloc[:15].iterrows():
            row_str = " ".join(str(cell) for cell in row if pd.notna(cell))

            # Look for account number patterns
            if "Account Number" in row_str or "A/C" in row_str:
                # Extract the number following it
                for cell in row.iloc[1:]:
                    if pd.notna(cell):
                        return str(cell).strip()

        # Fallback
        return "SBI-Account"

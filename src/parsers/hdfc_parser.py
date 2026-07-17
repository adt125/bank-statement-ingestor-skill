import pandas as pd
from datetime import datetime
from typing import List, Optional
from .base import BaseParser, Transaction


class HDFCParser(BaseParser):
    """Parser for HDFC Bank statements"""

    def parse(self) -> List[Transaction]:
        """
        Parse HDFC statement and extract transactions

        Expected format:
        - Rows 0-19: Header info (customer, account details, statement dates)
        - Row 20: Separator line (asterisks)
        - Row 21: Column headers (Date, Narration, Chq./Ref No., Value Dt, Withdrawal Amt., Deposit Amt., Closing Balance)
        - Rows 22+: Transaction rows
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
        # Look for the header row with Date, Narration, etc.
        table_start = self._find_table_start(df)

        if table_start == -1:
            # Debug: Print first few rows to understand structure
            print(f"Debug: Could not find transaction table in {self.filepath}")
            print(f"Debug: First 10 rows of file:")
            for i in range(min(10, len(df))):
                print(f"  Row {i}: {df.iloc[i].tolist()}")
            return transactions

        # Parse transaction rows. HDFC exports often include an asterisk
        # separator immediately after the header; skip that leading separator,
        # but still stop if another separator appears after transactions begin.
        seen_transactions = False
        for idx in range(table_start + 1, len(df)):
            row = df.iloc[idx]

            # Stop at separator rows only after the transaction table has begun
            if self._is_separator_row(row):
                if seen_transactions:
                    break
                continue

            if row.isnull().all():
                continue

            # Try to parse transaction
            transaction = self._parse_row(row)
            if transaction:
                transactions.append(transaction)
                seen_transactions = True

        return transactions

    def _find_table_start(self, df: pd.DataFrame) -> int:
        """
        Find the row where transaction table header is located
        Look for row with "Date" and "Narration" columns
        """
        for idx, row in df.iterrows():
            row_str = " ".join(str(cell) for cell in row if pd.notna(cell))

            # Look for the header row
            if "Date" in row_str and "Narration" in row_str:
                return idx

            # Also check for the pattern: Date | Narration pattern
            if "Narration" in row_str and any(
                self._is_date_like(str(cell)) for cell in row if pd.notna(cell)
            ):
                return idx

        return -1

    def _is_separator_row(self, row) -> bool:
        """Check if row is a separator (all asterisks or dashes)"""
        row_str = " ".join(str(cell) for cell in row if pd.notna(cell)).strip()

        # Check if mostly special characters
        if len(row_str) > 0:
            special_chars = sum(1 for c in row_str if c in "*-=")
            if special_chars > len(row_str) * 0.8:
                return True

        return False

    def _is_date_like(self, s: str) -> bool:
        """Check if string looks like a date"""
        try:
            for fmt in ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y"]:
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
        Parse a single transaction row from HDFC statement
        Columns: Date | Narration | Chq./Ref No. | Value Dt | Withdrawal Amt. | Deposit Amt. | Closing Balance
        """
        try:
            # Extract date (first column)
            date_str = str(row.iloc[0]).strip()
            if not self._is_date_like(date_str):
                return None

            date = self._parse_date(date_str)

            # Extract narration/description (second column)
            description = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""

            if not description:
                return None

            # HDFC format: Withdrawal Amt. and Deposit Amt. are separate columns
            # Looking at the structure: Col0=Date, Col1=Narration, Col2=Chq/Ref, Col3=Value Dt, Col4=Withdrawal, Col5=Deposit, Col6=Balance

            withdrawal_amt = None
            deposit_amt = None

            # Try to parse withdrawal amount (typically column 4)
            if len(row) > 4 and pd.notna(row.iloc[4]):
                try:
                    withdrawal_amt = float(row.iloc[4])
                except:
                    pass

            # Try to parse deposit amount (typically column 5)
            if len(row) > 5 and pd.notna(row.iloc[5]):
                try:
                    deposit_amt = float(row.iloc[5])
                except:
                    pass

            # Determine type and amount
            if withdrawal_amt and withdrawal_amt > 0:
                amount = withdrawal_amt
                trans_type = "Debit"
            elif deposit_amt and deposit_amt > 0:
                amount = deposit_amt
                trans_type = "Credit"
            else:
                return None

            return Transaction(
                date=date,
                description=description,
                amount=amount,
                type=trans_type,
                source=self.source,
                tag=self.tag,
            )
        except Exception as e:
            # print(f"Error parsing row: {e}")
            return None

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string in various formats"""
        for fmt in ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y"]:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except:
                pass
        # Default to current date if parsing fails
        return datetime.now()

    def extract_source(self) -> str:
        """Extract account number from HDFC statement"""
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
        """Extract account number/name from dataframe"""
        # Look for account number in header section (typically rows 0-20)
        for idx, row in df.iloc[:25].iterrows():
            row_str = " ".join(str(cell) for cell in row if pd.notna(cell))

            # Look for account number patterns
            if "Account No" in row_str:
                # Extract the number following it
                parts = row_str.split("Account No")
                if len(parts) > 1:
                    # Try to extract account number from the rest
                    acc_part = parts[1].strip()
                    # Get first sequence of alphanumeric characters
                    for cell in row.iloc[1:]:
                        if pd.notna(cell):
                            cell_str = str(cell).strip()
                            if cell_str and cell_str != "nan":
                                return cell_str

        # Try to get account holder name
        for idx, row in df.iloc[:10].iterrows():
            row_str = " ".join(str(cell) for cell in row if pd.notna(cell))

            if "MR." in row_str or "MS." in row_str:
                # This might be the account holder name
                for cell in row:
                    if pd.notna(cell):
                        cell_str = str(cell).strip()
                        if cell_str and "MR" in cell_str:
                            return cell_str

        # Fallback
        return "HDFC-Account"

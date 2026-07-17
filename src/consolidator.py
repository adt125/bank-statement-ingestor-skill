import os
from typing import List, Dict
from pathlib import Path
import pandas as pd
from parsers import SBIParser, HDFCParser, CreditCardParser, Transaction


class StatementConsolidator:
    """Consolidate transactions from multiple bank statements"""

    # Mapping of file patterns to parser classes and tags
    PARSER_CONFIG = {
        "sbi": {
            "parser_class": SBIParser,
            "tag": "sbi",
            "patterns": ["sbi", "state bank"],
        },
        "hdfc": {"parser_class": HDFCParser, "tag": "hdfc", "patterns": ["hdfc"]},
        "cc": {
            "parser_class": CreditCardParser,
            "tag": "cc",
            "patterns": ["credit card", "cc", "card"],
        },
    }

    def __init__(self):
        self.transactions: List[Transaction] = []

    def add_statement(self, filepath: str, tag: str, source: str = None) -> bool:
        """
        Add a statement file and parse it

        Args:
            filepath: Path to the statement file
            tag: Bank/account tag (sbi, hdfc, cc)
            source: Optional account name/number

        Returns:
            True if successful, False otherwise
        """
        if tag not in self.PARSER_CONFIG:
            print(f"Unknown tag: {tag}")
            return False

        parser_class = self.PARSER_CONFIG[tag]["parser_class"]

        try:
            parser = parser_class(filepath, tag, source)
            new_transactions = parser.parse()

            print(
                f"Parsed {len(new_transactions)} transactions from {os.path.basename(filepath)}"
            )
            self.transactions.extend(new_transactions)
            return True
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return False

    def add_statements_from_directory(self, directory: str) -> None:
        """
        Auto-detect and parse all statement files in a directory

        Files should be named with bank identifier (e.g., SBI_statement.xlsx, HDFC_Jan.xls, cc_statement.pdf)
        File extension takes priority: .pdf = CC, .xlsx/.xls = SBI/HDFC
        """
        if not os.path.isdir(directory):
            print(f"Directory not found: {directory}")
            return

        files = Path(directory).glob("*")

        for filepath in files:
            if not filepath.is_file():
                continue

            if filepath.suffix.lower() not in [".xlsx", ".xls", ".csv", ".pdf"]:
                continue

            # Try to detect tag from filename and extension
            tag = self._detect_tag(filepath.name, filepath.suffix)

            if tag:
                print(f"Detected {tag.upper()} statement: {filepath.name}")
                self.add_statement(str(filepath), tag)
            else:
                print(f"Could not detect bank from filename: {filepath.name}")

    def _detect_tag(self, filename: str, extension: str = None) -> str:
        """
        Detect bank tag from filename and extension

        Priority:
        1. File extension (PDF = CC)
        2. Filename patterns for SBI/HDFC (Excel files only)
        """
        filename_lower = filename.lower()
        extension_lower = extension.lower() if extension else ""

        # Check extension first
        if extension_lower == ".pdf":
            # PDF files could be CC or others, check filename patterns
            for tag, config in self.PARSER_CONFIG.items():
                for pattern in config["patterns"]:
                    if pattern in filename_lower:
                        return tag
            # Default to CC for PDF files
            return "cc"

        # For Excel files, only detect SBI or HDFC (not CC)
        if extension_lower in [".xlsx", ".xls", ".csv"]:
            for tag, config in self.PARSER_CONFIG.items():
                if tag == "cc":  # Skip CC for Excel files
                    continue
                for pattern in config["patterns"]:
                    if pattern in filename_lower:
                        return tag

        # No match found
        return None

    def consolidate(self, output_file: str = None) -> pd.DataFrame:
        """
        Consolidate all transactions into a single DataFrame

        Transactions are sorted by tag (hdfc, sbi, cc) and then by date

        Returns:
            DataFrame with consolidated transactions
        """
        if not self.transactions:
            print("No transactions to consolidate")
            return pd.DataFrame()

        # Convert transactions to DataFrame
        data = [
            {
                "date": t.date,
                "description": t.description,
                "amount": t.amount,
                "type": t.type,
                "source": t.source,
                "tag": t.tag,
            }
            for t in self.transactions
        ]

        df = pd.DataFrame(data)

        # Convert date to datetime
        df["date"] = pd.to_datetime(df["date"])

        # Sort by tag (in order: hdfc, sbi, cc) and then by date
        tag_order = {"hdfc": 0, "sbi": 1, "cc": 2}
        df["tag_order"] = df["tag"].map(lambda x: tag_order.get(x, 3))
        df = (
            df.sort_values(["tag_order", "date"])
            .drop("tag_order", axis=1)
            .reset_index(drop=True)
        )

        # Save if output file specified
        if output_file:
            df.to_csv(output_file, index=False)
            print(f"Consolidated {len(df)} transactions to {output_file}")

        return df

    def get_summary(self) -> Dict:
        """Get summary statistics"""
        if not self.transactions:
            return {}

        summary = {
            "total_transactions": len(self.transactions),
            "total_debits": sum(
                t.amount for t in self.transactions if t.type == "Debit"
            ),
            "total_credits": sum(
                t.amount for t in self.transactions if t.type == "Credit"
            ),
            "by_tag": {},
            "date_range": (
                min(t.date for t in self.transactions),
                max(t.date for t in self.transactions),
            ),
        }

        # Count by tag
        for t in self.transactions:
            if t.tag not in summary["by_tag"]:
                summary["by_tag"][t.tag] = 0
            summary["by_tag"][t.tag] += 1

        return summary

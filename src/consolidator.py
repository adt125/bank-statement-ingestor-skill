import os
from typing import List, Dict
from pathlib import Path
import pandas as pd
from parsers import SBIParser, HDFCParser, CreditCardParser, Transaction


class StatementConsolidator:
    """Consolidate transactions from multiple bank statements"""

    SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".pdf"}

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

        Preferred layout:
          directory/
            hdfc/
            sbi/
            cc/

        Files in those folders are routed by folder name. Files directly under
        the input directory still use filename-based detection as a fallback.
        """
        if not os.path.isdir(directory):
            print(f"Directory not found: {directory}")
            return

        input_path = Path(directory)
        files = self._statement_files(input_path)

        for filepath in files:
            if not filepath.is_file():
                continue

            if filepath.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue

            tag = self._detect_tag_from_path(filepath, input_path)

            if tag:
                print(f"Detected {tag.upper()} statement: {filepath}")
                self.add_statement(str(filepath), tag)
            else:
                print(f"Could not detect bank from filename: {filepath.name}")

    def _statement_files(self, input_path: Path):
        bank_dirs = [
            input_path / tag
            for tag in self.PARSER_CONFIG
            if (input_path / tag).is_dir()
        ]

        if bank_dirs:
            for filepath in sorted(input_path.iterdir()):
                if filepath.is_file():
                    yield filepath
            for bank_dir in bank_dirs:
                yield from sorted(bank_dir.rglob("*"))
            return

        yield from sorted(input_path.rglob("*"))

    def _detect_tag_from_path(self, filepath: Path, input_path: Path) -> str:
        """
        Detect bank tag from folder first, then filename.

        A folder named hdfc, sbi, or cc under the input directory wins over
        filename heuristics, so generic filenames like statement.xls work.
        """
        try:
            relative_path = filepath.relative_to(input_path)
        except ValueError:
            relative_path = filepath

        folder_parts = [part.lower() for part in relative_path.parts[:-1]]
        for part in folder_parts:
            if part in self.PARSER_CONFIG:
                return part

        return self._detect_tag(filepath.name, filepath.suffix)

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
        if extension_lower in [".xlsx", ".xls"]:
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
                "source": t.tag,
                "tag": "",
            }
            for t in self.transactions
        ]

        df = pd.DataFrame(data)

        # Convert date to datetime
        df["date"] = pd.to_datetime(df["date"])

        # Sort by source (in order: hdfc, sbi, cc) and then by date
        tag_order = {"hdfc": 0, "sbi": 1, "cc": 2}
        df["tag_order"] = df["source"].map(lambda x: tag_order.get(x, 3))
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

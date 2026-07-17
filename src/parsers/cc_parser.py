import pdfplumber
from datetime import datetime
from typing import List, Optional
import re
from .base import BaseParser, Transaction


class CreditCardParser(BaseParser):
    """Parser for Credit Card statements (PDF format)"""
    
    def parse(self) -> List[Transaction]:
        """
        Parse credit card PDF statement and extract transactions
        
        Expected format:
        - Header section: Card details, account info
        - Domestic Transactions section with columns:
          Date | Transaction Description | Base NeuCoins | Amount (in Rs.)
        - Amounts with "Cr" suffix are credits (payments)
        - Amounts without suffix are debits (charges)
        """
        transactions = []
        
        try:
            with pdfplumber.open(self.filepath) as pdf:
                # Extract source from first page if not provided
                if not self.source:
                    self.source = self.extract_source_from_pdf(pdf)
                
                # Parse all pages
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    
                    # Find transaction section
                    transactions.extend(self._parse_page_text(text))
        except Exception as e:
            print(f"Error reading PDF {self.filepath}: {e}")
            return transactions
        
        return transactions
    
    def _parse_page_text(self, page_text: str) -> List[Transaction]:
        """Extract transactions from page text"""
        transactions = []
        
        # Find "Domestic Transactions" section
        domestic_idx = page_text.find("Domestic Transactions")
        if domestic_idx == -1:
            return transactions
        
        # Extract lines after "Domestic Transactions"
        remaining_text = page_text[domestic_idx:]
        lines = remaining_text.split('\n')
        
        # Skip header lines (Date, Transaction Description, etc.)
        transaction_start = 0
        for i, line in enumerate(lines):
            if 'Date' in line and 'Transaction Description' in line:
                transaction_start = i + 1
                break
        
        # Parse transaction rows
        i = transaction_start
        while i < len(lines):
            line = lines[i].strip()
            
            # Stop at page breaks or section ends
            if not line or 'Page' in line or 'NeuCoins Summary' in line or '=' in line:
                break
            
            # Try to parse as date (DD/MM/YYYY format)
            if self._is_date_line(line):
                # This might be start of a transaction
                transaction = self._parse_transaction_block(lines, i)
                if transaction:
                    transactions.append(transaction)
                    i += 1
            else:
                i += 1
        
        return transactions
    
    def _is_date_line(self, line: str) -> bool:
        """Check if line starts with a date"""
        # Look for DD/MM/YYYY pattern
        return bool(re.match(r'^\d{2}/\d{2}/\d{4}', line))
    
    def _parse_transaction_block(self, lines: List[str], start_idx: int) -> Optional[Transaction]:
        """
        Parse a transaction from one or more lines
        
        Credit card transactions can span multiple lines:
        - Line 1: Date Description Amount
        - Or: Date Description (with optional timestamp)
               Continued description
               Amount
        """
        try:
            line = lines[start_idx].strip()
            
            # Parse date
            date_match = re.match(r'(\d{2}/\d{2}/\d{4})', line)
            if not date_match:
                return None
            
            date_str = date_match.group(1)
            date = self._parse_date(date_str)
            
            # Remove date and timestamp from line
            remaining = re.sub(r'\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}|\d{2}/\d{2}/\d{4}', '', line).strip()
            
            # Look for amount at end of line or in following lines
            amount, is_credit = self._extract_amount_from_text(remaining)
            
            if amount is None:
                # Amount might be on next line
                if start_idx + 1 < len(lines):
                    next_line = lines[start_idx + 1].strip()
                    amount, is_credit = self._extract_amount_from_text(next_line)
                    remaining = remaining + " " + next_line
            
            if amount is None:
                return None
            
            # Extract description (everything except the amount)
            description = self._clean_description(remaining.rsplit(str(amount), 1)[0])
            
            if not description:
                return None
            
            trans_type = 'Credit' if is_credit else 'Debit'
            
            return Transaction(
                date=date,
                description=description,
                amount=amount,
                type=trans_type,
                source=self.source,
                tag=self.tag
            )
        except Exception as e:
            # print(f"Error parsing transaction: {e}")
            return None
    
    def _extract_amount_from_text(self, text: str) -> tuple:
        """
        Extract amount and determine if it's credit or debit
        
        Returns: (amount, is_credit)
        Credit amounts have "Cr" suffix
        """
        # Look for amount patterns
        # Amount with Cr suffix: 34,908.00 Cr or 34908.00Cr
        credit_match = re.search(r'(\d+,?\d+\.?\d*)\s*Cr', text, re.IGNORECASE)
        if credit_match:
            amount_str = credit_match.group(1).replace(',', '')
            try:
                return float(amount_str), True
            except:
                pass
        
        # Regular amount (debit)
        amount_match = re.search(r'(\d+,?\d+\.?\d*)\s*$', text)
        if amount_match:
            amount_str = amount_match.group(1).replace(',', '')
            try:
                return float(amount_str), False
            except:
                pass
        
        return None, False
    
    def _clean_description(self, desc: str) -> str:
        """Clean description text"""
        # Remove leading/trailing whitespace
        desc = desc.strip()
        
        # Remove multiple spaces
        desc = re.sub(r'\s+', ' ', desc)
        
        # Remove reference numbers and timestamps
        desc = re.sub(r'\d{2}:\d{2}:\d{2}', '', desc)
        desc = re.sub(r'\(Ref#.*?\)', '', desc)
        
        return desc.strip()
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string in DD/MM/YYYY format"""
        try:
            return datetime.strptime(date_str.strip(), '%d/%m/%Y')
        except:
            return datetime.now()
    
    def extract_source(self) -> str:
        """Extract card number from credit card statement"""
        try:
            with pdfplumber.open(self.filepath) as pdf:
                return self.extract_source_from_pdf(pdf)
        except:
            return "Unknown"
    
    def extract_source_from_pdf(self, pdf) -> str:
        """Extract card number and account info from PDF"""
        try:
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            
            # Look for Card No pattern
            card_match = re.search(r'Card No[:\s]+(\d+\s\d+XX\s+XXXX\s+\d+)', text)
            if card_match:
                card_num = card_match.group(1).strip()
                return card_num
            
            # Look for AAN (Account Aggregation Number)
            aan_match = re.search(r'AAN\s*[:\s]+(\d+)', text)
            if aan_match:
                aan = aan_match.group(1).strip()
                return f"CC-{aan}"
            
            # Look for account holder name
            name_match = re.search(r'Name\s*[:\s]+([A-Z\s]+)', text)
            if name_match:
                name = name_match.group(1).strip()
                return f"CC-{name}"
        except:
            pass
        
        return "Credit-Card"

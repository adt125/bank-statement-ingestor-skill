from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class Transaction:
    """Represents a single transaction"""
    date: datetime
    description: str
    amount: float
    type: str  # 'Credit' or 'Debit'
    source: str  # Account name/number
    tag: str  # Bank/account type (sbi, hdfc, cc)


class BaseParser(ABC):
    """Base class for all bank statement parsers"""
    
    def __init__(self, filepath: str, tag: str, source: Optional[str] = None):
        """
        Initialize parser
        
        Args:
            filepath: Path to the statement file
            tag: Bank/account tag (sbi, hdfc, cc)
            source: Account name/number (extracted from statement if not provided)
        """
        self.filepath = filepath
        self.tag = tag
        self.source = source
    
    @abstractmethod
    def parse(self) -> List[Transaction]:
        """
        Parse statement and return list of transactions
        
        Returns:
            List of Transaction objects
        """
        pass
    
    @abstractmethod
    def extract_source(self) -> str:
        """Extract account source/number from statement"""
        pass

"""Signal domain model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    """Individual message in a signal thread."""

    content: str
    timestamp: str
    ai: Optional[Dict[str, Any]] = None


@dataclass
class Signal:
    """Trading signal from Discord thread."""

    # MongoDB fields
    id: str  # _id
    thread_id: str
    forum_id: str
    forum_name: str
    thread_name: str
    created_at: Optional[str] = None
    message_count: int = 0
    messages: List[Message] = field(default_factory=list)
    scraped: bool = False
    scrape_ready: bool = False
    collected_at: Optional[str] = None
    scraped_at: Optional[str] = None

    # Parsed signal data
    ticker: Optional[str] = None
    direction: Optional[str] = None  # BUY/SELL, CALL/PUT
    strike: Optional[float] = None
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    expiry: Optional[str] = None
    confidence: Optional[float] = None
    position_size: Optional[float] = None

    @classmethod
    def from_mongo_doc(cls, doc: Dict[str, Any]) -> "Signal":
        """Create Signal from MongoDB document.

        Args:
            doc: MongoDB document

        Returns:
            Signal instance
        """
        messages = [
            Message(
                content=m.get("content", ""),
                timestamp=m.get("timestamp", ""),
                ai=m.get("ai"),
            )
            for m in doc.get("messages", []) or []
        ]

        signal = cls(
            id=str(doc.get("_id", "")),
            thread_id=doc.get("thread_id", ""),
            forum_id=doc.get("forum_id", ""),
            forum_name=doc.get("forum_name", ""),
            thread_name=doc.get("thread_name", ""),
            created_at=doc.get("created_at"),
            message_count=doc.get("message_count", 0),
            messages=messages,
            scraped=doc.get("scraped", False),
            scrape_ready=doc.get("scrape_ready", False),
            collected_at=doc.get("collected_at"),
            scraped_at=doc.get("scraped_at"),
        )

        # Parse signal content
        signal._parse_signal_content()

        return signal

    def _parse_signal_content(self) -> None:
        """Parse signal content from messages."""
        if not self.messages:
            return

        full_content = "\n".join(m.content for m in self.messages)

        # Extract ticker from thread name (e.g., "SPY 2025-11-30")
        parts = self.thread_name.split()
        if parts:
            self.ticker = parts[0].upper()

        # Extract direction
        content_upper = full_content.upper()
        if "BUY CALLS" in content_upper or "DIRECTION: CALL" in content_upper:
            self.direction = "CALL"
        elif "BUY PUTS" in content_upper or "DIRECTION: PUT" in content_upper:
            self.direction = "PUT"
        elif "SELL" in content_upper:
            self.direction = "SELL"

        # Extract numeric values using simple parsing
        self._extract_numeric_values(full_content)

    def _extract_numeric_values(self, content: str) -> None:
        """Extract numeric values from content."""
        import re

        # Confidence (e.g., "Confidence: 65%")
        confidence_match = re.search(r"Confidence:\s*(\d+)%", content, re.IGNORECASE)
        if confidence_match:
            self.confidence = float(confidence_match.group(1)) / 100

        # Strike (e.g., "Strike: $683.00" or "Strike Focus: $683.00")
        strike_match = re.search(r"Strike(?:\s*Focus)?:\s*\$?([\d.]+)", content, re.IGNORECASE)
        if strike_match:
            self.strike = float(strike_match.group(1))

        # Entry Price (e.g., "Entry Price: $1.77" or "Entry Range: $1.77")
        entry_match = re.search(r"Entry(?:\s*(?:Price|Range))?:\s*\$?([\d.]+)", content, re.IGNORECASE)
        if entry_match:
            self.entry_price = float(entry_match.group(1))

        # Target (e.g., "Target 1: $2.10" or "Profit Target: $2.10")
        target_match = re.search(r"(?:Target\s*1|Profit\s*Target):\s*\$?([\d.]+)", content, re.IGNORECASE)
        if target_match:
            self.target_price = float(target_match.group(1))

        # Stop Loss (e.g., "Stop Loss: $1.40")
        stop_match = re.search(r"Stop\s*Loss:\s*\$?([\d.]+)", content, re.IGNORECASE)
        if stop_match:
            self.stop_loss = float(stop_match.group(1))

        # Position Size (e.g., "Position Size: 2%")
        size_match = re.search(r"(?:Position\s*)?Size:\s*([\d.]+)%?", content, re.IGNORECASE)
        if size_match:
            self.position_size = float(size_match.group(1)) / 100

        # Expiry (e.g., "Expiry: 2025-12-01")
        expiry_match = re.search(r"Expiry:\s*([\d-]+)", content, re.IGNORECASE)
        if expiry_match:
            self.expiry = expiry_match.group(1)

    def get_full_content(self) -> str:
        """Get concatenated content from all messages."""
        return "\n\n".join(m.content for m in self.messages)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for template rendering."""
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "forum_id": self.forum_id,
            "forum_name": self.forum_name,
            "thread_name": self.thread_name,
            "created_at": self.created_at,
            "message_count": self.message_count,
            "messages": [
                {"content": m.content, "timestamp": m.timestamp, "ai": m.ai}
                for m in self.messages
            ],
            "full_content": self.get_full_content(),
            "ticker": self.ticker,
            "direction": self.direction,
            "strike": self.strike,
            "entry_price": self.entry_price,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "expiry": self.expiry,
            "confidence": self.confidence,
            "position_size": self.position_size,
        }

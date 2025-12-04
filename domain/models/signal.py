"""Signal domain model."""

import re
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
    tickers_raw: Optional[str] = None  # Original ticker string if multiple/unparseable
    direction: Optional[str] = None  # BUY/SELL, CALL/PUT
    strike: Optional[float] = None
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    expiry: Optional[str] = None
    confidence: Optional[float] = None
    position_size: Optional[float] = None

    # Known invalid "ticker" words that appear in thread names
    INVALID_TICKER_WORDS = {
        'EXPLOSIVE', 'WSB', 'YOLO', 'HODL', 'MOON', 'APE',
        'STONK', 'STONKS', 'ALERT', 'SIGNAL', 'BUY', 'SELL',
        'CALL', 'PUT', 'OPTIONS', 'TRADING', 'STOCK', 'STOCKS',
        'UPDATE', 'NEWS', 'BREAKING', 'URGENT', 'HOT', 'NEW',
        'QUANTSIGNALS', 'KATY', 'PREDICTION', 'ANALYSIS',
        'AI', 'BOT', 'FREE', 'PREMIUM', 'VIP', 'DAILY', 'WEEKLY',
    }

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

    def _is_valid_ticker(self, ticker: str) -> bool:
        """Check if a string looks like a valid stock ticker.

        Args:
            ticker: Potential ticker string

        Returns:
            True if it looks like a valid ticker
        """
        if not ticker:
            return False

        # Clean the ticker
        ticker = ticker.strip().upper()

        # Must be alphabetic (no numbers, special chars)
        if not ticker.isalpha():
            return False

        # Must be 1-5 characters (standard US tickers)
        # Allow up to 6 for some special cases like GOOGL
        if len(ticker) < 1 or len(ticker) > 6:
            return False

        # Check against blacklist of common non-ticker words
        if ticker in self.INVALID_TICKER_WORDS:
            return False

        return True

    def _extract_ticker_from_thread_name(self) -> Optional[str]:
        """Extract valid ticker from thread name.

        Handles formats like:
        - "SPY 2025-11-30"
        - "SPY,QQQ,IWM QuantSignals..."
        - "NVDA Analysis..."
        - "$SPY Alert"

        Returns:
            Valid ticker or None
        """
        if not self.thread_name:
            return None

        # Split by whitespace
        parts = self.thread_name.split()

        for part in parts:
            # Clean the part
            raw = part.upper().strip()

            # Remove leading $ if present
            if raw.startswith('$'):
                raw = raw[1:]

            # Handle comma-separated tickers - take the first one
            if ',' in raw:
                candidates = raw.split(',')
                for candidate in candidates:
                    candidate = candidate.strip().rstrip(",.:;!?")
                    if self._is_valid_ticker(candidate):
                        return candidate
            else:
                # Remove trailing punctuation
                raw = raw.rstrip(",.:;!?")
                if self._is_valid_ticker(raw):
                    return raw

        return None

    def _extract_ticker_from_content(self) -> Optional[str]:
        """Try to extract ticker from message content.

        Returns:
            Valid ticker or None
        """
        if not self.messages:
            return None

        full_content = "\n".join(m.content for m in self.messages)

        # Look for common patterns like "Ticker: SPY" or "Symbol: NVDA"
        patterns = [
            r'(?:ticker|symbol)\s*[:\-=]\s*\$?([A-Z]{1,6})\b',
            r'\$([A-Z]{1,6})\b',  # $SPY format
            r'(?:analyzing|analysis of)\s+\$?([A-Z]{1,6})\b',
        ]

        for pattern in patterns:
            match = re.search(pattern, full_content, re.IGNORECASE)
            if match:
                candidate = match.group(1).upper()
                if self._is_valid_ticker(candidate):
                    return candidate

        return None

    def _get_raw_ticker_string(self) -> Optional[str]:
        """Get raw ticker string from thread name for LLM fallback.

        Returns:
            Raw ticker portion of thread name
        """
        if not self.thread_name:
            return None

        # Get the first "word" which might contain tickers
        parts = self.thread_name.split()
        if parts:
            raw = parts[0].strip()
            # If it looks like it could contain ticker info
            if any(c.isalpha() for c in raw):
                return raw

        return None

    def _extract_first_plausible_ticker(self, raw: str) -> Optional[str]:
        """Try to extract first plausible ticker from raw string.

        Args:
            raw: Raw ticker string (e.g., "SPY,QQQ,NVDA")

        Returns:
            First valid ticker or None
        """
        # Split by common separators
        for sep in [',', '/', '|', ' ', '-']:
            if sep in raw:
                parts = raw.split(sep)
                for part in parts:
                    cleaned = part.strip().upper().lstrip('$')
                    # Remove trailing punctuation
                    cleaned = re.sub(r'[^A-Z]$', '', cleaned)
                    if cleaned and self._is_valid_ticker(cleaned):
                        return cleaned

        # No separator, try cleaning the whole thing
        cleaned = raw.strip().upper().lstrip('$')
        cleaned = re.sub(r'[^A-Z]', '', cleaned)
        if cleaned and len(cleaned) <= 6 and self._is_valid_ticker(cleaned):
            return cleaned

        return None

    def _parse_signal_content(self) -> None:
        """Parse signal content from messages."""
        if not self.messages:
            return

        full_content = "\n".join(m.content for m in self.messages)

        # Extract ticker - try multiple strategies
        # Strategy 1: Try to get a clean single ticker from thread name
        self.ticker = self._extract_ticker_from_thread_name()

        # Strategy 2: If no clean ticker, try from content
        if not self.ticker:
            self.ticker = self._extract_ticker_from_content()

        # Strategy 3: If still nothing clean, save raw for LLM to figure out
        if not self.ticker:
            raw = self._get_raw_ticker_string()
            if raw:
                self.tickers_raw = raw
                # Try to get at least the first plausible ticker
                self.ticker = self._extract_first_plausible_ticker(raw)

        # Extract direction
        content_upper = full_content.upper()
        if "BUY CALLS" in content_upper or "DIRECTION: CALL" in content_upper:
            self.direction = "CALL"
        elif "BUY PUTS" in content_upper or "DIRECTION: PUT" in content_upper:
            self.direction = "PUT"
        elif "SHORT" in content_upper and "SELL" in content_upper:
            self.direction = "SELL"
        elif "LONG" in content_upper or "BUY" in content_upper:
            self.direction = "BUY"

        # Extract numeric values using simple parsing
        self._extract_numeric_values(full_content)

    def _extract_numeric_values(self, content: str) -> None:
        """Extract numeric values from content."""
        # Confidence (e.g., "Confidence: 65%")
        confidence_match = re.search(r"Confidence:\s*(\d+(?:\.\d+)?)%?", content, re.IGNORECASE)
        if confidence_match:
            val = float(confidence_match.group(1))
            self.confidence = val / 100 if val > 1 else val

        # Strike (e.g., "Strike: $683.00" or "Strike Focus: $683.00")
        strike_match = re.search(r"Strike(?:\s*Focus)?:\s*\$?([\d.]+)", content, re.IGNORECASE)
        if strike_match:
            self.strike = float(strike_match.group(1))

        # Entry Price (e.g., "Entry Price: $1.77" or "Entry Range: $1.77" or "Entry: $182.30")
        entry_match = re.search(r"Entry(?:\s*(?:Price|Range))?:\s*\$?([\d.]+)", content, re.IGNORECASE)
        if entry_match:
            self.entry_price = float(entry_match.group(1))

        # Target (e.g., "Target 1: $2.10" or "Profit Target: $2.10" or "Target: $180.92")
        target_match = re.search(r"(?:Target\s*(?:1)?|Profit\s*Target):\s*\$?([\d.]+)", content, re.IGNORECASE)
        if target_match:
            self.target_price = float(target_match.group(1))

        # Stop Loss (e.g., "Stop Loss: $1.40" or "Stop: $185.03")
        stop_match = re.search(r"Stop(?:\s*Loss)?:\s*\$?([\d.]+)", content, re.IGNORECASE)
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
            "tickers_raw": self.tickers_raw,  # Original if multiple/unparseable
            "direction": self.direction,
            "strike": self.strike,
            "entry_price": self.entry_price,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "expiry": self.expiry,
            "confidence": self.confidence,
            "position_size": self.position_size,
        }
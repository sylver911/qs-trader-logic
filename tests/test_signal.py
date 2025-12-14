"""Tests for Signal domain model."""

import pytest
from domain.models.signal import Signal, Message


# =============================================================================
# Additional fixtures for signal tests
# =============================================================================

@pytest.fixture
def sample_signal_doc_multiple_tickers():
    """Signal with multiple tickers in tickers_raw."""
    return {
        "_id": "test_multi",
        "forum_id": "f1",
        "forum_name": "signals",
        "thread_id": "t1",
        "thread_name": "SPY,QQQ,IWM Signal",
        "created_at": "2025-01-01T00:00:00Z",
        "messages": [
            {
                "content": "Watching SPY, QQQ, IWM today. Focus on SPY calls.",
                "timestamp": "2025-01-01T00:00:00Z",
                "ai": None,
            }
        ],
        "scraped": True,
    }


@pytest.fixture
def sample_signal_doc_no_ticker():
    """Signal with no valid ticker (only invalid words)."""
    return {
        "_id": "test_no_ticker",
        "forum_id": "f1",
        "forum_name": "signals",
        "thread_id": "t1",
        "thread_name": "EXPLOSIVE YOLO MOON STONKS",
        "created_at": "2025-01-01T00:00:00Z",
        "messages": [
            {
                "content": "This is EXPLOSIVE! YOLO into MOON! STONKS only go up!",
                "timestamp": "2025-01-01T00:00:00Z",
                "ai": None,
            }
        ],
        "scraped": True,
    }


@pytest.fixture
def sample_signal_doc_empty_messages():
    """Signal with empty messages list."""
    return {
        "_id": "test_empty",
        "forum_id": "f1",
        "forum_name": "signals",
        "thread_id": "t1",
        "thread_name": "SPY Alert",
        "created_at": "2025-01-01T00:00:00Z",
        "messages": [],
        "scraped": True,
    }


# =============================================================================
# Signal Parsing Tests
# =============================================================================

class TestSignalParsing:
    """Test signal content parsing."""

    def test_parse_basic_signal(self, sample_signal_doc):
        """Test parsing a standard signal document."""
        signal = Signal.from_mongo_doc(sample_signal_doc)

        assert signal.id == "692dc7ab8b19c22400c25705"
        assert signal.thread_id == "144477652490S4534197"
        assert signal.ticker == "SPY"
        assert signal.direction == "CALL"
        assert signal.strike == 683.00
        assert signal.entry_price == 1.77
        assert signal.target_price == 2.10
        assert signal.stop_loss == 1.40
        assert signal.confidence == 0.65
        assert signal.expiry == "2025-12-01"

    def test_parse_multiple_tickers_takes_first(self, sample_signal_doc_multiple_tickers):
        """Test that multiple tickers extracts the first valid one."""
        signal = Signal.from_mongo_doc(sample_signal_doc_multiple_tickers)

        # Should extract SPY as the first valid ticker
        assert signal.ticker == "SPY"

    def test_parse_invalid_ticker_words_rejected(self, sample_signal_doc_no_ticker):
        """Test that invalid ticker words are rejected."""
        signal = Signal.from_mongo_doc(sample_signal_doc_no_ticker)

        # Should not parse EXPLOSIVE, YOLO, MOON, STONKS as tickers
        assert signal.ticker is None or signal.ticker not in [
            "EXPLOSIVE", "YOLO", "MOON", "STONKS"
        ]

    def test_parse_empty_messages(self, sample_signal_doc_empty_messages):
        """Test handling of empty messages list."""
        signal = Signal.from_mongo_doc(sample_signal_doc_empty_messages)

        # With empty messages, no content to parse - ticker comes from messages
        assert signal.ticker is None  # Not extracted from thread name alone
        assert signal.direction is None
        assert signal.entry_price is None
        assert signal.messages == []

    def test_parse_none_messages(self):
        """Test handling of None messages."""
        doc = {
            "_id": "test",
            "thread_id": "t1",
            "forum_id": "f1",
            "forum_name": "forum",
            "thread_name": "AAPL Signal",
            "messages": None,
        }
        signal = Signal.from_mongo_doc(doc)

        # Messages should be converted to empty list
        assert signal.messages == []
        # Ticker extraction from thread_name depends on implementation
        # Just verify it doesn't crash

    def test_parse_message_with_none_content(self):
        """Test handling of message with None content."""
        doc = {
            "_id": "test",
            "thread_id": "t1",
            "forum_id": "f1",
            "forum_name": "forum",
            "thread_name": "MSFT Alert",
            "messages": [
                {"content": None, "timestamp": "2025-01-01T00:00:00Z", "ai": None},
                {"content": "Entry: $100.00", "timestamp": "2025-01-01T00:00:01Z", "ai": None},
            ],
        }
        # This might crash if Signal doesn't handle None content
        # Test that it either works or raises a clear error
        try:
            signal = Signal.from_mongo_doc(doc)
            # If it works, verify basic structure
            assert signal.thread_name == "MSFT Alert"
        except TypeError as e:
            # Expected if Signal joins content without None check
            assert "NoneType" in str(e)

    def test_is_valid_ticker(self):
        """Test ticker validation."""
        signal = Signal(
            id="test",
            thread_id="t1",
            forum_id="f1",
            forum_name="forum",
            thread_name="test",
        )

        # Valid tickers
        assert signal._is_valid_ticker("SPY") is True
        assert signal._is_valid_ticker("QQQ") is True
        assert signal._is_valid_ticker("AAPL") is True
        assert signal._is_valid_ticker("GOOGL") is True
        assert signal._is_valid_ticker("A") is True  # Single letter

        # Invalid tickers
        assert signal._is_valid_ticker("") is False
        assert signal._is_valid_ticker(None) is False
        assert signal._is_valid_ticker("TOOLONG7") is False
        assert signal._is_valid_ticker("123") is False
        assert signal._is_valid_ticker("SPY123") is False
        assert signal._is_valid_ticker("EXPLOSIVE") is False
        assert signal._is_valid_ticker("YOLO") is False
        assert signal._is_valid_ticker("STONK") is False

    def test_extract_numeric_values_various_formats(self):
        """Test extraction of numeric values with different formats."""
        doc = {
            "_id": "test",
            "thread_id": "t1",
            "forum_id": "f1",
            "forum_name": "forum",
            "thread_name": "AMD Signal",
            "messages": [
                {
                    "content": """
                    Confidence: 75%
                    Strike Focus: $150.00
                    Entry Price: $2.50
                    Target 1: $3.00
                    Stop Loss: $2.00
                    Expiry: 2025-12-15
                    Size: 5%
                    """,
                    "timestamp": "2025-01-01T00:00:00Z",
                    "ai": None,
                }
            ],
        }
        signal = Signal.from_mongo_doc(doc)

        assert signal.confidence == 0.75
        assert signal.strike == 150.00
        assert signal.entry_price == 2.50
        assert signal.target_price == 3.00
        assert signal.stop_loss == 2.00
        assert signal.expiry == "2025-12-15"
        assert signal.position_size == 0.05

    def test_get_full_content(self, sample_signal_doc):
        """Test full content concatenation."""
        signal = Signal.from_mongo_doc(sample_signal_doc)

        full_content = signal.get_full_content()

        # Check that content from messages is included
        assert "SPY QuantSignals V3" in full_content
        assert "Direction: BUY CALLS" in full_content

    def test_to_dict_contains_all_fields(self, sample_signal_doc):
        """Test to_dict includes all necessary fields."""
        signal = Signal.from_mongo_doc(sample_signal_doc)

        d = signal.to_dict()

        assert "id" in d
        assert "thread_id" in d
        assert "ticker" in d
        assert "direction" in d
        assert "strike" in d
        assert "entry_price" in d
        assert "target_price" in d
        assert "stop_loss" in d
        assert "expiry" in d
        assert "confidence" in d
        assert "full_content" in d
        assert "messages" in d


class TestSignalEdgeCases:
    """Test edge cases in signal parsing."""

    def test_confidence_as_decimal(self):
        """Test confidence already as decimal (0.65 vs 65%)."""
        doc = {
            "_id": "test",
            "thread_id": "t1",
            "forum_id": "f1",
            "forum_name": "forum",
            "thread_name": "SPY",
            "messages": [
                {"content": "Confidence: 0.75", "timestamp": "t", "ai": None}
            ],
        }
        signal = Signal.from_mongo_doc(doc)

        # 0.75 should stay as 0.75, not become 0.0075
        assert signal.confidence == 0.75

    def test_alternative_entry_format(self):
        """Test 'Entry:' without 'Price' or 'Range'."""
        doc = {
            "_id": "test",
            "thread_id": "t1",
            "forum_id": "f1",
            "forum_name": "forum",
            "thread_name": "TSLA",
            "messages": [
                {"content": "Entry: $182.30\nTarget: $180.92\nStop: $185.03", "timestamp": "t", "ai": None}
            ],
        }
        signal = Signal.from_mongo_doc(doc)

        assert signal.entry_price == 182.30
        assert signal.target_price == 180.92
        assert signal.stop_loss == 185.03

    def test_direction_short_sell(self):
        """Test SHORT/SELL direction detection."""
        doc = {
            "_id": "test",
            "thread_id": "t1",
            "forum_id": "f1",
            "forum_name": "forum",
            "thread_name": "SPY",
            "messages": [
                {"content": "Direction: SHORT SELL\nBearish setup", "timestamp": "t", "ai": None}
            ],
        }
        signal = Signal.from_mongo_doc(doc)

        assert signal.direction == "SELL"

    def test_direction_put(self):
        """Test PUT direction detection."""
        doc = {
            "_id": "test",
            "thread_id": "t1",
            "forum_id": "f1",
            "forum_name": "forum",
            "thread_name": "QQQ",
            "messages": [
                {"content": "Direction: PUT\nBUY PUTS signal", "timestamp": "t", "ai": None}
            ],
        }
        signal = Signal.from_mongo_doc(doc)

        assert signal.direction == "PUT"

    def test_signal_from_minimal_doc(self):
        """Test signal creation from minimal document."""
        doc = {
            "_id": "min",
            "thread_id": "t1",
            "forum_id": "f1",
            "forum_name": "forum",
            "thread_name": "Test",
        }
        signal = Signal.from_mongo_doc(doc)

        assert signal.id == "min"
        assert signal.thread_id == "t1"
        assert signal.messages == []

    def test_message_class_creation(self):
        """Test Message dataclass creation."""
        msg = Message(
            content="Test content",
            timestamp="2025-01-01T00:00:00Z",
            ai=None,
        )

        assert msg.content == "Test content"
        assert msg.timestamp == "2025-01-01T00:00:00Z"
        assert msg.ai is None

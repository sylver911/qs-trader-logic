"""Tests for Trading Service - QS Optimized."""

import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from domain.models.signal import Signal
from domain.models.trade import TradeAction, TradeDecision


class TestTradingServiceValidation:
    """Test pre-condition validation."""

    @patch("domain.services.trading_service.trading_config")
    def test_emergency_stop_blocks_trading(self, mock_config):
        """Emergency stop blocks all trading."""
        mock_config.emergency_stop = True

        from domain.services.trading_service import TradingService
        service = TradingService()
        
        signal = Signal(
            id="test", thread_id="t1", forum_id="f1",
            forum_name="forum", thread_name="SPY Signal", ticker="SPY"
        )

        result = service._validate_preconditions(signal)
        assert result is not None
        assert "emergency stop" in result.lower()

    @patch("domain.services.trading_service.trading_config")
    def test_whitelist_blocks_non_whitelisted(self, mock_config):
        """Whitelist blocks non-whitelisted tickers."""
        mock_config.emergency_stop = False
        mock_config.whitelist_tickers = ["SPY", "QQQ"]
        mock_config.blacklist_tickers = []
        mock_config.min_ai_confidence_score = 0.5
        mock_config.execute_orders = False

        from domain.services.trading_service import TradingService
        service = TradingService()
        
        signal = Signal(
            id="test", thread_id="t1", forum_id="f1",
            forum_name="forum", thread_name="AAPL Signal", ticker="AAPL"
        )

        result = service._validate_preconditions(signal)
        assert result is not None
        assert "whitelist" in result.lower()

    @patch("domain.services.trading_service.trading_config")
    def test_blacklist_blocks_blacklisted(self, mock_config):
        """Blacklist blocks blacklisted tickers."""
        mock_config.emergency_stop = False
        mock_config.whitelist_tickers = []
        mock_config.blacklist_tickers = ["GME", "AMC"]
        mock_config.min_ai_confidence_score = 0.5
        mock_config.execute_orders = False

        from domain.services.trading_service import TradingService
        service = TradingService()
        
        signal = Signal(
            id="test", thread_id="t1", forum_id="f1",
            forum_name="forum", thread_name="GME YOLO", ticker="GME"
        )

        result = service._validate_preconditions(signal)
        assert result is not None
        assert "blacklist" in result.lower()


class TestParseDecision:
    """Test AI decision parsing."""

    def test_parse_execute_with_bracket(self):
        """Parse execute decision with bracket parameters."""
        from domain.services.trading_service import TradingService
        service = TradingService()

        content = """{
            "action": "execute",
            "reasoning": "Good R:R of 2.1:1",
            "confidence": 0.75,
            "risk_reward_ratio": 2.1,
            "bracket": {
                "entry_price": 1.85,
                "take_profit": 2.50,
                "stop_loss": 1.40,
                "quantity": 2
            }
        }"""

        decision = service._parse_decision(content)

        assert decision.action == TradeAction.EXECUTE
        assert decision.confidence == 0.75
        assert decision.modified_entry == 1.85
        assert decision.modified_target == 2.50
        assert decision.modified_stop_loss == 1.40
        assert decision.modified_size == 2

    def test_parse_skip_with_null_bracket(self):
        """Parse skip decision with null bracket."""
        from domain.services.trading_service import TradingService
        service = TradingService()

        content = """{
            "action": "skip",
            "reasoning": "Market is closed",
            "confidence": 0.95,
            "risk_reward_ratio": null,
            "bracket": null
        }"""

        decision = service._parse_decision(content)

        assert decision.action == TradeAction.SKIP
        assert decision.modified_entry is None
        assert decision.skip_reason == "Market is closed"

    def test_parse_decision_with_extra_text(self):
        """Parse decision surrounded by text."""
        from domain.services.trading_service import TradingService
        service = TradingService()

        content = """Based on my analysis:
        {
            "action": "execute",
            "reasoning": "Good setup",
            "confidence": 0.8,
            "bracket": {"entry_price": 1.90, "take_profit": 2.40, "stop_loss": 1.50, "quantity": 1}
        }
        Proceeding with caution."""

        decision = service._parse_decision(content)
        assert decision.action == TradeAction.EXECUTE

    def test_parse_invalid_json_returns_skip(self):
        """Invalid JSON returns skip decision."""
        from domain.services.trading_service import TradingService
        service = TradingService()

        decision = service._parse_decision("This is not valid JSON")

        assert decision.action == TradeAction.SKIP
        assert "parse" in decision.skip_reason.lower()


class TestJsonSerializer:
    """Test JSON serializer."""

    def test_serialize_pandas_timestamp(self):
        """Serialize pandas Timestamp."""
        import pandas as pd
        from domain.services.trading_service import json_serializer

        ts = pd.Timestamp("2024-12-03 10:30:00")
        result = json_serializer(ts)

        assert isinstance(result, str)
        assert "2024-12-03" in result

    def test_serialize_datetime(self):
        """Serialize datetime."""
        from domain.services.trading_service import json_serializer

        dt = datetime(2024, 12, 3, 10, 30, 0)
        result = json_serializer(dt)

        assert isinstance(result, str)
        assert "2024-12-03" in result


class TestIsValidTicker:
    """Test ticker validation."""

    def test_valid_tickers(self):
        """Valid ticker symbols."""
        from domain.services.trading_service import TradingService
        service = TradingService()

        assert service._is_valid_ticker("SPY") is True
        assert service._is_valid_ticker("QQQ") is True
        assert service._is_valid_ticker("AAPL") is True

    def test_invalid_tickers(self):
        """Invalid ticker symbols."""
        from domain.services.trading_service import TradingService
        service = TradingService()

        assert service._is_valid_ticker("") is False
        assert service._is_valid_ticker(None) is False
        assert service._is_valid_ticker("EXPLOSIVE") is False
        assert service._is_valid_ticker("YOLO") is False

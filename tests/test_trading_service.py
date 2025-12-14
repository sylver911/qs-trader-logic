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

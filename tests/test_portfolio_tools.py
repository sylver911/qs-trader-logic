"""Tests for Portfolio Tools - QS Optimized."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from tools.portfolio_tools import PortfolioTools


class TestPortfolioTools:
    """Test PortfolioTools class."""

    def test_get_tool_definitions(self):
        """Tool definitions should be valid."""
        tools = PortfolioTools.get_tool_definitions()
        
        assert isinstance(tools, list)
        assert len(tools) == 2
        
        tool_names = {t["function"]["name"] for t in tools}
        assert "get_account_summary" in tool_names
        assert "get_positions" in tool_names

    def test_get_handlers(self):
        """Handlers should match tool definitions."""
        mock_broker = MagicMock()
        tools = PortfolioTools(broker=mock_broker)
        handlers = tools.get_handlers()
        
        assert "get_account_summary" in handlers
        assert "get_positions" in handlers
        
        for name, handler in handlers.items():
            assert callable(handler)

    def test_get_account_summary_usd(self):
        """get_account_summary extracts USD values."""
        mock_broker = MagicMock()
        mock_broker.get_account_summary.return_value = {
            "accountId": "DU1234567",
            "totalcashvalue-s": {"amount": 5000.0, "currency": "USD"},
            "buyingpower": {"amount": 10000.0, "currency": "USD"},
            "netliquidation": {"amount": 15000.0, "currency": "USD"},
        }
        
        tools = PortfolioTools(broker=mock_broker)
        result = tools.get_account_summary()
        
        assert result["usd_available_for_trading"] == 5000.0
        assert result["usd_buying_power"] == 10000.0
        assert result["currency"] == "USD"

    def test_get_account_summary_low_balance_warning(self):
        """Low balance triggers warning."""
        mock_broker = MagicMock()
        mock_broker.get_account_summary.return_value = {
            "totalcashvalue-s": {"amount": 100.0, "currency": "USD"},
        }
        
        tools = PortfolioTools(broker=mock_broker)
        result = tools.get_account_summary()
        
        assert "warning" in result
        assert "Low" in result["warning"]

    def test_get_positions_empty(self):
        """get_positions with no positions."""
        mock_broker = MagicMock()
        mock_broker.get_positions.return_value = []
        
        tools = PortfolioTools(broker=mock_broker)
        result = tools.get_positions()
        
        assert result["count"] == 0
        assert result["positions"] == []
        assert result["tickers"] == []

    def test_get_positions_with_data(self):
        """get_positions with actual positions."""
        mock_broker = MagicMock()
        mock_broker.get_positions.return_value = [
            {
                "conid": "265598",
                "contractDesc": "SPY",
                "ticker": "SPY",
                "position": 10,
                "avgCost": 450.50,
                "mktValue": 4550.00,
                "unrealizedPnl": 45.00,
            },
            {
                "conid": "265599",
                "contractDesc": "QQQ",
                "ticker": "QQQ",
                "position": 5,
                "avgCost": 400.00,
                "mktValue": 2050.00,
                "unrealizedPnl": 50.00,
            },
        ]
        
        tools = PortfolioTools(broker=mock_broker)
        result = tools.get_positions()
        
        assert result["count"] == 2
        assert len(result["positions"]) == 2
        assert "SPY" in result["tickers"]
        assert "QQQ" in result["tickers"]

    def test_get_account_summary_error(self):
        """get_account_summary handles errors."""
        mock_broker = MagicMock()
        mock_broker.get_account_summary.return_value = None
        
        tools = PortfolioTools(broker=mock_broker)
        result = tools.get_account_summary()
        
        assert "error" in result

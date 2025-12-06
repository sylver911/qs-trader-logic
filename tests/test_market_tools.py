"""Tests for Market Tools - QS Optimized."""

import pytest
from datetime import datetime, date
from unittest.mock import MagicMock, patch

from tools.market_tools import MarketTools, is_nyse_open, NYSE_HOLIDAYS


class TestNYSEMarketStatus:
    """Test NYSE market status checking."""

    def test_weekend_saturday(self):
        """Saturday should be closed."""
        # 2024-12-07 is Saturday
        dt = datetime(2024, 12, 7, 11, 0, 0)
        result = is_nyse_open(dt)
        
        assert result["is_open"] is False
        assert result["reason"] == "weekend"

    def test_weekend_sunday(self):
        """Sunday should be closed."""
        dt = datetime(2024, 12, 8, 11, 0, 0)
        result = is_nyse_open(dt)
        
        assert result["is_open"] is False
        assert result["reason"] == "weekend"

    def test_regular_hours_open(self):
        """Regular trading hours should be open."""
        # Tuesday at 11:00 AM
        dt = datetime(2024, 12, 3, 11, 0, 0)
        result = is_nyse_open(dt)
        
        assert result["is_open"] is True
        assert result["reason"] == "market_open"

    def test_pre_market(self):
        """Before 9:30 AM should be closed."""
        dt = datetime(2024, 12, 3, 8, 0, 0)
        result = is_nyse_open(dt)
        
        assert result["is_open"] is False
        assert result["reason"] == "pre_market"

    def test_after_hours(self):
        """After 4:00 PM should be closed."""
        dt = datetime(2024, 12, 3, 17, 0, 0)
        result = is_nyse_open(dt)
        
        assert result["is_open"] is False
        assert result["reason"] == "after_hours"

    def test_holiday_thanksgiving_2024(self):
        """Thanksgiving 2024 should be closed."""
        dt = datetime(2024, 11, 28, 11, 0, 0)
        result = is_nyse_open(dt)
        
        assert result["is_open"] is False
        assert result["reason"] == "holiday"

    def test_holiday_christmas_2025(self):
        """Christmas 2025 should be closed."""
        dt = datetime(2025, 12, 25, 11, 0, 0)
        result = is_nyse_open(dt)
        
        assert result["is_open"] is False
        assert result["reason"] == "holiday"


class TestMarketTools:
    """Test MarketTools class."""

    def test_get_tool_definitions(self):
        """Tool definitions should be valid."""
        tools = MarketTools.get_tool_definitions()
        
        assert isinstance(tools, list)
        assert len(tools) >= 4
        
        tool_names = {t["function"]["name"] for t in tools}
        assert "get_current_time" in tool_names
        assert "get_ticker_price" in tool_names
        assert "get_option_chain" in tool_names
        assert "get_vix" in tool_names

    def test_get_handlers(self):
        """Handlers should match tool definitions."""
        tools = MarketTools()
        handlers = tools.get_handlers()
        
        assert "get_current_time" in handlers
        assert "get_ticker_price" in handlers
        assert "get_option_chain" in handlers
        assert "get_vix" in handlers
        
        for name, handler in handlers.items():
            assert callable(handler)

    @patch("tools.market_tools.datetime")
    def test_get_current_time_structure(self, mock_datetime):
        """get_current_time returns proper structure."""
        # Mock datetime.now to return a known time
        import pytz
        est = pytz.timezone("US/Eastern")
        mock_now = datetime(2024, 12, 3, 11, 30, 0, tzinfo=est)
        mock_datetime.now.return_value = mock_now
        
        tools = MarketTools()
        result = tools.get_current_time()
        
        assert "timestamp" in result
        assert "time_est" in result
        assert "date" in result
        assert "is_market_open" in result
        assert "market_status" in result

    def test_get_ticker_price_structure(self):
        """get_ticker_price returns proper structure."""
        mock_market_data = MagicMock()
        mock_market_data.get_current_price.return_value = 605.50
        
        tools = MarketTools(market_data=mock_market_data)
        result = tools.get_ticker_price("SPY")
        
        assert result["symbol"] == "SPY"
        assert result["price"] == 605.50
        assert result["currency"] == "USD"
        assert "timestamp" in result

    def test_get_vix_structure(self):
        """get_vix returns proper structure."""
        mock_market_data = MagicMock()
        mock_market_data.get_vix.return_value = 18.5
        
        tools = MarketTools(market_data=mock_market_data)
        result = tools.get_vix()
        
        assert result["vix"] == 18.5
        assert "timestamp" in result

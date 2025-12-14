"""Tests for Order Tools - QS Optimized."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from tools.order_tools import OrderTools


class TestOrderTools:
    """Test OrderTools class."""

    def test_get_tool_definitions(self):
        """Tool definitions should be valid."""
        tools = OrderTools.get_tool_definitions()

        assert isinstance(tools, list)
        assert len(tools) == 2  # bracket order + skip_signal

        tool_names = {t["function"]["name"] for t in tools}
        assert "place_bracket_order" in tool_names
        assert "skip_signal" in tool_names

        # Check bracket order params - new API with separate option fields
        bracket_tool = next(t for t in tools if t["function"]["name"] == "place_bracket_order")
        params = bracket_tool["function"]["parameters"]["properties"]
        assert "ticker" in params
        assert "expiry" in params
        assert "strike" in params
        assert "direction" in params
        assert "side" in params
        assert "quantity" in params
        assert "entry_price" in params
        assert "take_profit" in params
        assert "stop_loss" in params

    def test_get_handlers(self):
        """Handlers should match tool definitions."""
        mock_broker = MagicMock()
        tools = OrderTools(broker=mock_broker)
        handlers = tools.get_handlers()

        assert "place_bracket_order" in handlers
        assert "skip_signal" in handlers
        assert callable(handlers["place_bracket_order"])
        assert callable(handlers["skip_signal"])

    def test_skip_signal_basic(self):
        """Skip signal should return proper structure."""
        mock_broker = MagicMock()
        tools = OrderTools(broker=mock_broker)

        result = tools.skip_signal(
            reason="Market is closed",
            category="market_closed"
        )

        assert result["action"] == "skip"
        assert result["reason"] == "Market is closed"
        assert result["category"] == "market_closed"
        assert "timestamp" in result


class TestOptionSymbolParsing:
    """Test option symbol parsing."""

    def test_parse_spy_call(self):
        """Parse SPY call option."""
        tools = OrderTools(broker=MagicMock())

        result = tools._parse_option_symbol("SPY 241209C00605000")

        assert result is not None
        assert result["ticker"] == "SPY"
        assert result["expiry_month"] == "DEC24"
        assert result["strike"] == 605.0
        assert result["right"] == "C"

    def test_parse_spy_put(self):
        """Parse SPY put option."""
        tools = OrderTools(broker=MagicMock())

        result = tools._parse_option_symbol("SPY 241209P00600000")

        assert result is not None
        assert result["ticker"] == "SPY"
        assert result["expiry_month"] == "DEC24"
        assert result["strike"] == 600.0
        assert result["right"] == "P"

    def test_parse_no_space(self):
        """Parse symbol without space."""
        tools = OrderTools(broker=MagicMock())

        result = tools._parse_option_symbol("SPY241209C00605000")

        assert result is not None
        assert result["ticker"] == "SPY"
        assert result["strike"] == 605.0

    def test_parse_fractional_strike(self):
        """Parse option with fractional strike."""
        tools = OrderTools(broker=MagicMock())

        # Strike 605.50 = 00605500
        result = tools._parse_option_symbol("SPY 241209C00605500")

        assert result is not None
        assert result["strike"] == 605.5

    def test_parse_tsla_option(self):
        """Parse TSLA option."""
        tools = OrderTools(broker=MagicMock())

        result = tools._parse_option_symbol("TSLA 241220C00400000")

        assert result is not None
        assert result["ticker"] == "TSLA"
        assert result["expiry_month"] == "DEC24"
        assert result["strike"] == 400.0
        assert result["right"] == "C"

    def test_parse_qqq_option(self):
        """Parse QQQ option."""
        tools = OrderTools(broker=MagicMock())

        result = tools._parse_option_symbol("QQQ 250117P00500000")

        assert result is not None
        assert result["ticker"] == "QQQ"
        assert result["expiry_month"] == "JAN25"
        assert result["strike"] == 500.0
        assert result["right"] == "P"

    def test_parse_invalid_symbol(self):
        """Invalid symbols should return None."""
        tools = OrderTools(broker=MagicMock())

        # Invalid formats
        assert tools._parse_option_symbol("SPY") is None
        assert tools._parse_option_symbol("INVALID") is None
        assert tools._parse_option_symbol("SPY 241209X00605000") is None  # Invalid right


class TestBuildOccSymbol:
    """Test OCC symbol building."""

    def test_build_call_symbol(self):
        """Build SPY call symbol."""
        tools = OrderTools(broker=MagicMock())

        symbol = tools._build_occ_symbol(
            ticker="SPY",
            expiry="2024-12-09",
            strike=605.0,
            direction="CALL"
        )

        assert symbol == "SPY 241209C00605000"

    def test_build_put_symbol(self):
        """Build SPY put symbol."""
        tools = OrderTools(broker=MagicMock())

        symbol = tools._build_occ_symbol(
            ticker="SPY",
            expiry="2024-12-09",
            strike=600.0,
            direction="PUT"
        )

        assert symbol == "SPY 241209P00600000"

    def test_build_fractional_strike(self):
        """Build symbol with fractional strike."""
        tools = OrderTools(broker=MagicMock())

        symbol = tools._build_occ_symbol(
            ticker="SPY",
            expiry="2024-12-09",
            strike=605.5,
            direction="CALL"
        )

        assert symbol == "SPY 241209C00605500"


class TestBracketOrderPlacement:
    """Test bracket order placement with new API."""

    def test_place_option_bracket_order_success(self):
        """Successful option bracket order placement."""
        mock_broker = MagicMock()
        mock_client = MagicMock()

        # Mock underlying lookup
        mock_broker.search_contract.return_value = {"conid": "756733"}
        mock_broker._get_client.return_value = mock_client

        # Mock option contract lookup
        mock_client.search_secdef_info_by_conid.return_value = MagicMock(
            data=[{"conid": "123456789"}]
        )

        # Mock order placement
        mock_broker.place_bracket_order.return_value = [{"order_id": "ORD123"}]

        tools = OrderTools(broker=mock_broker)
        result = tools.place_bracket_order(
            ticker="SPY",
            expiry="2024-12-09",
            strike=605.0,
            direction="CALL",
            side="BUY",
            quantity=2,
            entry_price=1.85,
            take_profit=2.50,
            stop_loss=1.40,
        )

        assert result["success"] is True
        assert result["conid"] == "123456789"
        assert result["symbol"] == "SPY 241209C00605000"
        assert result["order_type"] == "BRACKET"
        assert result["product"]["ticker"] == "SPY"
        assert result["product"]["expiry"] == "2024-12-09"
        assert result["product"]["strike"] == 605.0
        assert result["product"]["direction"] == "CALL"

    def test_place_bracket_order_underlying_not_found(self):
        """Bracket order fails when underlying not found."""
        mock_broker = MagicMock()
        mock_broker.search_contract.return_value = None

        tools = OrderTools(broker=mock_broker)
        result = tools.place_bracket_order(
            ticker="FAKE",
            expiry="2024-12-09",
            strike=100.0,
            direction="CALL",
            side="BUY",
            quantity=1,
            entry_price=1.00,
            take_profit=1.50,
            stop_loss=0.80,
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_place_bracket_order_option_not_found(self):
        """Bracket order fails when option contract not found."""
        mock_broker = MagicMock()
        mock_client = MagicMock()

        # Underlying found
        mock_broker.search_contract.return_value = {"conid": "756733"}
        mock_broker._get_client.return_value = mock_client

        # Option NOT found
        mock_client.search_secdef_info_by_conid.return_value = MagicMock(data=[])

        tools = OrderTools(broker=mock_broker)
        result = tools.place_bracket_order(
            ticker="SPY",
            expiry="2024-12-09",
            strike=999.0,  # Invalid strike
            direction="CALL",
            side="BUY",
            quantity=1,
            entry_price=1.00,
            take_profit=1.50,
            stop_loss=0.80,
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_place_bracket_order_broker_failure(self):
        """Bracket order handles broker failure."""
        mock_broker = MagicMock()
        mock_client = MagicMock()

        mock_broker.search_contract.return_value = {"conid": "756733"}
        mock_broker._get_client.return_value = mock_client
        mock_client.search_secdef_info_by_conid.return_value = MagicMock(
            data=[{"conid": "123456789"}]
        )

        # Broker fails to place order
        mock_broker.place_bracket_order.return_value = None

        tools = OrderTools(broker=mock_broker)
        result = tools.place_bracket_order(
            ticker="SPY",
            expiry="2024-12-09",
            strike=605.0,
            direction="CALL",
            side="BUY",
            quantity=1,
            entry_price=1.85,
            take_profit=2.50,
            stop_loss=1.40,
        )

        assert result["success"] is False

    def test_place_put_order(self):
        """Place a PUT option order."""
        mock_broker = MagicMock()
        mock_client = MagicMock()

        mock_broker.search_contract.return_value = {"conid": "756733"}
        mock_broker._get_client.return_value = mock_client
        mock_client.search_secdef_info_by_conid.return_value = MagicMock(
            data=[{"conid": "987654321"}]
        )
        mock_broker.place_bracket_order.return_value = [{"order_id": "ORD456"}]

        tools = OrderTools(broker=mock_broker)
        result = tools.place_bracket_order(
            ticker="SPY",
            expiry="2024-12-09",
            strike=600.0,
            direction="PUT",
            side="BUY",
            quantity=3,
            entry_price=2.00,
            take_profit=3.50,
            stop_loss=1.20,
        )

        assert result["success"] is True
        assert result["symbol"] == "SPY 241209P00600000"
        assert result["product"]["direction"] == "PUT"
        assert result["quantity"] == 3

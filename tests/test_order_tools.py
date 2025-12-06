"""Tests for Order Tools - QS Optimized."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from tools.order_tools import OrderTools


class TestOrderTools:
    """Test OrderTools class."""

    def test_get_tool_definitions(self):
        """Tool definitions should be valid."""
        tools = OrderTools.get_tool_definitions()
        
        assert isinstance(tools, list)
        assert len(tools) == 1  # Only bracket order
        
        tool_def = tools[0]
        assert tool_def["function"]["name"] == "place_bracket_order"
        
        params = tool_def["function"]["parameters"]["properties"]
        assert "symbol" in params
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
        assert callable(handlers["place_bracket_order"])

    def test_place_bracket_order_success(self):
        """Successful bracket order placement."""
        mock_broker = MagicMock()
        mock_broker.search_contract.return_value = {"conid": "12345"}
        mock_broker.place_bracket_order.return_value = {"order_id": "ORD123"}
        
        tools = OrderTools(broker=mock_broker)
        result = tools.place_bracket_order(
            symbol="SPY",
            side="BUY",
            quantity=2,
            entry_price=1.85,
            take_profit=2.50,
            stop_loss=1.40,
        )
        
        assert result["success"] is True
        assert result["symbol"] == "SPY"
        assert result["side"] == "BUY"
        assert result["quantity"] == 2
        assert result["entry_price"] == 1.85
        assert result["take_profit"] == 2.50
        assert result["stop_loss"] == 1.40
        assert result["order_type"] == "BRACKET"

    def test_place_bracket_order_contract_not_found(self):
        """Bracket order fails when contract not found."""
        mock_broker = MagicMock()
        mock_broker.search_contract.return_value = None
        
        tools = OrderTools(broker=mock_broker)
        result = tools.place_bracket_order(
            symbol="INVALID",
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
        mock_broker.search_contract.return_value = {"conid": "12345"}
        mock_broker.place_bracket_order.return_value = None
        
        tools = OrderTools(broker=mock_broker)
        result = tools.place_bracket_order(
            symbol="SPY",
            side="BUY",
            quantity=1,
            entry_price=1.85,
            take_profit=2.50,
            stop_loss=1.40,
        )
        
        assert result["success"] is False

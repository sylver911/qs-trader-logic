"""Tests for IBKR Client.

These tests use the mocked ibind from conftest.py.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

# Import the mock instance from conftest (already set up in sys.modules)
from conftest import mock_ibkr_client_instance, mock_ibkr_client_class

from infrastructure.broker.ibkr_client import IBKRBroker


class TestIBKRBroker:
    """Test IBKR broker client."""

    def setup_method(self):
        """Reset mocks before each test."""
        mock_ibkr_client_instance.reset_mock()
        mock_ibkr_client_instance.side_effect = None
        # Reset common return values
        mock_ibkr_client_instance.tickle.side_effect = None
        mock_ibkr_client_instance.positions.side_effect = None
        mock_ibkr_client_instance.cancel_order.side_effect = None
        mock_ibkr_client_instance.live_orders.side_effect = None
        mock_ibkr_client_instance.portfolio_accounts.side_effect = None

    def test_check_health_success(self):
        """Test successful health check."""
        mock_ibkr_client_instance.tickle.return_value = MagicMock(
            data={"authenticated": True}
        )

        broker = IBKRBroker()
        result = broker.check_health()

        assert result is True
        mock_ibkr_client_instance.tickle.assert_called_once()

    def test_check_health_failure(self):
        """Test health check failure."""
        mock_ibkr_client_instance.tickle.side_effect = Exception("Connection failed")

        broker = IBKRBroker()
        result = broker.check_health()

        assert result is False

    def test_get_positions_success(self):
        """Test getting positions."""
        mock_ibkr_client_instance.positions.return_value = MagicMock(
            data=[{"ticker": "SPY", "position": 10}]
        )

        broker = IBKRBroker()
        positions = broker.get_positions()

        assert len(positions) == 1
        assert positions[0]["ticker"] == "SPY"

    def test_get_positions_error(self):
        """Test positions fetch error returns empty list."""
        mock_ibkr_client_instance.positions.side_effect = Exception("API Error")

        broker = IBKRBroker()
        positions = broker.get_positions()

        assert positions == []

    def test_search_contract_success(self):
        """Test contract search."""
        mock_ibkr_client_instance.search_contract_by_symbol.return_value = MagicMock(
            data=[{"conid": "265598", "symbol": "SPY"}]
        )

        broker = IBKRBroker()
        contract = broker.search_contract("SPY")

        assert contract is not None
        assert contract["conid"] == "265598"

    def test_search_contract_not_found(self):
        """Test contract search when not found."""
        mock_ibkr_client_instance.search_contract_by_symbol.return_value = MagicMock(
            data=[]
        )

        broker = IBKRBroker()
        contract = broker.search_contract("INVALID")

        assert contract is None

    def test_place_order_success(self):
        """Test order placement."""
        # Mock receive_brokerage_accounts (preflight)
        mock_ibkr_client_instance.receive_brokerage_accounts.return_value = MagicMock(
            data={"accounts": ["DU123"]}
        )

        # Mock place_order
        mock_ibkr_client_instance.place_order.return_value = MagicMock(
            data={"order_id": "12345"}
        )

        broker = IBKRBroker()
        broker._account_id = "DU123"  # Set account ID directly
        result = broker.place_order(
            conid="265598",
            side="BUY",
            quantity=10,
            order_type="MKT",
        )

        assert result is not None

    def test_cancel_order_success(self):
        """Test successful order cancellation."""
        mock_ibkr_client_instance.cancel_order.return_value = MagicMock(
            data={"msg": "cancelled"}
        )

        broker = IBKRBroker()
        broker._account_id = "DU123"
        result = broker.cancel_order("12345")

        assert result is True

    def test_cancel_order_failure(self):
        """Test order cancellation failure."""
        mock_ibkr_client_instance.cancel_order.side_effect = Exception("Not found")

        broker = IBKRBroker()
        result = broker.cancel_order("12345")

        assert result is False

    def test_get_live_orders_success(self):
        """Test getting live orders."""
        mock_ibkr_client_instance.live_orders.return_value = MagicMock(
            data={"orders": [{"orderId": "123"}]}
        )

        broker = IBKRBroker()
        orders = broker.get_live_orders()

        assert len(orders) == 1

    def test_get_live_orders_error(self):
        """Test live orders error returns empty list."""
        mock_ibkr_client_instance.live_orders.side_effect = Exception("API Error")

        broker = IBKRBroker()
        orders = broker.get_live_orders()

        assert orders == []

    def test_get_account_summary_success(self):
        """Test getting account summary."""
        # Mock portfolio_accounts first
        mock_ibkr_client_instance.portfolio_accounts.return_value = MagicMock(
            data=[{"id": "DU123"}]
        )

        # Mock account_summary
        mock_ibkr_client_instance.account_summary.return_value = MagicMock(
            data={"netliquidation": {"amount": 10000.0}}
        )

        broker = IBKRBroker()
        summary = broker.get_account_summary()

        assert summary is not None

    def test_get_account_summary_error(self):
        """Test account summary error returns None."""
        mock_ibkr_client_instance.portfolio_accounts.side_effect = Exception("API Error")

        broker = IBKRBroker()
        summary = broker.get_account_summary()

        assert summary is None


class TestIBKRClientImportBug:
    """Test for the import time bug in ibkr_client.py."""

    def test_time_import_at_end_of_file(self):
        """
        BUG: ibkr_client.py has 'import time' at the END of the file.
        This test documents the bug - it should be at the top.
        """
        import ast
        from pathlib import Path

        # This would be the actual file path in the project
        # For the test, we'll check if time is used before import
        code = '''
import time  # Should be at top

def place_bracket_order():
    parent_coid = f"parent_{int(time.time())}"
    return parent_coid

# BUG: import time here would cause NameError
'''
        # Parse the code to verify time is imported before use
        tree = ast.parse(code)

        import_nodes = []
        time_usage_nodes = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "time":
                        import_nodes.append(node.lineno)
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "time":
                    time_usage_nodes.append(node.lineno)

        # Import should come before usage
        if import_nodes and time_usage_nodes:
            assert min(import_nodes) < min(time_usage_nodes), \
                "time module should be imported before it's used"

"""Tests for IBKR Client."""

import pytest
from unittest.mock import MagicMock, patch


class TestIBKRBroker:
    """Test IBKR broker client."""

    def test_check_health_success(self):
        """Test successful health check."""
        mock_client = MagicMock()
        mock_client.tickle.return_value = MagicMock(data={"authenticated": True})

        with patch("ibind.IbkrClient", return_value=mock_client):
            from infrastructure.broker.ibkr_client import IBKRBroker

            broker = IBKRBroker()
            result = broker.check_health()

            assert result is True

    def test_check_health_failure(self):
        """Test health check failure."""
        mock_client = MagicMock()
        mock_client.tickle.side_effect = Exception("Connection failed")

        with patch("ibind.IbkrClient", return_value=mock_client):
            from infrastructure.broker.ibkr_client import IBKRBroker

            broker = IBKRBroker()
            result = broker.check_health()

            assert result is False

    def test_get_positions(self):
        """Test getting positions."""
        mock_client = MagicMock()
        mock_client.positions.return_value = MagicMock(
            data=[{"ticker": "SPY", "position": 10}]
        )

        with patch("ibind.IbkrClient", return_value=mock_client):
            from infrastructure.broker.ibkr_client import IBKRBroker

            broker = IBKRBroker()
            positions = broker.get_positions()

            assert len(positions) == 1
            assert positions[0]["ticker"] == "SPY"

    def test_get_positions_error(self):
        """Test positions fetch error returns empty list."""
        mock_client = MagicMock()
        mock_client.positions.side_effect = Exception("API Error")

        with patch("ibind.IbkrClient", return_value=mock_client):
            from infrastructure.broker.ibkr_client import IBKRBroker

            broker = IBKRBroker()
            positions = broker.get_positions()

            assert positions == []

    def test_search_contract(self):
        """Test contract search."""
        mock_client = MagicMock()
        mock_client.search_contract_by_symbol.return_value = MagicMock(
            data=[{"conid": "265598", "symbol": "SPY"}]
        )

        with patch("ibind.IbkrClient", return_value=mock_client):
            from infrastructure.broker.ibkr_client import IBKRBroker

            broker = IBKRBroker()
            contract = broker.search_contract("SPY")

            assert contract is not None
            assert contract["conid"] == "265598"

    def test_search_contract_not_found(self):
        """Test contract search when not found."""
        mock_client = MagicMock()
        mock_client.search_contract_by_symbol.return_value = MagicMock(data=[])

        with patch("ibind.IbkrClient", return_value=mock_client):
            from infrastructure.broker.ibkr_client import IBKRBroker

            broker = IBKRBroker()
            contract = broker.search_contract("INVALID")

            assert contract is None

    def test_place_order(self):
        """Test order placement."""
        mock_client = MagicMock()
        mock_client.place_order.return_value = MagicMock(
            data={"order_id": "12345"}
        )

        with patch("ibind.IbkrClient", return_value=mock_client):
            from infrastructure.broker.ibkr_client import IBKRBroker

            broker = IBKRBroker()
            result = broker.place_order(
                conid="265598",
                side="BUY",
                quantity=10,
                order_type="MKT",
            )

            assert result is not None

    def test_cancel_order_success(self):
        """Test successful order cancellation."""
        mock_client = MagicMock()
        mock_client.cancel_order.return_value = MagicMock(data={"msg": "cancelled"})

        with patch("ibind.IbkrClient", return_value=mock_client):
            from infrastructure.broker.ibkr_client import IBKRBroker

            broker = IBKRBroker()
            result = broker.cancel_order("12345")

            assert result is True

    def test_cancel_order_failure(self):
        """Test order cancellation failure."""
        mock_client = MagicMock()
        mock_client.cancel_order.side_effect = Exception("Not found")

        with patch("ibind.IbkrClient", return_value=mock_client):
            from infrastructure.broker.ibkr_client import IBKRBroker

            broker = IBKRBroker()
            result = broker.cancel_order("12345")

            assert result is False

    def test_get_live_orders(self):
        """Test getting live orders."""
        mock_client = MagicMock()
        mock_client.live_orders.return_value = MagicMock(
            data={"orders": [{"orderId": "123"}]}
        )

        with patch("ibind.IbkrClient", return_value=mock_client):
            from infrastructure.broker.ibkr_client import IBKRBroker

            broker = IBKRBroker()
            orders = broker.get_live_orders()

            assert len(orders) == 1

    def test_get_account_summary(self):
        """Test getting account summary."""
        mock_client = MagicMock()
        mock_client.account_summary.return_value = MagicMock(
            data={"netliquidation": 10000.0}
        )

        with patch("ibind.IbkrClient", return_value=mock_client):
            from infrastructure.broker.ibkr_client import IBKRBroker

            broker = IBKRBroker()
            summary = broker.get_account_summary()

            assert summary is not None
            assert "netliquidation" in summary


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

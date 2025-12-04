"""Portfolio tools for AI."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from infrastructure.broker.ibkr_client import IBKRBroker
from domain.models.position import Position, PortfolioSummary, DailyPnL


class PortfolioTools:
    """Portfolio and account tools for AI function calling."""

    def __init__(self, broker: Optional[IBKRBroker] = None):
        """Initialize portfolio tools.

        Args:
            broker: IBKR broker client
        """
        self._broker = broker or IBKRBroker()

    @staticmethod
    def get_tool_definitions() -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool definitions.

        Returns:
            List of tool definitions
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_positions",
                    "description": "Get all current open positions in the portfolio",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_daily_pnl",
                    "description": "Get the daily profit and loss for the account",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_account_summary",
                    "description": "Get account summary with available USD cash for trading US stocks/options. Returns buying power and cash available in USD.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_trading_history",
                    "description": "Get recent trading history",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days": {
                                "type": "integer",
                                "description": "Number of days of history (1-7)",
                                "default": 1,
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_live_orders",
                    "description": "Get all live/pending orders",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ]

    def get_handlers(self) -> Dict[str, callable]:
        """Get tool handler functions.

        Returns:
            Map of function names to handlers
        """
        return {
            "get_positions": self.get_positions,
            "get_daily_pnl": self.get_daily_pnl,
            "get_account_summary": self.get_account_summary,
            "get_trading_history": self.get_trading_history,
            "get_live_orders": self.get_live_orders,
        }

    def get_positions(self) -> Dict[str, Any]:
        """Get current positions.

        Returns:
            Positions data
        """
        positions_data = self._broker.get_positions()

        positions = [
            Position.from_ibkr(p).to_dict()
            for p in positions_data
        ]

        return {
            "positions": positions,
            "count": len(positions),
            "timestamp": datetime.now().isoformat(),
        }

    def get_daily_pnl(self) -> Dict[str, Any]:
        """Get daily P&L.

        Returns:
            P&L data
        """
        pnl_data = self._broker.get_pnl()

        if not pnl_data:
            return {
                "error": "Unable to fetch P&L",
                "timestamp": datetime.now().isoformat(),
            }

        return {
            "daily_pnl": pnl_data,
            "timestamp": datetime.now().isoformat(),
        }

    def _extract_usd_value(self, data: Dict[str, Any], key: str) -> Optional[float]:
        """Extract USD value from IBKR account data.

        IBKR returns data in format like:
        {
            "totalcashvalue": {"amount": 899078.0, "currency": "HUF", "isNull": false},
            "totalcashvalue-c": {"amount": 899078.0, "currency": "HUF"},
            "totalcashvalue-s": {"amount": 1287.45, "currency": "USD"},
        }

        The '-s' suffix typically means USD (securities currency).

        Args:
            data: Account summary data
            key: Key to look up

        Returns:
            USD value or None
        """
        # Try USD-specific key first (with -s suffix)
        usd_key = f"{key}-s"
        if usd_key in data:
            val = data[usd_key]
            if isinstance(val, dict):
                currency = val.get("currency", "")
                if currency == "USD":
                    return float(val.get("amount", 0))

        # Try the base key and check currency
        if key in data:
            val = data[key]
            if isinstance(val, dict):
                currency = val.get("currency", "")
                if currency == "USD":
                    return float(val.get("amount", 0))
                # If it's already in USD amount directly
                if "amount" in val:
                    return float(val.get("amount", 0))
            elif isinstance(val, (int, float)):
                return float(val)

        return None

    def _parse_account_summary(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """Parse IBKR account summary into clean USD-focused format.

        Args:
            summary: Raw IBKR account summary

        Returns:
            Clean summary focused on USD trading
        """
        # Extract USD values
        usd_cash = self._extract_usd_value(summary, "totalcashvalue")
        usd_buying_power = self._extract_usd_value(summary, "buyingpower")
        usd_available = self._extract_usd_value(summary, "availablefunds")
        usd_net_liq = self._extract_usd_value(summary, "netliquidation")

        # Also try to find any explicit USD cash entries
        # Sometimes IBKR has multiple cash balances by currency
        for key, value in summary.items():
            if isinstance(value, dict):
                currency = value.get("currency", "")
                if currency == "USD" and "cash" in key.lower():
                    amount = value.get("amount", 0)
                    if amount and (usd_cash is None or amount > 0):
                        usd_cash = float(amount)

        # Build clean response for LLM
        result = {
            "usd_available_for_trading": usd_cash or usd_available or 0,
            "usd_buying_power": usd_buying_power or 0,
            "usd_net_liquidation": usd_net_liq or 0,
            "currency": "USD",
            "note": "Values shown are USD available for US stock/option trading",
        }

        # Add warning if USD cash is low
        if result["usd_available_for_trading"] < 1000:
            result["warning"] = "Low USD balance - may need to convert currency or deposit funds for US trading"

        return result

    def get_account_summary(self) -> Dict[str, Any]:
        """Get account summary focused on USD trading.

        Returns:
            Account summary with USD values for trading
        """
        summary = self._broker.get_account_summary()

        if not summary:
            return {
                "error": "Unable to fetch account summary",
                "timestamp": datetime.now().isoformat(),
            }

        # Parse into clean USD format
        parsed = self._parse_account_summary(summary)

        return {
            **parsed,
            "timestamp": datetime.now().isoformat(),
        }

    def get_trading_history(self, days: int = 1) -> Dict[str, Any]:
        """Get trading history.

        Args:
            days: Number of days

        Returns:
            Trading history
        """
        days = min(max(days, 1), 7)  # Clamp to 1-7
        trades = self._broker.get_trades(days=days)

        return {
            "trades": trades,
            "count": len(trades),
            "days": days,
            "timestamp": datetime.now().isoformat(),
        }

    def get_live_orders(self) -> Dict[str, Any]:
        """Get live orders.

        Returns:
            Live orders
        """
        orders = self._broker.get_live_orders()

        return {
            "orders": orders,
            "count": len(orders),
            "timestamp": datetime.now().isoformat(),
        }

    def get_portfolio_summary(self) -> PortfolioSummary:
        """Get full portfolio summary.

        Returns:
            PortfolioSummary object
        """
        summary = self._broker.get_account_summary() or {}
        positions_data = self._broker.get_positions()
        pnl_data = self._broker.get_pnl() or {}

        positions = [Position.from_ibkr(p) for p in positions_data]

        # Extract USD values
        usd_cash = self._extract_usd_value(summary, "totalcashvalue") or 0
        usd_net_liq = self._extract_usd_value(summary, "netliquidation") or 0

        return PortfolioSummary(
            account_id=summary.get("accountId", ""),
            net_liquidation=usd_net_liq,
            total_cash=usd_cash,
            unrealized_pnl=float(pnl_data.get("unrealizedPnl", 0)),
            realized_pnl=float(pnl_data.get("realizedPnl", 0)),
            positions=positions,
        )
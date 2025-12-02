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
                    "description": "Get account summary including cash, buying power, and net liquidation",
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

    def get_account_summary(self) -> Dict[str, Any]:
        """Get account summary.

        Returns:
            Account summary
        """
        summary = self._broker.get_account_summary()

        if not summary:
            return {
                "error": "Unable to fetch account summary",
                "timestamp": datetime.now().isoformat(),
            }

        return {
            "account_summary": summary,
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

        return PortfolioSummary(
            account_id=summary.get("accountId", ""),
            net_liquidation=float(summary.get("netliquidation", {}).get("amount", 0)),
            total_cash=float(summary.get("totalcashvalue", {}).get("amount", 0)),
            unrealized_pnl=float(pnl_data.get("unrealizedPnl", 0)),
            realized_pnl=float(pnl_data.get("realizedPnl", 0)),
            positions=positions,
        )

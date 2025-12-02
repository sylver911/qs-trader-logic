"""Position domain model."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Position:
    """Trading position."""

    conid: str
    symbol: str
    quantity: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    currency: str = "USD"

    @classmethod
    def from_ibkr(cls, data: Dict[str, Any]) -> "Position":
        """Create from IBKR API response.

        Args:
            data: IBKR position data

        Returns:
            Position instance
        """
        return cls(
            conid=str(data.get("conid", "")),
            symbol=data.get("contractDesc", data.get("ticker", "")),
            quantity=float(data.get("position", 0)),
            avg_cost=float(data.get("avgCost", 0)),
            market_value=float(data.get("mktValue", 0)),
            unrealized_pnl=float(data.get("unrealizedPnl", 0)),
            realized_pnl=float(data.get("realizedPnl", 0)),
            currency=data.get("currency", "USD"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "conid": self.conid,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "currency": self.currency,
        }


@dataclass
class PortfolioSummary:
    """Portfolio summary."""

    account_id: str
    net_liquidation: float
    total_cash: float
    unrealized_pnl: float
    realized_pnl: float
    positions: List[Position]

    @property
    def position_count(self) -> int:
        """Number of open positions."""
        return len(self.positions)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "account_id": self.account_id,
            "net_liquidation": self.net_liquidation,
            "total_cash": self.total_cash,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "position_count": self.position_count,
            "positions": [p.to_dict() for p in self.positions],
        }


@dataclass
class DailyPnL:
    """Daily profit and loss."""

    date: str
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    trade_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "date": self.date,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_pnl": self.total_pnl,
            "trade_count": self.trade_count,
        }

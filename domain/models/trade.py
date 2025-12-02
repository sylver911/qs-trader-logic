"""Trade domain model."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class TradeAction(Enum):
    """Possible trade actions."""

    SKIP = "skip"
    EXECUTE = "execute"
    MODIFY = "modify"
    ERROR = "error"


class OrderSide(Enum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type."""

    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    STOP_LIMIT = "STP_LMT"


@dataclass
class TradeDecision:
    """AI's decision on a trade."""

    action: TradeAction
    reasoning: str
    confidence: float = 0.0

    # Modified parameters (if action is MODIFY)
    modified_entry: Optional[float] = None
    modified_target: Optional[float] = None
    modified_stop_loss: Optional[float] = None
    modified_size: Optional[float] = None

    # Skip reason (if action is SKIP)
    skip_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action.value,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "modified_entry": self.modified_entry,
            "modified_target": self.modified_target,
            "modified_stop_loss": self.modified_stop_loss,
            "modified_size": self.modified_size,
            "skip_reason": self.skip_reason,
        }


@dataclass
class OrderRequest:
    """Order request to be sent to broker."""

    conid: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    price: Optional[float] = None
    aux_price: Optional[float] = None  # For stop orders
    tif: str = "DAY"  # Time in force

    # Bracket order components
    take_profit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to IBind order format."""
        order = {
            "conid": self.conid,
            "side": self.side.value,
            "quantity": self.quantity,
            "orderType": self.order_type.value,
            "tif": self.tif,
        }

        if self.price:
            order["price"] = self.price

        if self.aux_price:
            order["auxPrice"] = self.aux_price

        return order


@dataclass
class TradeResult:
    """Result of a trade execution."""

    success: bool
    order_id: Optional[str] = None
    error: Optional[str] = None
    fill_price: Optional[float] = None
    filled_quantity: Optional[int] = None
    simulated: bool = False  # True if dry run (execute_orders=False)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "order_id": self.order_id,
            "error": self.error,
            "fill_price": self.fill_price,
            "filled_quantity": self.filled_quantity,
            "simulated": self.simulated,
            "timestamp": self.timestamp,
        }


@dataclass
class AIResponse:
    """Full AI response for a signal."""

    decision: TradeDecision
    trade_result: Optional[TradeResult] = None
    raw_response: str = ""
    model_used: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_mongo_update(self) -> Dict[str, Any]:
        """Convert to MongoDB update format for 'ai' field."""
        return {
            "decision": self.decision.to_dict(),
            "trade_result": self.trade_result.to_dict() if self.trade_result else None,
            "act": self.decision.action.value,
            "reasoning": self.decision.reasoning,
            "model_used": self.model_used,
            "timestamp": self.timestamp,
        }
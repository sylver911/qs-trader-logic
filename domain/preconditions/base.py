"""Base class for preconditions (Discord cog pattern)."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from domain.models.signal import Signal


class Precondition(ABC):
    """Base class for all preconditions.

    Each precondition is a single validation check that can block trading.
    Similar to Discord bot cogs - modular, self-contained, and easy to add/remove.
    """

    name: str = "base"
    description: str = ""
    live_mode_only: bool = False  # If True, only runs when execute_orders=True

    @abstractmethod
    def check(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        """Check if precondition passes.

        Args:
            signal: The trading signal to validate
            context: Shared context containing:
                - trading_config: Redis config instance
                - broker: IBKRBroker instance
                - market_data: MarketDataProvider instance
                - ticker: Resolved ticker string

        Returns:
            None if precondition passes, error message string if it fails
        """
        pass

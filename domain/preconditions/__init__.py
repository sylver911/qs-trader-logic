"""Preconditions module - Discord cog-style validation checks."""

import logging
from typing import Any, Dict, List, Optional

from domain.models.signal import Signal
from domain.preconditions.base import Precondition
from domain.preconditions.emergency_stop import EmergencyStopPrecondition
from domain.preconditions.ticker_required import TickerRequiredPrecondition
from domain.preconditions.ticker_whitelist import TickerWhitelistPrecondition
from domain.preconditions.ticker_blacklist import TickerBlacklistPrecondition
from domain.preconditions.signal_confidence import SignalConfidencePrecondition
from domain.preconditions.vix_level import VixLevelPrecondition
from domain.preconditions.max_positions import MaxPositionsPrecondition
from domain.preconditions.duplicate_position import DuplicatePositionPrecondition

logger = logging.getLogger(__name__)


class PreconditionManager:
    """Manages and runs all preconditions in order."""

    def __init__(self):
        """Initialize with all preconditions in execution order."""
        self._preconditions: List[Precondition] = [
            EmergencyStopPrecondition(),
            TickerRequiredPrecondition(),
            TickerWhitelistPrecondition(),
            TickerBlacklistPrecondition(),
            SignalConfidencePrecondition(),
            VixLevelPrecondition(),
            MaxPositionsPrecondition(),
            DuplicatePositionPrecondition(),
        ]

    def check_all(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        """Run all preconditions in order.

        Args:
            signal: The trading signal to validate
            context: Shared context dict with trading_config, broker, market_data, ticker

        Returns:
            None if all preconditions pass, first error message if any fails
        """
        is_live = context["trading_config"].execute_orders

        for precondition in self._preconditions:
            # Skip live-only preconditions in dry run mode
            if precondition.live_mode_only and not is_live:
                logger.debug(f"Skipping {precondition.name} (live mode only)")
                continue

            result = precondition.check(signal, context)
            if result is not None:
                logger.debug(f"Precondition {precondition.name} failed: {result}")
                return result

        return None

    @property
    def preconditions(self) -> List[Precondition]:
        """Get list of all preconditions."""
        return self._preconditions


__all__ = ["PreconditionManager", "Precondition"]

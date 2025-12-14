"""Duplicate position precondition."""

from typing import Any, Dict, Optional

from domain.models.signal import Signal
from domain.preconditions.base import Precondition


class DuplicatePositionPrecondition(Precondition):
    """Prevents entering duplicate positions in the same ticker."""

    name = "duplicate_position"
    description = "Blocks duplicate entries in same underlying"
    live_mode_only = True

    def check(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        ticker = context.get("ticker")
        if not ticker:
            return None

        broker = context["broker"]
        positions = broker.get_positions()

        if not positions:
            return None

        # Extract base tickers from positions
        # Handles option symbols like "SPY 241206C00605000"
        existing_tickers = set()
        for pos in positions:
            pos_symbol = pos.get("symbol", "") or pos.get("ticker", "")
            base_ticker = pos_symbol.split()[0].upper() if pos_symbol else ""
            if base_ticker:
                existing_tickers.add(base_ticker)

        if ticker.upper() in existing_tickers:
            return f"Already have position in {ticker} - duplicate entry blocked"

        return None

"""Ticker required precondition."""

from typing import Any, Dict, Optional

from domain.models.signal import Signal
from domain.preconditions.base import Precondition


class TickerRequiredPrecondition(Precondition):
    """Ensures signal has a ticker or sufficient content for AI analysis."""

    name = "ticker_required"
    description = "Requires ticker or meaningful content"
    live_mode_only = False

    def check(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        ticker = context.get("ticker")

        if not ticker:
            # Allow if there's enough content for AI to analyze
            content = signal.get_full_content()
            if content and len(content) > 50:
                return None  # Let AI analyze even without ticker
            return "No ticker found and insufficient content"

        return None

"""Ticker blacklist precondition."""

from typing import Any, Dict, Optional

from domain.models.signal import Signal
from domain.preconditions.base import Precondition


class TickerBlacklistPrecondition(Precondition):
    """Blocks tickers in the blacklist."""

    name = "ticker_blacklist"
    description = "Blocks trading on blacklisted tickers"
    live_mode_only = False

    def check(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        ticker = context.get("ticker")
        blacklist = context["trading_config"].blacklist_tickers

        if ticker and ticker in blacklist:
            return f"Ticker {ticker} is blacklisted"

        return None

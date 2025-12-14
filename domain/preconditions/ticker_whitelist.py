"""Ticker whitelist precondition."""

from typing import Any, Dict, Optional

from domain.models.signal import Signal
from domain.preconditions.base import Precondition


class TickerWhitelistPrecondition(Precondition):
    """Only allows tickers in the whitelist."""

    name = "ticker_whitelist"
    description = "Restricts trading to whitelisted tickers only"
    live_mode_only = False

    def check(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        ticker = context.get("ticker")
        whitelist = context["trading_config"].whitelist_tickers

        if whitelist and ticker and ticker not in whitelist:
            return f"Ticker {ticker} not in whitelist: {whitelist}"

        return None

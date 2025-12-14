"""VIX level precondition."""

from typing import Any, Dict, Optional

from domain.models.signal import Signal
from domain.preconditions.base import Precondition


class VixLevelPrecondition(Precondition):
    """Blocks trading when VIX is above maximum threshold."""

    name = "vix_level"
    description = "Blocks trading during high volatility (VIX)"
    live_mode_only = True

    def check(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        max_vix = context["trading_config"].max_vix_level
        market_data = context["market_data"]

        vix = market_data.get_vix()
        if vix and vix > max_vix:
            return f"VIX {vix:.1f} above maximum {max_vix}"

        return None

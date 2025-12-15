"""VIX (Volatility Index) prefetch.

Fetches current VIX level for volatility assessment.

Jinja2 template usage:
    {{ vix.value }}      -> 18.5
    {{ vix.level }}      -> "normal" / "elevated" / "high" / "extreme"
    {{ vix.timestamp }}  -> "2025-12-15T10:30:00"

    Conditional:
    {% if vix.value > 25 %}
        High volatility environment - consider reducing position size
    {% elif vix.value < 15 %}
        Low volatility - normal position sizing
    {% endif %}

    Level-based:
    {% if vix.level == "extreme" %}
        EXTREME volatility - trading halted
    {% endif %}
"""

import logging
from datetime import datetime
from typing import Any, Dict

from domain.prefetches.base import Prefetch, PrefetchResult

logger = logging.getLogger(__name__)


def _classify_vix_level(vix_value: float) -> str:
    """Classify VIX into human-readable levels."""
    if vix_value < 15:
        return "low"
    elif vix_value < 20:
        return "normal"
    elif vix_value < 25:
        return "elevated"
    elif vix_value < 30:
        return "high"
    else:
        return "extreme"


class VixPrefetch(Prefetch):
    """Prefetch current VIX level.

    Template key: vix
    """

    name = "vix"
    key = "vix"
    description = "Current VIX volatility index"
    requires_ticker = False
    requires_broker = False  # Uses yfinance

    def fetch(self, signal, context: Dict[str, Any]) -> PrefetchResult:
        """Fetch current VIX."""
        try:
            market_data = context.get("market_data")
            if not market_data:
                return PrefetchResult.from_error("No market_data provider in context")

            vix_value = market_data.get_vix()

            if vix_value is None:
                return PrefetchResult.from_error("Failed to get VIX")

            data = {
                "value": round(vix_value, 2),
                "level": _classify_vix_level(vix_value),
                "timestamp": datetime.now().isoformat(),

                # Convenience booleans for templates
                "is_low": vix_value < 15,
                "is_normal": 15 <= vix_value < 20,
                "is_elevated": 20 <= vix_value < 25,
                "is_high": 25 <= vix_value < 30,
                "is_extreme": vix_value >= 30,
            }

            return PrefetchResult.from_data(data)

        except Exception as e:
            logger.error(f"VIX prefetch error: {e}")
            return PrefetchResult.from_error(str(e))

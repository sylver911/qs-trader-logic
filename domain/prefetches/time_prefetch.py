"""Time and market status prefetch.

Provides current time in EST and NYSE market status.

Jinja2 template usage:
    {{ time.time_est }}           -> "10:30:45"
    {{ time.date }}               -> "2025-12-15"
    {{ time.day_of_week }}        -> "Monday"
    {{ time.is_market_open }}     -> True/False
    {{ time.market_status }}      -> "open" / "closed"
    {{ time.status_reason }}      -> "market_open" / "after_hours" / "weekend" / "holiday"
    {{ time.closes_at }}          -> "16:00 ET" (only when open)
    {{ time.opens_at }}           -> "09:30 ET" (only when closed pre-market)

Conditional example:
    {% if time.is_market_open %}
        Market is open until {{ time.closes_at }}
    {% else %}
        Market is closed ({{ time.status_reason }})
    {% endif %}
"""

from datetime import datetime, date
from typing import Any, Dict
import pytz

from domain.prefetches.base import Prefetch, PrefetchResult


# NYSE Holiday Calendar 2024-2026
NYSE_HOLIDAYS = {
    # 2024
    date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19), date(2024, 3, 29),
    date(2024, 5, 27), date(2024, 6, 19), date(2024, 7, 4), date(2024, 9, 2),
    date(2024, 11, 28), date(2024, 12, 25),
    # 2025
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1),
    date(2025, 11, 27), date(2025, 12, 25),
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
}

# Early close days (1:00 PM ET)
NYSE_EARLY_CLOSE = {
    date(2024, 7, 3), date(2024, 11, 29), date(2024, 12, 24),
    date(2025, 7, 3), date(2025, 11, 28), date(2025, 12, 24),
    date(2026, 11, 27), date(2026, 12, 24),
}


def _check_nyse_status(dt: datetime) -> Dict[str, Any]:
    """Check NYSE market status at given datetime."""
    current_date = dt.date()
    current_time = dt.time()

    if dt.weekday() >= 5:
        return {
            "is_open": False,
            "reason": "weekend",
            "day_of_week": dt.strftime("%A"),
        }

    if current_date in NYSE_HOLIDAYS:
        return {"is_open": False, "reason": "holiday"}

    market_open_time = dt.replace(hour=9, minute=30, second=0, microsecond=0).time()

    if current_date in NYSE_EARLY_CLOSE:
        market_close_time = dt.replace(hour=13, minute=0, second=0, microsecond=0).time()
        close_str = "13:00 ET"
    else:
        market_close_time = dt.replace(hour=16, minute=0, second=0, microsecond=0).time()
        close_str = "16:00 ET"

    if current_time < market_open_time:
        return {"is_open": False, "reason": "pre_market", "opens_at": "09:30 ET"}
    elif current_time > market_close_time:
        return {"is_open": False, "reason": "after_hours"}
    else:
        return {"is_open": True, "reason": "market_open", "closes_at": close_str}


class TimePrefetch(Prefetch):
    """Prefetch current time and NYSE market status.

    Template key: time
    """

    name = "current_time"
    key = "time"
    description = "Current time in EST and NYSE market status"
    requires_ticker = False
    requires_broker = False

    def fetch(self, signal, context: Dict[str, Any]) -> PrefetchResult:
        """Fetch current time and market status."""
        try:
            est = pytz.timezone("US/Eastern")
            now = datetime.now(est)
            market_status = _check_nyse_status(now)

            data = {
                # Time fields
                "timestamp": now.isoformat(),
                "time_est": now.strftime("%H:%M:%S"),
                "date": now.strftime("%Y-%m-%d"),
                "day_of_week": now.strftime("%A"),
                "timezone": "US/Eastern (ET)",

                # Market status
                "is_market_open": market_status["is_open"],
                "market_status": "open" if market_status["is_open"] else "closed",
                "status_reason": market_status["reason"],
            }

            # Add conditional fields
            if "closes_at" in market_status:
                data["closes_at"] = market_status["closes_at"]
            if "opens_at" in market_status:
                data["opens_at"] = market_status["opens_at"]

            return PrefetchResult.from_data(data)

        except Exception as e:
            return PrefetchResult.from_error(str(e))

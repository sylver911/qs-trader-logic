"""Account summary prefetch.

Fetches account balance and buying power information.

Jinja2 template usage:
    {{ account.available }}        -> 10000.00 (USD available for trading)
    {{ account.buying_power }}     -> 20000.00
    {{ account.net_liquidation }}  -> 50000.00
    {{ account.currency }}         -> "USD"

    Formatted:
    Available: ${{ "%.2f"|format(account.available) }}

    Conditional:
    {% if account.available > 1000 %}
        Sufficient funds available
    {% else %}
        Low account balance!
    {% endif %}
"""

import logging
from typing import Any, Dict

from domain.prefetches.base import Prefetch, PrefetchResult

logger = logging.getLogger(__name__)


class AccountPrefetch(Prefetch):
    """Prefetch account summary (balance, buying power).

    Template key: account
    """

    name = "account_summary"
    key = "account"
    description = "Account balance and buying power"
    requires_ticker = False
    requires_broker = True

    def fetch(self, signal, context: Dict[str, Any]) -> PrefetchResult:
        """Fetch account summary."""
        try:
            broker = context.get("broker")
            trading_config = context.get("trading_config")

            # In dry run mode, return mock data
            if trading_config and not trading_config.execute_orders:
                data = {
                    "available": 10000.00,
                    "buying_power": 20000.00,
                    "net_liquidation": 50000.00,
                    "currency": "USD",
                    "is_simulated": True,
                }
                return PrefetchResult.from_data(data)

            if not broker:
                return PrefetchResult.from_error("No broker in context")

            # Get real account data
            summary = broker.get_account_summary()

            if not summary:
                return PrefetchResult.from_error("Failed to get account summary")

            # Normalize field names for template use
            data = {
                "available": summary.get("usd_available_for_trading",
                            summary.get("availableFunds",
                            summary.get("available", 0))),
                "buying_power": summary.get("usd_buying_power",
                               summary.get("buyingPower",
                               summary.get("buying_power", 0))),
                "net_liquidation": summary.get("usd_net_liquidation",
                                  summary.get("netLiquidation",
                                  summary.get("net_liquidation", 0))),
                "currency": "USD",
                "is_simulated": False,
            }

            return PrefetchResult.from_data(data)

        except Exception as e:
            logger.error(f"Account prefetch error: {e}")
            return PrefetchResult.from_error(str(e))

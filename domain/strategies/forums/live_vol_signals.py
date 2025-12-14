"""Strategy for 💣live-vol-signals forum.

Volatility trading signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveVolStrategy(SkipStrategy):
    """Volatility trading strategy. (NOT IMPLEMENTED)"""

    name = "live_vol"
    description = "Volatility trading signals"

    forum_id = "1408844438192652328"
    forum_name_pattern = r"live-vol-signals"

    def __init__(self):
        super().__init__(reason="Volatility strategy not implemented")

    # TODO: Implement volatility trading logic
    # Consider: VIX products, vol spreads, gamma scalping

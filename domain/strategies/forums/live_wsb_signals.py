"""Strategy for 🎲live-wsb-signals forum.

WallStreetBets style signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveWsbStrategy(SkipStrategy):
    """WallStreetBets style strategy. (NOT IMPLEMENTED)"""

    name = "live_wsb"
    description = "WSB-style high risk signals"

    forum_id = "1392117684656799824"
    forum_name_pattern = r"live-wsb-signals"

    def __init__(self):
        super().__init__(reason="WSB signals strategy not implemented")

    # TODO: Implement WSB-style trading logic
    # Consider: meme stocks, high volatility, YOLO trades

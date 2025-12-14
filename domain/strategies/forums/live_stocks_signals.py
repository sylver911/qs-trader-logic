"""Strategy for 💼live-stocks-signals forum.

Stock (non-options) signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveStocksStrategy(SkipStrategy):
    """Stock trading strategy. (NOT IMPLEMENTED)"""

    name = "live_stocks"
    description = "Stock (equity) signals"

    forum_id = "1373533551772831764"
    forum_name_pattern = r"live-stocks-signals"

    def __init__(self):
        super().__init__(reason="Stocks strategy not implemented")

    # TODO: Implement stock trading logic
    # Consider: equity positions, not options

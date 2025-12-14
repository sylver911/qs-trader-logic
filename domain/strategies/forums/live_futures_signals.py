"""Strategy for 🛢live-futures-signals forum.

Futures trading signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveFuturesStrategy(SkipStrategy):
    """Futures trading strategy. (NOT IMPLEMENTED)"""

    name = "live_futures"
    description = "Futures trading signals"

    forum_id = "1373533427940200500"
    forum_name_pattern = r"live-futures-signals"

    def __init__(self):
        super().__init__(reason="Futures strategy not implemented")

    # TODO: Implement futures trading logic
    # Consider: ES, NQ, CL - different contract handling

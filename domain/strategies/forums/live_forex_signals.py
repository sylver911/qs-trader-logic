"""Strategy for 💹live-forex-signals forum.

Forex trading signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveForexStrategy(SkipStrategy):
    """Forex trading strategy. (NOT IMPLEMENTED)"""

    name = "live_forex"
    description = "Forex trading signals"

    forum_id = "1376805441274646539"
    forum_name_pattern = r"live-forex-signals"

    def __init__(self):
        super().__init__(reason="Forex strategy not implemented")

    # TODO: Implement forex trading logic
    # Consider: currency pairs, different broker integration

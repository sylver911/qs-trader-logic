"""Strategy for ⌛live-leap-signals forum.

LEAPS (long-term options) signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveLeapStrategy(SkipStrategy):
    """LEAPS strategy. (NOT IMPLEMENTED)"""

    name = "live_leap"
    description = "LEAPS (long-term options) signals"

    forum_id = "1373533391361937478"
    forum_name_pattern = r"live-leap-signals"

    def __init__(self):
        super().__init__(reason="LEAPS strategy not implemented")

    # TODO: Implement LEAPS logic
    # Consider: long-term holds, stock replacement, delta exposure

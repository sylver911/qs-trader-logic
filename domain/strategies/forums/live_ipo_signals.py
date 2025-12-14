"""Strategy for 🚀live-ipo-signals forum.

IPO trading signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveIpoStrategy(SkipStrategy):
    """IPO trading strategy. (NOT IMPLEMENTED)"""

    name = "live_ipo"
    description = "IPO trading signals"

    forum_id = "1402524542504665138"
    forum_name_pattern = r"live-ipo-signals"

    def __init__(self):
        super().__init__(reason="IPO strategy not implemented")

    # TODO: Implement IPO trading logic
    # Consider: lockup expirations, first day trades

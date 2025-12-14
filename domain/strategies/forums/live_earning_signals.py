"""Strategy for 💸live-earning-signals forum.

Earnings play signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveEarningStrategy(SkipStrategy):
    """Earnings play strategy. (NOT IMPLEMENTED)"""

    name = "live_earning"
    description = "Earnings play signals"

    forum_id = "1373533516431884398"
    forum_name_pattern = r"live-earning-signals"

    def __init__(self):
        super().__init__(reason="Earnings strategy not implemented")

    # TODO: Implement earnings play logic
    # Consider: IV crush, straddles/strangles, directional bets

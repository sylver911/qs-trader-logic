"""Strategy for 📅live-weekly-signals forum.

Weekly options signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveWeeklyStrategy(SkipStrategy):
    """Weekly options strategy. (NOT IMPLEMENTED)"""

    name = "live_weekly"
    description = "Weekly options signals"

    forum_id = "1373533175724376197"
    forum_name_pattern = r"live-weekly-signals"

    def __init__(self):
        super().__init__(reason="Weekly options strategy not implemented")

    # TODO: Implement weekly options logic
    # Consider: theta decay, weekend risk, longer holding periods

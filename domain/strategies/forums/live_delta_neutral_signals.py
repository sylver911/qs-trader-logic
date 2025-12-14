"""Strategy for 🧇live-delta-neutral-signals forum.

Delta neutral signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveDeltaNeutralStrategy(SkipStrategy):
    """Delta neutral strategy. (NOT IMPLEMENTED)"""

    name = "live_delta_neutral"
    description = "Delta neutral signals"

    forum_id = "1378202249699922011"
    forum_name_pattern = r"live-delta-neutral-signals"

    def __init__(self):
        super().__init__(reason="Delta neutral strategy not implemented")

    # TODO: Implement delta neutral logic
    # Consider: straddles, strangles, hedged positions

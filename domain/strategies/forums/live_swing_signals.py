"""Strategy for 🔄live-swing-signals forum.

Swing trading signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveSwingStrategy(SkipStrategy):
    """Swing trading strategy. (NOT IMPLEMENTED)"""

    name = "live_swing"
    description = "Swing trading signals"

    forum_id = "1373533328631922729"
    forum_name_pattern = r"live-swing-signals"

    def __init__(self):
        super().__init__(reason="Swing trading strategy not implemented")

    # TODO: Implement swing trading logic
    # Consider: multi-day holds, trend following, support/resistance

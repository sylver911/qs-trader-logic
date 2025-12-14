"""Strategy for 💥live-small-options forum.

Small cap options signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveSmallOptionsStrategy(SkipStrategy):
    """Small cap options strategy. (NOT IMPLEMENTED)"""

    name = "live_small_options"
    description = "Small cap options signals"

    forum_id = "1419885141454753813"
    forum_name_pattern = r"live-small-options"

    def __init__(self):
        super().__init__(reason="Small options strategy not implemented")

    # TODO: Implement small cap options logic
    # Consider: higher risk tolerance, wider stops, smaller position sizes

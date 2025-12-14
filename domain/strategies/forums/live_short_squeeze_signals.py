"""Strategy for 📈live-short-squeeze-signals forum.

Short squeeze signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveShortSqueezeStrategy(SkipStrategy):
    """Short squeeze strategy. (NOT IMPLEMENTED)"""

    name = "live_short_squeeze"
    description = "Short squeeze signals"

    forum_id = "1434390722542567437"
    forum_name_pattern = r"live-short-squeeze-signals"

    def __init__(self):
        super().__init__(reason="Short squeeze strategy not implemented")

    # TODO: Implement short squeeze logic
    # Consider: short interest, days to cover, borrow rate

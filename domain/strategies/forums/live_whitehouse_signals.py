"""Strategy for 🏛️live-whitehouse-signals forum.

Political/White House related signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveWhitehouseStrategy(SkipStrategy):
    """White House/political strategy. (NOT IMPLEMENTED)"""

    name = "live_whitehouse"
    description = "Political event signals"

    forum_id = "1405094188076372019"
    forum_name_pattern = r"live-whitehouse-signals"

    def __init__(self):
        super().__init__(reason="White House strategy not implemented")

    # TODO: Implement political event logic
    # Consider: policy announcements, regulatory changes

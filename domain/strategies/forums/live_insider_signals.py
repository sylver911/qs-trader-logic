"""Strategy for 👩‍💼live-insider-signals forum.

Insider trading signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveInsiderStrategy(SkipStrategy):
    """Insider trading strategy. (NOT IMPLEMENTED)"""

    name = "live_insider"
    description = "Insider trading signals"

    forum_id = "1436251132744831017"
    forum_name_pattern = r"live-insider-signals"

    def __init__(self):
        super().__init__(reason="Insider signals strategy not implemented")

    # TODO: Implement insider trading logic
    # Consider: Form 4 filings, cluster buys, executive purchases

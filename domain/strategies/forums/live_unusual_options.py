"""Strategy for 🤖live-unusual-options forum.

Unusual options activity signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveUnusualOptionsStrategy(SkipStrategy):
    """Unusual options activity strategy. (NOT IMPLEMENTED)"""

    name = "live_unusual_options"
    description = "Unusual options activity signals"

    forum_id = "1381222105529450566"
    forum_name_pattern = r"live-unusual-options"

    def __init__(self):
        super().__init__(reason="Unusual options strategy not implemented")

    # TODO: Implement unusual options flow logic
    # Consider: volume spikes, large block trades, smart money tracking

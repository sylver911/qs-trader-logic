"""Strategy for 🦔live-covered-call-signals forum.

Covered call signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveCoveredCallStrategy(SkipStrategy):
    """Covered call strategy. (NOT IMPLEMENTED)"""

    name = "live_covered_call"
    description = "Covered call signals"

    forum_id = "1403125945367269426"
    forum_name_pattern = r"live-covered-call-signals"

    def __init__(self):
        super().__init__(reason="Covered call strategy not implemented")

    # TODO: Implement covered call logic
    # Consider: stock + short call, income generation

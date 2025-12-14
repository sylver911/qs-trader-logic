"""Strategy for 💎live-sp-inclusion-signals forum.

S&P 500 inclusion signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveSpInclusionStrategy(SkipStrategy):
    """S&P inclusion strategy. (NOT IMPLEMENTED)"""

    name = "live_sp_inclusion"
    description = "S&P 500 inclusion signals"

    forum_id = "1434391229713612900"
    forum_name_pattern = r"live-sp-inclusion-signals"

    def __init__(self):
        super().__init__(reason="S&P inclusion strategy not implemented")

    # TODO: Implement S&P inclusion logic
    # Consider: index rebalancing, passive fund flows

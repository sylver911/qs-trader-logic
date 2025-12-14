"""Strategy for 💵live-credit-spread-signals forum.

Credit spread signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveCreditSpreadStrategy(SkipStrategy):
    """Credit spread strategy. (NOT IMPLEMENTED)"""

    name = "live_credit_spread"
    description = "Credit spread signals"

    forum_id = "1427565217151193230"
    forum_name_pattern = r"live-credit-spread-signals"

    def __init__(self):
        super().__init__(reason="Credit spread strategy not implemented")

    # TODO: Implement credit spread logic
    # Consider: multi-leg orders, defined risk strategies

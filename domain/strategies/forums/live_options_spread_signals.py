"""Strategy for 🧈live-options-spread-signals forum.

Options spread signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveOptionsSpreadStrategy(SkipStrategy):
    """Options spread strategy. (NOT IMPLEMENTED)"""

    name = "live_options_spread"
    description = "Options spread signals"

    forum_id = "1378202161896493189"
    forum_name_pattern = r"live-options-spread-signals"

    def __init__(self):
        super().__init__(reason="Options spread strategy not implemented")

    # TODO: Implement options spread logic
    # Consider: debit/credit spreads, butterflies, condors

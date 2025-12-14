"""Strategy for 🕶️live-darkpool-signals forum.

Dark pool trading signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveDarkpoolStrategy(SkipStrategy):
    """Dark pool strategy. (NOT IMPLEMENTED)"""

    name = "live_darkpool"
    description = "Dark pool signals"

    forum_id = "1436251327062872115"
    forum_name_pattern = r"live-darkpool-signals"

    def __init__(self):
        super().__init__(reason="Dark pool strategy not implemented")

    # TODO: Implement dark pool logic
    # Consider: large block prints, institutional flow

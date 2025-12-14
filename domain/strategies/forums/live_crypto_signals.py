"""Strategy for 🪙live-crypto-signals forum.

Cryptocurrency signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveCryptoStrategy(SkipStrategy):
    """Crypto trading strategy. (NOT IMPLEMENTED)"""

    name = "live_crypto"
    description = "Cryptocurrency signals"

    forum_id = "1373533466276270081"
    forum_name_pattern = r"live-crypto-signals"

    def __init__(self):
        super().__init__(reason="Crypto strategy not implemented")

    # TODO: Implement crypto trading logic
    # Consider: BTC, ETH, altcoins - different broker integration needed

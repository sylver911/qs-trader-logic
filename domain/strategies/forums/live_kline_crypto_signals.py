"""Strategy for 🎰live-kline-crypto-signals forum.

Crypto Kline pattern signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveKlineCryptoStrategy(SkipStrategy):
    """Crypto Kline pattern strategy. (NOT IMPLEMENTED)"""

    name = "live_kline_crypto"
    description = "Crypto Kline pattern signals"

    forum_id = "1419027708989542480"
    forum_name_pattern = r"live-kline-crypto-signals"

    def __init__(self):
        super().__init__(reason="Crypto Kline strategy not implemented")

    # TODO: Implement crypto Kline logic
    # Consider: BTC/ETH patterns, crypto-specific indicators

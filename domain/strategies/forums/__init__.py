"""Forum-specific trading strategies.

Each forum has its own strategy that determines how signals are processed.
"""

from domain.strategies.forums.live_0dte_signals import Live0DteStrategy
from domain.strategies.forums.live_kline_signals import LiveKlineStrategy
from domain.strategies.forums.live_news_signals import LiveNewsStrategy
from domain.strategies.forums.live_unusual_options import LiveUnusualOptionsStrategy
from domain.strategies.forums.live_small_options import LiveSmallOptionsStrategy
from domain.strategies.forums.live_wsb_signals import LiveWsbStrategy
from domain.strategies.forums.live_short_squeeze_signals import LiveShortSqueezeStrategy
from domain.strategies.forums.live_sp_inclusion_signals import LiveSpInclusionStrategy
from domain.strategies.forums.live_insider_signals import LiveInsiderStrategy
from domain.strategies.forums.live_darkpool_signals import LiveDarkpoolStrategy
from domain.strategies.forums.live_credit_spread_signals import LiveCreditSpreadStrategy
from domain.strategies.forums.live_whitehouse_signals import LiveWhitehouseStrategy
from domain.strategies.forums.live_kline_crypto_signals import LiveKlineCryptoStrategy
from domain.strategies.forums.live_weekly_signals import LiveWeeklyStrategy
from domain.strategies.forums.live_earning_signals import LiveEarningStrategy
from domain.strategies.forums.live_swing_signals import LiveSwingStrategy
from domain.strategies.forums.live_stocks_signals import LiveStocksStrategy
from domain.strategies.forums.live_leap_signals import LiveLeapStrategy
from domain.strategies.forums.live_vol_signals import LiveVolStrategy
from domain.strategies.forums.live_ipo_signals import LiveIpoStrategy
from domain.strategies.forums.live_options_spread_signals import LiveOptionsSpreadStrategy
from domain.strategies.forums.live_delta_neutral_signals import LiveDeltaNeutralStrategy
from domain.strategies.forums.live_covered_call_signals import LiveCoveredCallStrategy
from domain.strategies.forums.live_crypto_signals import LiveCryptoStrategy
from domain.strategies.forums.live_futures_signals import LiveFuturesStrategy
from domain.strategies.forums.live_forex_signals import LiveForexStrategy

# All available forum strategies
ALL_STRATEGIES = [
    Live0DteStrategy,
    LiveKlineStrategy,
    LiveNewsStrategy,
    LiveUnusualOptionsStrategy,
    LiveSmallOptionsStrategy,
    LiveWsbStrategy,
    LiveShortSqueezeStrategy,
    LiveSpInclusionStrategy,
    LiveInsiderStrategy,
    LiveDarkpoolStrategy,
    LiveCreditSpreadStrategy,
    LiveWhitehouseStrategy,
    LiveKlineCryptoStrategy,
    LiveWeeklyStrategy,
    LiveEarningStrategy,
    LiveSwingStrategy,
    LiveStocksStrategy,
    LiveLeapStrategy,
    LiveVolStrategy,
    LiveIpoStrategy,
    LiveOptionsSpreadStrategy,
    LiveDeltaNeutralStrategy,
    LiveCoveredCallStrategy,
    LiveCryptoStrategy,
    LiveFuturesStrategy,
    LiveForexStrategy,
]

__all__ = [
    "Live0DteStrategy",
    "LiveKlineStrategy",
    "LiveNewsStrategy",
    "LiveUnusualOptionsStrategy",
    "LiveSmallOptionsStrategy",
    "LiveWsbStrategy",
    "LiveShortSqueezeStrategy",
    "LiveSpInclusionStrategy",
    "LiveInsiderStrategy",
    "LiveDarkpoolStrategy",
    "LiveCreditSpreadStrategy",
    "LiveWhitehouseStrategy",
    "LiveKlineCryptoStrategy",
    "LiveWeeklyStrategy",
    "LiveEarningStrategy",
    "LiveSwingStrategy",
    "LiveStocksStrategy",
    "LiveLeapStrategy",
    "LiveVolStrategy",
    "LiveIpoStrategy",
    "LiveOptionsSpreadStrategy",
    "LiveDeltaNeutralStrategy",
    "LiveCoveredCallStrategy",
    "LiveCryptoStrategy",
    "LiveFuturesStrategy",
    "LiveForexStrategy",
    "ALL_STRATEGIES",
]

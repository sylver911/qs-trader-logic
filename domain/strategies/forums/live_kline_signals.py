"""Strategy for 🎰live-kline-signals forum.

Kline signals based on technical analysis patterns.
Uses LLM analysis by default, but can be switched to hardcoded rules.

NOTE: Ticker whitelist/blacklist comes from Redis config (dashboard).
Strategy-level whitelist is empty = use global Redis config.
"""

from domain.strategies.base import StrategyConfig
from domain.strategies.llm_strategy import LlmStrategy


class LiveKlineStrategy(LlmStrategy):
    """Kline pattern trading strategy.

    This forum focuses on Kline (candlestick) pattern signals.
    Currently uses LLM analysis, but can be customized for pattern-specific rules.

    Ticker filtering is controlled by Redis config (dashboard settings).
    """

    name = "live_kline"
    description = "Kline pattern trading with LLM analysis"

    # Forum matching
    forum_id = "1412620062346444810"
    forum_name_pattern = r"live-kline-signals"

    def __init__(self):
        super().__init__()

        # Strategy-specific configuration
        # NOTE: whitelist/blacklist comes from Redis config (dashboard)
        # Empty list here means: use global Redis config
        self.config = StrategyConfig(
            # Ticker filters - EMPTY = use Redis config from dashboard
            whitelist_tickers=[],  # Controlled by dashboard
            blacklist_tickers=[],  # Controlled by dashboard

            # AI settings
            use_llm=True,
            llm_model=None,  # Use global default
            min_confidence=0.5,

            # Execution
            enabled=True,
            dry_run_override=None,

            # Risk
            max_position_size_percent=0.05,
            max_positions=5,
        )

    # TODO: Override execute() for hardcoded Kline pattern logic if needed
    # def execute(self, signal: Signal, context: Dict[str, Any]) -> AIResponse:
    #     # Custom Kline pattern analysis
    #     pass

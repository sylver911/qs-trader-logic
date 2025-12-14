"""Strategy for 🎰live-kline-signals forum.

Kline signals based on technical analysis patterns.
Uses LLM analysis by default, but can be switched to hardcoded rules.
"""

from domain.strategies.base import StrategyConfig
from domain.strategies.llm_strategy import LlmStrategy


class LiveKlineStrategy(LlmStrategy):
    """Kline pattern trading strategy.

    This forum focuses on Kline (candlestick) pattern signals.
    Currently uses LLM analysis, but can be customized for pattern-specific rules.
    """

    name = "live_kline"
    description = "Kline pattern trading with LLM analysis"

    # Forum matching
    forum_id = "1412620062346444810"
    forum_name_pattern = r"live-kline-signals"

    def __init__(self):
        super().__init__()

        # Strategy-specific configuration
        self.config = StrategyConfig(
            # Ticker filters - broader range for Kline patterns
            whitelist_tickers=["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META", "GOOGL", "AMZN"],
            blacklist_tickers=[],

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

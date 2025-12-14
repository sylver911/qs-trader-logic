"""Strategy for ⏰live-0dte-signals forum.

This is the main 0DTE options trading strategy using LLM analysis.
Uses the current production logic with AI-based decision making.
"""

from domain.strategies.base import StrategyConfig
from domain.strategies.llm_strategy import LlmStrategy


class Live0DteStrategy(LlmStrategy):
    """0DTE options trading strategy with LLM analysis.

    This forum focuses on same-day expiry (0DTE) options trades.
    Uses AI to analyze signals and make trading decisions.
    """

    name = "live_0dte"
    description = "0DTE options trading with LLM analysis"

    # Forum matching
    forum_id = "1373531558274666496"
    forum_name_pattern = r"live-0dte-signals"

    def __init__(self):
        super().__init__()

        # Strategy-specific configuration
        self.config = StrategyConfig(
            # Ticker filters - only trade major indices for 0DTE
            whitelist_tickers=["SPY", "QQQ", "IWM", "DIA"],
            blacklist_tickers=[],

            # AI settings
            use_llm=True,
            llm_model=None,  # Use global default
            min_confidence=0.6,

            # Execution
            enabled=True,
            dry_run_override=None,  # Use global setting

            # Risk - conservative for 0DTE
            max_position_size_percent=0.03,  # 3% max per trade
            max_positions=3,  # Max 3 concurrent 0DTE positions
        )

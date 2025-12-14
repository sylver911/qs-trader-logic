"""Base strategy class for forum-specific trading strategies.

Each forum can have its own strategy that determines how signals are processed.
Strategies can use LLM analysis, hardcoded rules, or a combination.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from domain.models.signal import Signal
from domain.models.trade import AIResponse


@dataclass
class StrategyConfig:
    """Configuration for a trading strategy.

    This replaces per-forum settings that were previously global.
    """
    # Ticker filters (moved from global config)
    whitelist_tickers: List[str] = field(default_factory=list)  # Empty = all allowed
    blacklist_tickers: List[str] = field(default_factory=list)

    # AI settings
    use_llm: bool = True  # False = hardcoded logic only
    llm_model: Optional[str] = None  # None = use global default
    min_confidence: float = 0.5

    # Execution settings
    enabled: bool = True  # False = skip all signals from this forum
    dry_run_override: Optional[bool] = None  # None = use global, True/False = override

    # Risk settings
    max_position_size_percent: float = 0.05
    max_positions: Optional[int] = None  # None = use global


class Strategy(ABC):
    """Base class for forum-specific trading strategies.

    Similar to Discord cog pattern - each strategy handles a specific forum.
    """

    # Strategy metadata
    name: str = "base"
    description: str = ""

    # Forum matching - set one or both
    forum_id: Optional[str] = None  # Exact match by ID
    forum_name_pattern: Optional[str] = None  # Regex pattern for forum name

    # Strategy configuration
    config: StrategyConfig = field(default_factory=StrategyConfig)

    def __init__(self):
        """Initialize strategy with default config."""
        if not hasattr(self, 'config') or self.config is None:
            self.config = StrategyConfig()

    def matches(self, signal: Signal) -> bool:
        """Check if this strategy handles the given signal's forum.

        Args:
            signal: The trading signal

        Returns:
            True if this strategy should handle signals from this forum
        """
        # Match by forum_id (exact)
        if self.forum_id and signal.forum_id == self.forum_id:
            return True

        # Match by forum_name pattern (regex)
        if self.forum_name_pattern:
            pattern = re.compile(self.forum_name_pattern, re.IGNORECASE)
            if pattern.search(signal.forum_name or ""):
                return True

        return False

    def validate_ticker(self, signal: Signal) -> Optional[str]:
        """Validate ticker against strategy's whitelist/blacklist.

        Args:
            signal: The trading signal

        Returns:
            Error message if validation fails, None if passed
        """
        ticker = signal.ticker
        if not ticker:
            return None  # No ticker to validate

        ticker = ticker.upper()

        # Check whitelist (if set)
        if self.config.whitelist_tickers:
            if ticker not in [t.upper() for t in self.config.whitelist_tickers]:
                return f"Ticker {ticker} not in strategy whitelist: {self.config.whitelist_tickers}"

        # Check blacklist
        if self.config.blacklist_tickers:
            if ticker in [t.upper() for t in self.config.blacklist_tickers]:
                return f"Ticker {ticker} is blacklisted in strategy"

        return None

    def pre_check(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        """Run strategy-specific pre-checks before execution.

        Override this to add custom validation logic.

        Args:
            signal: The trading signal
            context: Shared context dict

        Returns:
            Error message if check fails, None if passed
        """
        # Check if strategy is enabled
        if not self.config.enabled:
            return f"Strategy '{self.name}' is disabled"

        # Validate ticker
        ticker_error = self.validate_ticker(signal)
        if ticker_error:
            return ticker_error

        return None

    @abstractmethod
    def execute(self, signal: Signal, context: Dict[str, Any]) -> AIResponse:
        """Execute the trading strategy for a signal.

        Args:
            signal: The trading signal to process
            context: Shared context containing:
                - trading_config: Global TradingConfig
                - broker: IBKRBroker instance
                - market_data: MarketDataProvider instance
                - prefetched_data: Pre-fetched tool data
                - scheduled_context: Context from previous analysis (if reanalysis)

        Returns:
            AIResponse with the decision (execute/skip/delay)
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' forum_id='{self.forum_id}'>"


class SkipStrategy(Strategy):
    """Strategy that always skips signals.

    Use this as a placeholder for forums that are not yet implemented.
    """

    name = "skip"
    description = "Skips all signals (placeholder strategy)"

    def __init__(self, reason: str = "Forum strategy not implemented"):
        super().__init__()
        self.skip_reason = reason
        self.config.enabled = True

    def execute(self, signal: Signal, context: Dict[str, Any]) -> AIResponse:
        from domain.models.trade import TradeDecision, TradeAction

        return AIResponse(
            decision=TradeDecision(
                action=TradeAction.SKIP,
                reasoning=self.skip_reason,
                skip_reason="strategy_skip",
            ),
            raw_response="",
            model_used="none",
        )

"""Base strategy class for forum-specific trading strategies.

Each forum can have its own strategy that determines how signals are processed.
Strategies can use LLM analysis, hardcoded rules, or a combination.

IMPORTANT: Strategy configurations should come from Redis (dashboard settings),
not hardcoded values. The StrategyConfig class provides defaults that are
overridden by Redis config at runtime.
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

    Values here are DEFAULTS that get overridden by Redis config.
    The actual runtime values come from:
    1. Redis config (dashboard) - highest priority
    2. Strategy defaults (this class) - fallback
    """
    # Ticker filters - EMPTY means use global Redis config
    # If set here, they EXTEND (not replace) the global config
    whitelist_tickers: List[str] = field(default_factory=list)
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

    # Strategy configuration (set in __init__ or subclass)
    config: StrategyConfig = None

    def __init__(self):
        """Initialize strategy with default config."""
        if self.config is None:
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

    def validate_ticker(self, signal: Signal, context: Dict[str, Any] = None) -> Optional[str]:
        """Validate ticker against whitelist/blacklist from Redis config.

        Priority:
        1. Redis config (dashboard settings) - if set
        2. Strategy config (fallback) - only if Redis is empty

        Args:
            signal: The trading signal
            context: Context containing trading_config from Redis

        Returns:
            Error message if validation fails, None if passed
        """
        ticker = signal.ticker
        if not ticker:
            return None  # No ticker to validate

        ticker = ticker.upper()

        # Get config from Redis (dashboard) via context
        trading_config = context.get("trading_config") if context else None

        # Determine effective whitelist/blacklist
        # Priority: Redis config > Strategy config (only if Redis is empty)
        whitelist = []
        blacklist = []

        if trading_config:
            # Get from Redis config (dashboard settings)
            redis_whitelist = trading_config.whitelist_tickers or []
            redis_blacklist = trading_config.blacklist_tickers or []

            # Use Redis config if set, otherwise fall back to strategy config
            whitelist = redis_whitelist if redis_whitelist else self.config.whitelist_tickers
            blacklist = redis_blacklist if redis_blacklist else self.config.blacklist_tickers
        else:
            # No Redis config available, use strategy defaults
            whitelist = self.config.whitelist_tickers
            blacklist = self.config.blacklist_tickers

        # Check whitelist (if set - empty list means all allowed)
        if whitelist:
            if ticker not in [t.upper() for t in whitelist]:
                return f"Ticker {ticker} not in whitelist: {whitelist}"

        # Check blacklist
        if blacklist:
            if ticker in [t.upper() for t in blacklist]:
                return f"Ticker {ticker} is blacklisted"

        return None

    def pre_check(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        """Run strategy-specific pre-checks before execution.

        Override this to add custom validation logic.

        Args:
            signal: The trading signal
            context: Shared context dict (contains trading_config from Redis)

        Returns:
            Error message if check fails, None if passed
        """
        # Check if strategy is enabled
        if not self.config.enabled:
            return f"Strategy '{self.name}' is disabled"

        # Validate ticker against Redis config (dashboard settings)
        ticker_error = self.validate_ticker(signal, context)
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

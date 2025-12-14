"""Strategy system for forum-specific trading logic.

This module provides:
- StrategyManager: Routes signals to appropriate forum strategies
- Strategy base classes: For creating custom strategies
- Forum strategies: Pre-configured strategies for each forum
"""

import logging
from typing import Any, Dict, List, Optional, Type

from domain.models.signal import Signal
from domain.models.trade import AIResponse, TradeAction, TradeDecision
from domain.strategies.base import Strategy, StrategyConfig, SkipStrategy
from domain.strategies.llm_strategy import LlmStrategy
from domain.strategies.forums import ALL_STRATEGIES

logger = logging.getLogger(__name__)


class StrategyManager:
    """Manages and routes signals to forum-specific strategies.

    Similar to how PreconditionManager works, but for execution strategies.
    Each forum can have its own strategy (LLM-based, hardcoded, or skip).
    """

    def __init__(self, strategies: List[Type[Strategy]] = None):
        """Initialize strategy manager.

        Args:
            strategies: List of strategy classes to use. Defaults to ALL_STRATEGIES.
        """
        strategy_classes = strategies or ALL_STRATEGIES
        self._strategies: List[Strategy] = [cls() for cls in strategy_classes]
        self._default_strategy = SkipStrategy(reason="No strategy configured for this forum")

        logger.info(f"StrategyManager initialized with {len(self._strategies)} strategies")
        for s in self._strategies:
            logger.debug(f"  - {s.name}: {s.forum_name_pattern or s.forum_id}")

    @property
    def strategies(self) -> List[Strategy]:
        """Get all registered strategies."""
        return self._strategies

    def get_strategy(self, signal: Signal) -> Strategy:
        """Get the strategy for a given signal based on its forum.

        Args:
            signal: The trading signal

        Returns:
            Matching strategy or default skip strategy
        """
        for strategy in self._strategies:
            if strategy.matches(signal):
                logger.debug(f"Matched strategy '{strategy.name}' for forum '{signal.forum_name}'")
                return strategy

        logger.warning(f"No strategy found for forum '{signal.forum_name}' (ID: {signal.forum_id})")
        return self._default_strategy

    def execute(self, signal: Signal, context: Dict[str, Any]) -> AIResponse:
        """Execute the appropriate strategy for a signal.

        This is the main entry point for signal processing.

        Args:
            signal: The trading signal
            context: Shared context containing broker, market_data, etc.

        Returns:
            AIResponse with the decision
        """
        strategy = self.get_strategy(signal)

        logger.info(f"📊 Using strategy: {strategy.name}")

        # Run strategy-specific pre-checks
        pre_check_error = strategy.pre_check(signal, context)
        if pre_check_error:
            logger.warning(f"⚠️ Strategy pre-check failed: {pre_check_error}")
            return AIResponse(
                decision=TradeDecision(
                    action=TradeAction.SKIP,
                    reasoning=pre_check_error,
                    skip_reason="strategy_pre_check",
                ),
                raw_response="",
                model_used="none",
            )

        # Execute the strategy
        try:
            return strategy.execute(signal, context)
        except Exception as e:
            logger.error(f"Strategy execution failed: {e}", exc_info=True)
            return AIResponse(
                decision=TradeDecision(
                    action=TradeAction.SKIP,
                    reasoning=f"Strategy execution error: {e}",
                    skip_reason="strategy_error",
                ),
                raw_response="",
                model_used="none",
            )

    def list_strategies(self) -> List[Dict[str, Any]]:
        """List all registered strategies with their configurations.

        Returns:
            List of strategy info dicts
        """
        return [
            {
                "name": s.name,
                "description": s.description,
                "forum_id": s.forum_id,
                "forum_pattern": s.forum_name_pattern,
                "enabled": s.config.enabled if hasattr(s, 'config') else True,
                "use_llm": s.config.use_llm if hasattr(s, 'config') else False,
            }
            for s in self._strategies
        ]


# Export commonly used classes
__all__ = [
    "StrategyManager",
    "Strategy",
    "StrategyConfig",
    "SkipStrategy",
    "LlmStrategy",
]

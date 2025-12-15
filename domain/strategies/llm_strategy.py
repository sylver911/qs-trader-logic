"""LLM-based trading strategy.

This strategy uses an LLM to analyze signals and make trading decisions.
It encapsulates the current AI analysis logic from trading_service.py.

Prefetched data is available in Jinja2 templates via:
    {{ time.is_market_open }}
    {{ account.buying_power }}
    {{ option_chain.calls[0].strike }}
    {{ positions.count }}
    {{ vix.value }}
"""

import json
import logging
from typing import Any, Dict, Optional

from domain.models.signal import Signal
from domain.models.trade import AIResponse, TradeAction, TradeDecision, TradeResult
from domain.strategies.base import Strategy, StrategyConfig
from domain.prefetches import PrefetchManager
from infrastructure.ai.llm_client import LLMClient
from infrastructure.storage.trades_repository import trades_repo
from tools.order_tools import OrderTools
from tools.schedule_tools import ScheduleTools

logger = logging.getLogger(__name__)


class LlmStrategy(Strategy):
    """Base LLM strategy that uses AI to analyze signals.

    Subclass this to create forum-specific LLM strategies with
    different configurations (prompts, models, risk params).

    Prefetched data is automatically available in Jinja2 templates:
        {{ time.is_market_open }}
        {{ account.buying_power }}
        {{ option_chain.calls[0].strike }}
        {{ positions.count }}
        {{ vix.value }}
    """

    name = "llm_base"
    description = "LLM-based signal analysis strategy"

    def __init__(self):
        super().__init__()
        self._llm = LLMClient()
        self._prefetch_manager = PrefetchManager()

    def execute(self, signal: Signal, context: Dict[str, Any]) -> AIResponse:
        """Execute LLM-based analysis on the signal.

        Args:
            signal: The trading signal
            context: Contains broker, market_data, trading_config, etc.

        Returns:
            AIResponse with the decision
        """
        broker = context.get("broker")
        trading_config = context.get("trading_config")
        scheduled_context = context.get("scheduled_context")

        # Initialize tools with broker
        order_tools = OrderTools(broker)
        schedule_tools = ScheduleTools()

        # Pre-fetch all data using PrefetchManager (parallel execution)
        prefetch_context = self._prefetch_manager.fetch_all(signal, context)

        # Convert to template-ready dict for LLM
        prefetched_data = prefetch_context.to_template_context()

        # Get portfolio data from prefetch (for backward compatibility)
        account_data = prefetched_data.get("account", {})
        positions_data = prefetched_data.get("positions", {})
        portfolio_data = {
            "cash": account_data.get("available", 10000),
            "buying_power": account_data.get("buying_power", 20000),
            "positions": positions_data.get("items", []),
            "pnl": positions_data.get("total_unrealized_pnl", 0),
        }

        # Prepare market data
        market_data = {"symbol": signal.ticker, "timestamp": ""} if signal.ticker else {}

        # Get trading params - use strategy config overrides if set
        trading_params = trading_config.get_all()

        # Override with strategy-specific settings
        if self.config.llm_model:
            trading_params["current_llm_model"] = self.config.llm_model
        if self.config.whitelist_tickers:
            trading_params["whitelist_tickers"] = self.config.whitelist_tickers
        if self.config.blacklist_tickers:
            trading_params["blacklist_tickers"] = self.config.blacklist_tickers

        # Decision tools only
        tools = (
            OrderTools.get_tool_definitions()
            + ScheduleTools.get_tool_definitions()
        )
        handlers = {
            **order_tools.get_handlers(),
            **schedule_tools.get_handlers(),
        }

        retry_count = scheduled_context.get("retry_count", 0) if scheduled_context else 0

        # Single LLM call with prefetched data
        response = self._llm.analyze_signal(
            signal_data=signal.to_dict(),
            market_data=market_data,
            portfolio_data=portfolio_data,
            trading_params=trading_params,
            tools=tools,
            scheduled_context=scheduled_context,
            prefetched_data=prefetched_data,
        )

        trace_id = response.get("request_id")

        # Process response
        return self._process_llm_response(
            response=response,
            signal=signal,
            handlers=handlers,
            retry_count=retry_count,
            trace_id=trace_id,
            trading_config=trading_config,
        )

    def _process_llm_response(
        self,
        response: Dict[str, Any],
        signal: Signal,
        handlers: Dict[str, callable],
        retry_count: int,
        trace_id: Optional[str],
        trading_config: Any,
    ) -> AIResponse:
        """Process LLM response and execute tool calls."""

        # No tool call → auto-skip
        if not response.get("tool_calls"):
            logger.info("   ⏭️ AI did not call any tool - auto-skip")
            return AIResponse(
                decision=TradeDecision(
                    action=TradeAction.SKIP,
                    reasoning=response.get("content", "AI did not make a decision"),
                    skip_reason="no_decision",
                ),
                raw_response=response.get("content", ""),
                model_used=response.get("model", ""),
                trace_id=trace_id,
            )

        # Execute the first tool call
        call = response["tool_calls"][0]
        func_name = call["function"]
        args = call["arguments"]

        logger.info(f"   🔧 AI called: {func_name}")

        handler = handlers.get(func_name)
        if not handler:
            logger.warning(f"Unknown tool: {func_name}")
            return AIResponse(
                decision=TradeDecision(
                    action=TradeAction.SKIP,
                    reasoning=f"Unknown tool called: {func_name}",
                    skip_reason="tool_error",
                ),
                raw_response=json.dumps({"error": f"Unknown tool: {func_name}"}),
                model_used=response.get("model", ""),
                trace_id=trace_id,
            )

        # Inject context for schedule_reanalysis
        if func_name == "schedule_reanalysis":
            args["_thread_id"] = signal.thread_id
            args["_thread_name"] = signal.thread_name or signal.tickers_raw
            args["_previous_tools"] = []
            args["_retry_count"] = retry_count
            args["_signal_data"] = signal.to_dict()

        try:
            tool_result = handler(**args)
        except Exception as e:
            logger.error(f"Tool {func_name} failed: {e}")
            return AIResponse(
                decision=TradeDecision(
                    action=TradeAction.SKIP,
                    reasoning=f"Tool execution failed: {e}",
                    skip_reason="tool_error",
                ),
                raw_response=json.dumps({"error": str(e)}),
                model_used=response.get("model", ""),
                trace_id=trace_id,
            )

        # Handle each decision tool type
        if func_name == "schedule_reanalysis":
            logger.info(f"   ⏰ AI scheduled reanalysis: {tool_result.get('reason', 'N/A')}")
            return AIResponse(
                decision=TradeDecision(
                    action=TradeAction.DELAY,
                    reasoning=tool_result.get("reason", "Scheduled for reanalysis"),
                    skip_reason=None,
                ),
                raw_response=json.dumps(tool_result),
                model_used=response.get("model", ""),
                trace_id=trace_id,
                delay_info={
                    "reanalyze_at": tool_result.get("reanalyze_at"),
                    "delay_minutes": tool_result.get("delay_minutes"),
                    "question": tool_result.get("question"),
                },
            )

        if func_name == "skip_signal":
            logger.info(f"   ⏭️ AI called skip_signal: {tool_result.get('reason', 'No reason')}")
            return AIResponse(
                decision=TradeDecision(
                    action=TradeAction.SKIP,
                    reasoning=tool_result.get("reason", "AI decided to skip"),
                    skip_reason=tool_result.get("category", "other"),
                ),
                raw_response=json.dumps(tool_result),
                model_used=response.get("model", ""),
                trace_id=trace_id,
            )

        if func_name == "place_bracket_order":
            logger.info(f"   💰 AI called place_bracket_order")
            return self._handle_bracket_order(
                tool_result=tool_result,
                args=args,
                response=response,
                signal=signal,
                trace_id=trace_id,
                trading_config=trading_config,
            )

        # Fallback for unknown decision tool
        logger.warning(f"Unexpected tool: {func_name}")
        return AIResponse(
            decision=TradeDecision(
                action=TradeAction.SKIP,
                reasoning=f"Unexpected tool called: {func_name}",
                skip_reason="tool_error",
            ),
            raw_response=json.dumps(tool_result),
            model_used=response.get("model", ""),
            trace_id=trace_id,
        )

    def _handle_bracket_order(
        self,
        tool_result: Dict[str, Any],
        args: Dict[str, Any],
        response: Dict[str, Any],
        signal: Signal,
        trace_id: Optional[str],
        trading_config: Any,
    ) -> AIResponse:
        """Handle place_bracket_order tool result."""

        # Extract order ID from result
        order_data = tool_result.get("order")
        order_id = None
        if order_data:
            if isinstance(order_data, list) and len(order_data) > 0:
                first_order = order_data[0] if isinstance(order_data[0], dict) else {}
                order_id = str(first_order.get("order_id", "")) if first_order.get("order_id") else None
            elif isinstance(order_data, dict):
                order_id = str(order_data.get("order_id", "")) if order_data.get("order_id") else None

        trade_result = TradeResult(
            success=tool_result.get("success", False),
            order_id=order_id,
            error=tool_result.get("error"),
        )

        # Save trade to P&L tracking if successful (both live and dry run)
        if trade_result.success:
            is_simulated = tool_result.get("simulated", False)
            product = tool_result.get("product", {})
            trade_data = {
                "thread_id": signal.thread_id,
                "ticker": tool_result.get("symbol"),
                "direction": args.get("side"),
                "entry_price": args.get("entry_price"),
                "quantity": args.get("quantity"),
                "take_profit": args.get("take_profit"),
                "stop_loss": args.get("stop_loss"),
                "order_id": trade_result.order_id,
                "conid": tool_result.get("conid"),
                "model_used": response.get("model", ""),
                "product": product,
                "simulated": is_simulated,
            }
            trade_id = trades_repo.save_trade(trade_data)
            trade_result.trade_id = trade_id
            trade_result.simulated = is_simulated

        return AIResponse(
            decision=TradeDecision(
                action=TradeAction.EXECUTE,
                reasoning="AI placed bracket order via tool call",
                confidence=0.8,
                modified_entry=args.get("entry_price"),
                modified_target=args.get("take_profit"),
                modified_stop_loss=args.get("stop_loss"),
                modified_size=args.get("quantity"),
            ),
            raw_response=json.dumps(tool_result),
            model_used=response.get("model", ""),
            trace_id=trace_id,
            trade_result=trade_result,
        )

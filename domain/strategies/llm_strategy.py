"""LLM-based trading strategy.

This strategy uses an LLM to analyze signals and make trading decisions.
It encapsulates the current AI analysis logic from trading_service.py.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Optional

from domain.models.signal import Signal
from domain.models.trade import AIResponse, TradeAction, TradeDecision, TradeResult
from domain.strategies.base import Strategy, StrategyConfig
from infrastructure.ai.llm_client import LLMClient
from infrastructure.storage.trades_repository import trades_repo
from tools.order_tools import OrderTools
from tools.schedule_tools import ScheduleTools
from tools.market_tools import MarketTools
from tools.portfolio_tools import PortfolioTools

logger = logging.getLogger(__name__)


class LlmStrategy(Strategy):
    """Base LLM strategy that uses AI to analyze signals.

    Subclass this to create forum-specific LLM strategies with
    different configurations (prompts, models, risk params).
    """

    name = "llm_base"
    description = "LLM-based signal analysis strategy"

    def __init__(self):
        super().__init__()
        self._llm = LLMClient()
        # Tools are initialized when execute() is called with context

    def execute(self, signal: Signal, context: Dict[str, Any]) -> AIResponse:
        """Execute LLM-based analysis on the signal.

        Args:
            signal: The trading signal
            context: Contains broker, market_data, trading_config, etc.

        Returns:
            AIResponse with the decision
        """
        broker = context.get("broker")
        market_data_provider = context.get("market_data")
        trading_config = context.get("trading_config")
        scheduled_context = context.get("scheduled_context")

        # Initialize tools with broker
        market_tools = MarketTools(market_data_provider)
        portfolio_tools = PortfolioTools(broker)
        order_tools = OrderTools(broker)
        schedule_tools = ScheduleTools()

        # Pre-fetch market data
        prefetched_data = self._prefetch_tool_data(signal, market_tools, portfolio_tools)

        # Get portfolio data
        if trading_config.execute_orders:
            portfolio = portfolio_tools.get_portfolio_summary()
            portfolio_data = portfolio.to_dict() if portfolio else {}
        else:
            portfolio_data = {"positions": [], "cash": 10000, "pnl": 0}

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

        # Single LLM call
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

    def _prefetch_tool_data(
        self,
        signal: Signal,
        market_tools: MarketTools,
        portfolio_tools: PortfolioTools,
    ) -> Dict[str, Any]:
        """Pre-fetch all tool data in parallel."""
        data = {}
        market_handlers = market_tools.get_handlers()
        portfolio_handlers = portfolio_tools.get_handlers()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}

            # 1. Current time
            futures[executor.submit(market_handlers["get_current_time"])] = "time"

            # 2. Option chain (if ticker known)
            if signal.ticker:
                if signal.expiry:
                    futures[executor.submit(
                        market_handlers["get_option_chain"],
                        symbol=signal.ticker,
                        expiry=signal.expiry
                    )] = "option_chain"
                else:
                    futures[executor.submit(
                        market_handlers["get_option_chain"],
                        symbol=signal.ticker
                    )] = "option_chain"

            # 3. Account summary
            futures[executor.submit(portfolio_handlers["get_account_summary"])] = "account"

            # 4. Current positions
            futures[executor.submit(portfolio_handlers["get_positions"])] = "positions"

            # Collect results
            for future in as_completed(futures):
                key = futures[future]
                try:
                    data[key] = future.result()
                    logger.debug(f"   ✓ Prefetch {key}")
                except Exception as e:
                    logger.warning(f"   ✗ Prefetch {key} failed: {e}")
                    data[key] = {"error": str(e)}

        return data

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

        # Save trade to P&L tracking if successful
        if trade_result.success and trading_config.execute_orders:
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
            }
            trade_id = trades_repo.save_trade(trade_data)
            trade_result.trade_id = trade_id

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

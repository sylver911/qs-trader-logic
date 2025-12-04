"""Trading service - main business logic."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from config.settings import config
from config.redis_config import trading_config
from domain.models.signal import Signal
from domain.models.trade import TradeAction, TradeDecision, AIResponse, TradeResult
from infrastructure.storage.mongo import MongoHandler
from infrastructure.broker.ibkr_client import IBKRBroker
from infrastructure.broker.market_data import MarketDataProvider
from infrastructure.ai.llm_client import LLMClient
from tools.market_tools import MarketTools
from tools.portfolio_tools import PortfolioTools
from tools.order_tools import OrderTools

logger = logging.getLogger(__name__)


def json_serializer(obj: Any) -> Any:
    """Custom JSON serializer for non-standard types.

    Handles:
    - pandas Timestamp -> ISO string
    - datetime -> ISO string
    - numpy types -> Python native types
    """
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, 'item'):  # numpy types
        return obj.item()
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')


class TradingService:
    """Main trading service orchestrating signal analysis and execution."""

    def __init__(self):
        """Initialize trading service."""
        self._broker = IBKRBroker()
        self._market_data = MarketDataProvider(self._broker)
        self._llm = LLMClient()

        # Tools
        self._market_tools = MarketTools(self._market_data)
        self._portfolio_tools = PortfolioTools(self._broker)
        self._order_tools = OrderTools(self._broker)

    def process_signal(self, task: Dict[str, Any]) -> bool:
        """Process a signal from the queue.

        Args:
            task: Task data from Redis queue

        Returns:
            True if processed successfully
        """
        thread_id = task.get("thread_id", "")
        thread_name = task.get("thread_name", "")

        logger.info(f"Processing signal: {thread_name} ({thread_id})")

        try:
            # 1. Load signal from MongoDB
            signal = self._load_signal(thread_id)
            if not signal:
                logger.error(f"Signal not found: {thread_id}")
                return False

            # 2. Validate pre-conditions
            validation_error = self._validate_preconditions(signal)
            if validation_error:
                logger.warning(f"Validation failed: {validation_error}")
                self._save_skip_result(signal, validation_error)
                return True

            # 3. Get market data
            market_data = self._get_market_data(signal.ticker)

            # 4. Get portfolio state (skip in dry run)
            if trading_config.execute_orders:
                portfolio = self._portfolio_tools.get_portfolio_summary()
                portfolio_data = portfolio.to_dict() if portfolio else {}
            else:
                logger.debug("Dry run mode - using empty portfolio")
                portfolio_data = {"positions": [], "cash": 100000, "pnl": 0}

            # 5. Analyze with AI
            ai_response = self._analyze_with_ai(signal, market_data, portfolio_data)

            # 6. Execute if needed
            if ai_response.decision.action == TradeAction.EXECUTE:
                trade_result = self._execute_trade(signal, ai_response)
                ai_response.trade_result = trade_result

            # 7. Save result to MongoDB
            self._save_result(signal, ai_response)

            logger.info(
                f"Signal processed: {thread_name} -> {ai_response.decision.action.value}"
            )
            return True

        except Exception as e:
            logger.error(f"Error processing signal {thread_id}: {e}", exc_info=True)
            return False

    def _load_signal(self, thread_id: str) -> Optional[Signal]:
        """Load signal from MongoDB."""
        with MongoHandler() as mongo:
            doc = mongo.find_one(
                config.THREADS_COLLECTION,
                query={"thread_id": thread_id},
            )
            if doc:
                return Signal.from_mongo_doc(doc)
        return None

    def _validate_preconditions(self, signal: Signal) -> Optional[str]:
        """Validate trading preconditions."""
        if trading_config.emergency_stop:
            return "Emergency stop is active"

        ticker = signal.ticker

        # If no parsed ticker but we have raw ticker info, let LLM handle it
        if not ticker and signal.tickers_raw:
            logger.info(f"No clean ticker parsed, but have raw: {signal.tickers_raw} - letting LLM decide")
            # Don't fail validation - LLM will figure it out from raw or content
            ticker = signal.tickers_raw.split(',')[0].strip() if signal.tickers_raw else None

        if not ticker:
            # Check if there's enough info in the signal content for LLM
            if signal.get_full_content() and len(signal.get_full_content()) > 50:
                logger.info("No ticker found but signal has content - letting LLM analyze")
                return None  # Let LLM try to figure it out
            return "No ticker found in signal and insufficient content"

        # Validate ticker format (basic sanity check) - but be lenient
        if ticker and not self._is_valid_ticker(ticker):
            # Log but don't fail - maybe LLM can work with the raw content
            logger.warning(f"Ticker '{ticker}' may be invalid, but proceeding for LLM analysis")

        whitelist = trading_config.whitelist_tickers
        if whitelist and ticker and ticker not in whitelist:
            return f"Ticker {ticker} not in whitelist"

        blacklist = trading_config.blacklist_tickers
        if ticker and ticker in blacklist:
            return f"Ticker {ticker} is blacklisted"

        if signal.confidence and signal.confidence < trading_config.min_ai_confidence_score:
            return f"Signal confidence {signal.confidence:.0%} below minimum"

        # Skip IBKR checks in dry run mode
        if not trading_config.execute_orders:
            logger.debug("Dry run mode - skipping IBKR validation")
            return None

        vix = self._market_data.get_vix()
        if vix and vix > trading_config.max_vix_level:
            return f"VIX {vix:.1f} above maximum {trading_config.max_vix_level}"

        positions = self._broker.get_positions()
        if len(positions) >= trading_config.max_concurrent_positions:
            return f"Max concurrent positions reached"

        return None

    def _is_valid_ticker(self, ticker: str) -> bool:
        """Validate ticker format.

        Args:
            ticker: Ticker symbol to validate

        Returns:
            True if ticker appears valid
        """
        if not ticker:
            return False

        # Must be 1-5 uppercase letters (standard US tickers)
        # Or 1-6 for some ETFs like GOOGL, NVDA
        if not ticker.isalpha():
            return False

        if len(ticker) > 6:
            return False

        # Blacklist obvious non-ticker words
        invalid_tickers = {
            'EXPLOSIVE', 'WSB', 'YOLO', 'HODL', 'MOON', 'APE',
            'STONK', 'STONKS', 'ALERT', 'SIGNAL', 'BUY', 'SELL',
            'CALL', 'PUT', 'OPTIONS', 'TRADING', 'STOCK', 'STOCKS',
            'UPDATE', 'NEWS', 'BREAKING', 'URGENT', 'HOT', 'NEW',
        }

        if ticker.upper() in invalid_tickers:
            return False

        return True

    def _get_market_data(self, ticker: str) -> Dict[str, Any]:
        """Get market data for a ticker."""
        if not ticker:
            return {}
        return self._market_data.get_market_data(ticker)

    def _analyze_with_ai(
        self,
        signal: Signal,
        market_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
    ) -> AIResponse:
        """Analyze signal with AI with iterative tool calling."""
        tools = (
            MarketTools.get_tool_definitions()
            + PortfolioTools.get_tool_definitions()
            + OrderTools.get_tool_definitions()
        )

        handlers = {
            **self._market_tools.get_handlers(),
            **self._portfolio_tools.get_handlers(),
            **self._order_tools.get_handlers(),
        }

        trading_params = trading_config.get_all()

        # Initial call
        response = self._llm.analyze_signal(
            signal_data=signal.to_dict(),
            market_data=market_data,
            portfolio_data=portfolio_data,
            trading_params=trading_params,
            tools=tools,
        )

        # Build message history for multi-turn
        messages = [
            {"role": "system", "content": self._llm._get_system_prompt()},
            {"role": "user", "content": response.get("_prompt", "")},
        ]

        # Iterative tool calling loop (max 10 iterations to prevent infinite loops)
        max_iterations = 10
        iteration = 0

        while response.get("tool_calls") and iteration < max_iterations:
            iteration += 1
            logger.info(f"Tool call iteration {iteration}")

            # Execute tool calls
            tool_results = self._llm.execute_tool_calls(
                response["tool_calls"],
                handlers,
            )

            for result in tool_results:
                if result["success"]:
                    logger.info(f"Tool executed: {result['function']} -> {str(result.get('result', ''))[:100]}")
                else:
                    logger.warning(f"Tool failed: {result['function']} - {result.get('error')}")

            # Add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": response.get("content", ""),
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"],
                            "arguments": json.dumps(tc["arguments"]),
                        }
                    }
                    for tc in response["tool_calls"]
                ],
            })

            # Add tool results - USE CUSTOM SERIALIZER for Timestamp handling
            for result in tool_results:
                try:
                    result_content = result.get("result") if result["success"] else {"error": result.get("error")}
                    # Use custom serializer to handle pandas Timestamp
                    serialized_content = json.dumps(result_content, default=json_serializer)
                except TypeError as e:
                    logger.warning(f"Serialization error for {result.get('function')}: {e}")
                    serialized_content = json.dumps({"error": f"Serialization error: {str(e)}"})

                messages.append({
                    "role": "tool",
                    "tool_call_id": result["call_id"],
                    "content": serialized_content,
                })

            # Continue with tool results
            response = self._llm.continue_with_tool_results(
                original_messages=messages,
                tool_results=tool_results,
                tools=tools,
            )

        if iteration >= max_iterations:
            logger.warning(f"Max tool call iterations ({max_iterations}) reached")

        # Parse final decision
        decision = self._parse_decision(response.get("content", ""))

        return AIResponse(
            decision=decision,
            raw_response=response.get("content", ""),
            model_used=response.get("model", ""),
        )

    def _parse_decision(self, content: str) -> TradeDecision:
        """Parse AI decision from response."""
        try:
            start = content.find("{")
            end = content.rfind("}") + 1

            if start >= 0 and end > start:
                json_str = content[start:end]
                data = json.loads(json_str)

                action_str = data.get("action", "skip").lower()
                action = TradeAction(action_str) if action_str in ["skip", "execute", "modify"] else TradeAction.SKIP

                # FIX: Handle None modified_params safely
                modified_params = data.get("modified_params") or {}

                return TradeDecision(
                    action=action,
                    reasoning=data.get("reasoning", ""),
                    confidence=float(data.get("confidence", 0)),
                    modified_entry=modified_params.get("entry_price"),
                    modified_target=modified_params.get("target_price"),
                    modified_stop_loss=modified_params.get("stop_loss"),
                    modified_size=modified_params.get("size"),
                    skip_reason=data.get("reasoning") if action == TradeAction.SKIP else None,
                )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse AI response: {e}")

        return TradeDecision(
            action=TradeAction.SKIP,
            reasoning="Failed to parse AI response",
            skip_reason="Parse error",
        )

    def _execute_trade(self, signal: Signal, ai_response: AIResponse) -> TradeResult:
        """Execute a trade based on AI decision."""
        decision = ai_response.decision

        entry = decision.modified_entry or signal.entry_price
        target = decision.modified_target or signal.target_price
        stop_loss = decision.modified_stop_loss or signal.stop_loss

        if not all([signal.ticker, entry, target, stop_loss]):
            return TradeResult(success=False, error="Missing required trade parameters")

        quantity = 1  # TODO: Calculate based on portfolio

        # Check if we should actually execute or just simulate
        if not trading_config.execute_orders:
            logger.info(f"[DRY RUN] Would execute: {signal.ticker} @ {entry} | TP: {target} | SL: {stop_loss}")
            return TradeResult(
                success=True,
                order_id="DRY_RUN_SIMULATED",
                simulated=True,
            )

        try:
            result = self._order_tools.place_bracket_order(
                symbol=signal.ticker,
                side="BUY" if signal.direction in ["CALL", "BUY"] else "SELL",
                quantity=quantity,
                entry_price=entry,
                take_profit=target,
                stop_loss=stop_loss,
            )

            if result.get("success"):
                logger.info(f"Trade executed: {signal.ticker} @ {entry}")
                return TradeResult(
                    success=True,
                    order_id=str(result.get("order", {}).get("order_id", "")),
                )
            else:
                return TradeResult(success=False, error=result.get("error", "Unknown error"))

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            return TradeResult(success=False, error=str(e))

    def _save_result(self, signal: Signal, ai_response: AIResponse) -> None:
        """Save AI result to MongoDB."""
        with MongoHandler() as mongo:
            ai_data = ai_response.to_mongo_update()
            mongo.update_one(
                config.THREADS_COLLECTION,
                query={"thread_id": signal.thread_id},
                update_data={
                    "ai_processed": True,
                    "ai_processed_at": datetime.now().isoformat(),
                    "ai_result": ai_data,
                },
            )
        logger.debug(f"Saved AI result for {signal.thread_id}")

    def _save_skip_result(self, signal: Signal, reason: str) -> None:
        """Save skip result to MongoDB."""
        with MongoHandler() as mongo:
            mongo.update_one(
                config.THREADS_COLLECTION,
                query={"thread_id": signal.thread_id},
                update_data={
                    "ai_processed": True,
                    "ai_processed_at": datetime.now().isoformat(),
                    "ai_result": {
                        "act": "skip",
                        "reasoning": reason,
                        "decision": {"action": "skip", "skip_reason": reason},
                    },
                },
            )
"""Trading service - main business logic - QS Optimized Version."""

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
from tools.schedule_tools import ScheduleTools

logger = logging.getLogger(__name__)


def json_serializer(obj: Any) -> Any:
    """Custom JSON serializer for non-standard types."""
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, 'item'):
        return obj.item()
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')


class TradingService:
    """Main trading service orchestrating signal analysis and execution."""

    def __init__(self):
        """Initialize trading service."""
        self._broker = IBKRBroker()
        self._market_data = MarketDataProvider(self._broker)
        self._llm = LLMClient()

        self._market_tools = MarketTools(self._market_data)
        self._portfolio_tools = PortfolioTools(self._broker)
        self._order_tools = OrderTools(self._broker)
        self._schedule_tools = ScheduleTools()

    def process_signal(self, task: Dict[str, Any]) -> bool:
        """Process a signal from the queue.
        
        Args:
            task: Queue task containing thread_id and optional scheduled_context
        """
        thread_id = task.get("thread_id", "")
        thread_name = task.get("thread_name", "")
        scheduled_context = task.get("scheduled_context")  # Present if this is a reanalysis

        logger.info("=" * 50)
        if scheduled_context:
            retry_count = scheduled_context.get("retry_count", 1)
            logger.info(f"🔄 SCHEDULED REANALYSIS #{retry_count}: {thread_name}")
            logger.info(f"   Reason: {scheduled_context.get('delay_reason', 'N/A')}")
            logger.info(f"   Question: {scheduled_context.get('delay_question', 'N/A')}")
        else:
            logger.info(f"📥 SIGNAL RECEIVED: {thread_name}")
        logger.info(f"   Thread ID: {thread_id}")

        try:
            signal = self._load_signal(thread_id)
            if not signal:
                logger.error(f"❌ Signal not found in MongoDB: {thread_id}")
                return False

            logger.info(f"   Ticker: {signal.ticker or 'N/A'} | Direction: {signal.direction or 'N/A'}")
            if signal.entry_price:
                logger.info(f"   Entry: ${signal.entry_price} | Target: ${signal.target_price} | SL: ${signal.stop_loss}")

            validation_error = self._validate_preconditions(signal)
            if validation_error:
                logger.warning(f"⚠️ Validation failed: {validation_error}")
                self._save_skip_result(signal, validation_error)
                logger.info(f"📋 DECISION: SKIP (validation) | {validation_error}")
                logger.info("=" * 50)
                return True

            # Get basic market data for context (non-blocking)
            market_data = self._get_market_data(signal.ticker)

            # Portfolio data for context
            if trading_config.execute_orders:
                portfolio = self._portfolio_tools.get_portfolio_summary()
                portfolio_data = portfolio.to_dict() if portfolio else {}
            else:
                logger.debug("Dry run mode - using simulated portfolio")
                portfolio_data = {"positions": [], "cash": 10000, "pnl": 0}

            # Let AI analyze and decide
            logger.info("🤖 Starting AI analysis...")
            ai_response = self._analyze_with_ai(signal, market_data, portfolio_data, scheduled_context)

            # Check for DELAY decision
            if ai_response.decision.action == TradeAction.DELAY:
                logger.info(f"⏰ DECISION: DELAY | {ai_response.decision.reasoning}")
                self._save_delay_result(signal, ai_response)
                logger.info("=" * 50)
                return True

            # Execute if AI decided to
            if ai_response.decision.action == TradeAction.EXECUTE:
                logger.info("💰 Executing trade...")
                trade_result = self._execute_trade(signal, ai_response)
                ai_response.trade_result = trade_result
                if trade_result.success:
                    logger.info(f"   ✅ Trade executed: {trade_result.order_id}")
                else:
                    logger.error(f"   ❌ Trade failed: {trade_result.error}")

            self._save_result(signal, ai_response)

            # Final decision summary
            decision = ai_response.decision
            action_emoji = "✅" if decision.action == TradeAction.EXECUTE else "⏭️"
            logger.info(f"📋 DECISION: {decision.action.value.upper()} | Confidence: {decision.confidence:.0%}")
            logger.info(f"{action_emoji} Reasoning: {decision.reasoning[:100]}..." if len(decision.reasoning) > 100 else f"{action_emoji} Reasoning: {decision.reasoning}")
            logger.info("=" * 50)
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
        """Validate trading preconditions.
        
        These are hard stops that don't need AI evaluation.
        """
        # Emergency stop - immediate block
        if trading_config.emergency_stop:
            return "Emergency stop is active"

        # Get ticker (try parsed, then raw)
        ticker = signal.ticker
        if not ticker and signal.tickers_raw:
            logger.info(f"No clean ticker, using raw: {signal.tickers_raw}")
            ticker = signal.tickers_raw.split(',')[0].strip() if signal.tickers_raw else None

        # No ticker and no content - can't process
        if not ticker:
            if signal.get_full_content() and len(signal.get_full_content()) > 50:
                logger.info("No ticker but has content - letting AI analyze")
                return None
            return "No ticker found and insufficient content"

        # Whitelist check
        whitelist = trading_config.whitelist_tickers
        if whitelist and ticker and ticker not in whitelist:
            return f"Ticker {ticker} not in whitelist: {whitelist}"

        # Blacklist check
        blacklist = trading_config.blacklist_tickers
        if ticker and ticker in blacklist:
            return f"Ticker {ticker} is blacklisted"

        # Low confidence from signal itself (not AI)
        if signal.confidence and signal.confidence < trading_config.min_ai_confidence_score:
            return f"Signal confidence {signal.confidence:.0%} below minimum {trading_config.min_ai_confidence_score:.0%}"

        # VIX check (only in live mode)
        if trading_config.execute_orders:
            vix = self._market_data.get_vix()
            if vix and vix > trading_config.max_vix_level:
                return f"VIX {vix:.1f} above maximum {trading_config.max_vix_level}"

            # Max positions check
            positions = self._broker.get_positions()
            if len(positions) >= trading_config.max_concurrent_positions:
                return f"Max concurrent positions ({trading_config.max_concurrent_positions}) reached"

        return None

    def _is_valid_ticker(self, ticker: str) -> bool:
        """Validate ticker format."""
        if not ticker:
            return False
        if not ticker.isalpha():
            return False
        if len(ticker) > 6:
            return False

        invalid_tickers = {
            'EXPLOSIVE', 'WSB', 'YOLO', 'HODL', 'MOON', 'APE',
            'STONK', 'STONKS', 'ALERT', 'SIGNAL', 'BUY', 'SELL',
            'CALL', 'PUT', 'OPTIONS', 'TRADING', 'STOCK', 'STOCKS',
        }
        return ticker.upper() not in invalid_tickers

    def _get_market_data(self, ticker: str) -> Dict[str, Any]:
        """Get market data for context (minimal)."""
        if not ticker:
            return {}
        return {"symbol": ticker, "timestamp": datetime.now().isoformat()}

    def _analyze_with_ai(
        self,
        signal: Signal,
        market_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
        scheduled_context: Dict[str, Any] = None,
    ) -> AIResponse:
        """Analyze signal with AI using iterative tool calling.
        
        Args:
            signal: The trading signal
            market_data: Current market data
            portfolio_data: Portfolio information
            scheduled_context: Context from previous analysis if this is a reanalysis
        """
        
        # Combine all tools (including schedule_reanalysis)
        tools = (
            MarketTools.get_tool_definitions()
            + PortfolioTools.get_tool_definitions()
            + OrderTools.get_tool_definitions()
            + ScheduleTools.get_tool_definitions()
        )

        handlers = {
            **self._market_tools.get_handlers(),
            **self._portfolio_tools.get_handlers(),
            **self._order_tools.get_handlers(),
            **self._schedule_tools.get_handlers(),
        }

        trading_params = trading_config.get_all()
        
        # Get retry count from scheduled context
        retry_count = scheduled_context.get("retry_count", 0) if scheduled_context else 0

        # Initial call
        response = self._llm.analyze_signal(
            signal_data=signal.to_dict(),
            market_data=market_data,
            portfolio_data=portfolio_data,
            trading_params=trading_params,
            tools=tools,
            scheduled_context=scheduled_context,  # Pass scheduled context to prompt
        )
        
        # Track request_id for trace linking (use last one from conversation)
        last_request_id = response.get("request_id")
        
        # Track tool calls for schedule_reanalysis context
        all_tool_calls = []

        # Build message history
        messages = [
            {"role": "system", "content": self._llm._get_system_prompt()},
            {"role": "user", "content": response.get("_prompt", "")},
        ]

        # Tool call tracking for efficiency
        tool_cache = {}  # Cache results to detect duplicates
        
        # Iterative tool calling loop
        max_iterations = 8
        iteration = 0
        total_tool_calls = 0

        while response.get("tool_calls") and iteration < max_iterations:
            iteration += 1
            num_calls = len(response["tool_calls"])
            total_tool_calls += num_calls
            tool_names = [tc["function"] for tc in response["tool_calls"]]
            logger.info(f"   🔧 Iteration {iteration}: {num_calls} tool call(s) - {', '.join(tool_names)}")

            # Execute tool calls
            tool_results = []
            for call in response["tool_calls"]:
                func_name = call["function"]
                args = call["arguments"]
                args_key = json.dumps(args, sort_keys=True, default=str)
                cache_key = f"{func_name}:{args_key}"
                
                # Check for duplicate calls
                if cache_key in tool_cache:
                    logger.debug(f"Tool {func_name} (CACHED - duplicate call)")
                    result = {
                        "call_id": call["id"],
                        "function": func_name,
                        "result": {
                            **tool_cache[cache_key],
                            "_warning": f"DUPLICATE CALL! You already called {func_name}. OUTPUT your decision NOW!"
                        },
                        "success": True,
                    }
                else:
                    # Execute new tool call
                    handler = handlers.get(func_name)
                    if handler:
                        try:
                            # Special handling for schedule_reanalysis - inject context
                            if func_name == "schedule_reanalysis":
                                args["_thread_id"] = signal.thread_id
                                args["_thread_name"] = signal.thread_name or signal.tickers_raw
                                args["_previous_tools"] = all_tool_calls
                                args["_retry_count"] = retry_count
                                args["_signal_data"] = signal.to_dict()
                            
                            tool_result = handler(**args)
                            tool_cache[cache_key] = tool_result
                            result = {
                                "call_id": call["id"],
                                "function": func_name,
                                "result": tool_result,
                                "success": True,
                            }
                            
                            # Track tool calls for context
                            all_tool_calls.append({
                                "name": func_name,
                                "arguments": args,
                                "result": tool_result,
                            })
                            
                            logger.debug(f"Tool {func_name} -> OK")
                            
                            # If schedule_reanalysis was called successfully, return DELAY
                            if func_name == "schedule_reanalysis" and tool_result.get("success"):
                                logger.info(f"   ⏰ AI scheduled reanalysis: {tool_result.get('reason', 'N/A')}")
                                return AIResponse(
                                    decision=TradeDecision(
                                        action=TradeAction.DELAY,
                                        reasoning=tool_result.get("reason", "Scheduled for reanalysis"),
                                        skip_reason=None,
                                    ),
                                    raw_response=json.dumps(tool_result),
                                    model_used=response.get("model", ""),
                                    trace_id=last_request_id,
                                    delay_info={
                                        "reanalyze_at": tool_result.get("reanalyze_at"),
                                        "delay_minutes": tool_result.get("delay_minutes"),
                                        "question": tool_result.get("question"),
                                    },
                                )
                            
                            # If skip_signal tool was called, return immediately with decision
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
                                    trace_id=last_request_id,
                                )
                            
                            # If place_bracket_order tool was called, return with execute decision
                            if func_name == "place_bracket_order":
                                logger.info(f"   💰 AI called place_bracket_order")
                                return AIResponse(
                                    decision=TradeDecision(
                                        action=TradeAction.EXECUTE,
                                        reasoning="AI placed bracket order",
                                        confidence=0.8,
                                        modified_entry=args.get("entry_price"),
                                        modified_target=args.get("take_profit"),
                                        modified_stop_loss=args.get("stop_loss"),
                                        modified_size=args.get("quantity"),
                                    ),
                                    raw_response=json.dumps(tool_result),
                                    model_used=response.get("model", ""),
                                    trace_id=last_request_id,
                                )
                        except Exception as e:
                            result = {
                                "call_id": call["id"],
                                "function": func_name,
                                "error": str(e),
                                "success": False,
                            }
                            logger.warning(f"Tool {func_name} -> ERROR: {e}")
                    else:
                        result = {
                            "call_id": call["id"],
                            "function": func_name,
                            "error": "Unknown function",
                            "success": False,
                        }
                        logger.warning(f"Unknown tool: {func_name}")
                
                tool_results.append(result)

            # Add assistant message with tool calls
            assistant_msg = {
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
            }
            # Add reasoning_content if present (required for DeepSeek Reasoner)
            if response.get("reasoning_content"):
                assistant_msg["reasoning_content"] = response["reasoning_content"]
            messages.append(assistant_msg)

            # Add tool results
            for result in tool_results:
                try:
                    result_content = result.get("result") if result["success"] else {"error": result.get("error")}
                    serialized_content = json.dumps(result_content, default=json_serializer)
                except TypeError as e:
                    logger.warning(f"Serialization error: {e}")
                    serialized_content = json.dumps({"error": f"Serialization error: {str(e)}"})

                messages.append({
                    "role": "tool",
                    "tool_call_id": result["call_id"],
                    "content": serialized_content,
                })

            # Add tool history reminder after 2+ unique tool calls
            if len(tool_cache) >= 2:
                tool_summary = "\n---\n## TOOLS ALREADY CALLED (DO NOT CALL AGAIN):\n"
                for cached_key, cached_result in tool_cache.items():
                    tool_name = cached_key.split(":")[0]
                    result_preview = json.dumps(cached_result, default=str)[:150]
                    tool_summary += f"- {tool_name}: {result_preview}...\n"
                tool_summary += "\nYou have the data. OUTPUT your JSON decision NOW!\n---"
                
                messages.append({
                    "role": "user",
                    "content": tool_summary
                })

            # Continue conversation
            response = self._llm.continue_with_tool_results(
                messages=messages,
                tools=tools,
            )
            
            # Update request_id (use the last one for trace linking)
            if response.get("request_id"):
                last_request_id = response["request_id"]

        if iteration >= max_iterations:
            logger.warning(f"⚠️ Max iterations ({max_iterations}) reached - forcing decision")

        # Log AI analysis summary
        logger.info(f"   📊 AI Analysis complete: {iteration} iteration(s), {total_tool_calls} tool call(s)")

        # Parse final decision
        decision = self._parse_decision(response.get("content", ""))

        return AIResponse(
            decision=decision,
            raw_response=response.get("content", ""),
            model_used=response.get("model", ""),
            trace_id=last_request_id,
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

                # Extract bracket parameters
                bracket = data.get("bracket") or {}
                
                return TradeDecision(
                    action=action,
                    reasoning=data.get("reasoning", ""),
                    confidence=float(data.get("confidence", 0)),
                    modified_entry=bracket.get("entry_price"),
                    modified_target=bracket.get("take_profit"),
                    modified_stop_loss=bracket.get("stop_loss"),
                    modified_size=bracket.get("quantity"),
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

        # Use AI's bracket parameters, fallback to signal
        entry = decision.modified_entry or signal.entry_price
        target = decision.modified_target or signal.target_price
        stop_loss = decision.modified_stop_loss or signal.stop_loss
        quantity = int(decision.modified_size) if decision.modified_size else 1

        if not all([signal.ticker, entry, target, stop_loss]):
            return TradeResult(success=False, error="Missing required trade parameters")

        # Dry run mode
        if not trading_config.execute_orders:
            logger.info(f"[DRY RUN] {signal.ticker} @ ${entry} | TP: ${target} | SL: ${stop_loss} | Qty: {quantity}")
            return TradeResult(
                success=True,
                order_id="DRY_RUN_SIMULATED",
                simulated=True,
            )

        # Live execution
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
                logger.info(f"Trade executed: {signal.ticker} @ ${entry}")
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
            update_data = {
                "ai_processed": True,
                "ai_processed_at": datetime.now().isoformat(),
                "ai_result": ai_data,
            }
            # Also save trace_id at thread root level for easy querying
            if ai_response.trace_id:
                update_data["trace_id"] = ai_response.trace_id
            mongo.update_one(
                config.THREADS_COLLECTION,
                query={"thread_id": signal.thread_id},
                update_data=update_data,
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

    def _save_delay_result(self, signal: Signal, ai_response: AIResponse) -> None:
        """Save delay result to MongoDB (signal scheduled for reanalysis)."""
        with MongoHandler() as mongo:
            ai_data = ai_response.to_mongo_update()
            update_data = {
                "ai_processed": True,  # Marked as processed (but with delay)
                "ai_processed_at": datetime.now().isoformat(),
                "ai_result": ai_data,
                "scheduled_reanalysis": ai_response.delay_info,
            }
            if ai_response.trace_id:
                update_data["trace_id"] = ai_response.trace_id
            mongo.update_one(
                config.THREADS_COLLECTION,
                query={"thread_id": signal.thread_id},
                update_data=update_data,
            )
        logger.debug(f"Saved delay result for {signal.thread_id}")

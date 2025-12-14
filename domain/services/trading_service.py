"""Trading service - main business logic - QS Optimized Version."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.settings import config
from config.redis_config import trading_config
from domain.models.signal import Signal
from domain.preconditions import PreconditionManager
from domain.models.trade import TradeAction, TradeDecision, AIResponse, TradeResult
from infrastructure.storage.mongo import MongoHandler
from infrastructure.storage.trades_repository import trades_repo
from infrastructure.broker.ibkr_client import IBKRBroker
from infrastructure.broker.market_data import MarketDataProvider
from infrastructure.ai.llm_client import LLMClient
from tools.market_tools import MarketTools
from tools.portfolio_tools import PortfolioTools
from tools.order_tools import OrderTools
from tools.schedule_tools import ScheduleTools

logger = logging.getLogger(__name__)


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

        self._precondition_manager = PreconditionManager()

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

            # Pre-fetch tool data (always enabled - data goes into prompt)
            logger.info("🔄 Pre-fetching tool data...")
            prefetched_data = self._prefetch_tool_data(signal)
            logger.info("   ✅ Pre-fetch complete")

            # Let AI analyze and decide
            logger.info("🤖 Starting AI analysis...")
            ai_response = self._analyze_with_ai(signal, market_data, portfolio_data, scheduled_context, prefetched_data)

            # Check for DELAY decision
            if ai_response.decision.action == TradeAction.DELAY:
                logger.info(f"⏰ DECISION: DELAY | {ai_response.decision.reasoning}")
                self._save_delay_result(signal, ai_response)
                logger.info("=" * 50)
                return True

            # Execute if AI decided to (and hasn't already executed via tool call)
            if ai_response.decision.action == TradeAction.EXECUTE and ai_response.trade_result is None:
                logger.info("💰 Executing trade...")
                trade_result = self._execute_trade(signal, ai_response)
                ai_response.trade_result = trade_result
                if trade_result.success:
                    logger.info(f"   ✅ Trade executed: {trade_result.order_id}")
                else:
                    logger.error(f"   ❌ Trade failed: {trade_result.error}")
            elif ai_response.decision.action == TradeAction.EXECUTE and ai_response.trade_result is not None:
                # Trade was already executed via tool call
                trade_result = ai_response.trade_result
                if trade_result.success:
                    logger.info(f"   ✅ Trade executed (via tool): {trade_result.order_id}")
                else:
                    logger.error(f"   ❌ Trade failed (via tool): {trade_result.error}")

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
        """Validate trading preconditions using PreconditionManager.

        These are hard stops that don't need AI evaluation.
        """
        # Resolve ticker (try parsed, then raw)
        ticker = signal.ticker
        if not ticker and signal.tickers_raw:
            logger.info(f"No clean ticker, using raw: {signal.tickers_raw}")
            ticker = signal.tickers_raw.split(',')[0].strip() if signal.tickers_raw else None

        # Build context for preconditions
        context = {
            "trading_config": trading_config,
            "broker": self._broker,
            "market_data": self._market_data,
            "ticker": ticker,
        }

        return self._precondition_manager.check_all(signal, context)

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

    def _prefetch_tool_data(self, signal: Signal) -> Dict[str, Any]:
        """Pre-fetch all tool data in parallel to include in prompt.
        
        This reduces token usage by providing data upfront so AI 
        doesn't need to call tools iteratively.
        """
        data = {}
        market_handlers = self._market_tools.get_handlers()
        portfolio_handlers = self._portfolio_tools.get_handlers()
        
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

    def _analyze_with_ai(
        self,
        signal: Signal,
        market_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
        scheduled_context: Dict[str, Any] = None,
        prefetched_data: Dict[str, Any] = None,
    ) -> AIResponse:
        """Analyze signal with AI - single LLM call with decision tools only.

        Args:
            signal: The trading signal
            market_data: Current market data
            portfolio_data: Portfolio information
            scheduled_context: Context from previous analysis if this is a reanalysis
            prefetched_data: Pre-fetched tool data (always required)
        """
        # Decision tools only - data is always prefetched into prompt
        tools = (
            OrderTools.get_tool_definitions()
            + ScheduleTools.get_tool_definitions()
        )
        handlers = {
            **self._order_tools.get_handlers(),
            **self._schedule_tools.get_handlers(),
        }

        trading_params = trading_config.get_all()
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

        # Execute the first (and only expected) tool call
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

        # Prepare trade data for P&L tracking
        trade_data = {
            "thread_id": signal.thread_id,
            "ticker": signal.ticker,
            "direction": signal.direction,
            "entry_price": entry,
            "quantity": quantity,
            "take_profit": target,
            "stop_loss": stop_loss,
            "model_used": ai_response.model_used,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning[:500] if decision.reasoning else None,
        }

        # Dry run mode
        if not trading_config.execute_orders:
            logger.info(f"[DRY RUN] {signal.ticker} @ ${entry} | TP: ${target} | SL: ${stop_loss} | Qty: {quantity}")
            
            # Save simulated trade for tracking
            trade_data["order_id"] = "DRY_RUN_SIMULATED"
            trade_data["simulated"] = True
            trade_id = trades_repo.save_trade(trade_data)
            
            return TradeResult(
                success=True,
                order_id="DRY_RUN_SIMULATED",
                simulated=True,
                trade_id=trade_id,
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
                order_id = str(result.get("order", {}).get("order_id", ""))
                logger.info(f"Trade executed: {signal.ticker} @ ${entry}")
                
                # Save trade to P&L tracking
                trade_data["order_id"] = order_id
                trade_data["conid"] = result.get("order", {}).get("conid")
                trade_id = trades_repo.save_trade(trade_data)
                
                return TradeResult(
                    success=True,
                    order_id=order_id,
                    trade_id=trade_id,
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

"""Trading service - main business logic - QS Optimized Version."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from config.settings import config
from config.redis_config import trading_config
from domain.models.signal import Signal
from domain.preconditions import PreconditionManager
from domain.strategies import StrategyManager
from domain.models.trade import TradeAction, AIResponse, TradeResult
from infrastructure.storage.mongo import MongoHandler
from infrastructure.storage.trades_repository import trades_repo
from infrastructure.broker.ibkr_client import IBKRBroker
from infrastructure.broker.market_data import MarketDataProvider
from tools.order_tools import OrderTools

logger = logging.getLogger(__name__)


class TradingService:
    """Main trading service orchestrating signal analysis and execution."""

    def __init__(self):
        """Initialize trading service."""
        self._broker = IBKRBroker()
        self._market_data = MarketDataProvider(self._broker)
        self._order_tools = OrderTools(self._broker)

        # Global preconditions (emergency stop, max positions, VIX)
        self._precondition_manager = PreconditionManager()

        # Forum-specific strategies
        self._strategy_manager = StrategyManager()

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

            logger.info(f"   Forum: {signal.forum_name}")
            logger.info(f"   Ticker: {signal.ticker or 'N/A'} | Direction: {signal.direction or 'N/A'}")
            if signal.entry_price:
                logger.info(f"   Entry: ${signal.entry_price} | Target: ${signal.target_price} | SL: ${signal.stop_loss}")

            # Global preconditions (emergency stop, max positions, VIX)
            validation_error = self._validate_preconditions(signal)
            if validation_error:
                logger.warning(f"⚠️ Validation failed: {validation_error}")
                self._save_skip_result(signal, validation_error)
                logger.info(f"📋 DECISION: SKIP (validation) | {validation_error}")
                logger.info("=" * 50)
                return True

            # Build context for strategy
            context = {
                "trading_config": trading_config,
                "broker": self._broker,
                "market_data": self._market_data,
                "scheduled_context": scheduled_context,
            }

            # Execute forum-specific strategy
            logger.info("🤖 Executing strategy...")
            ai_response = self._strategy_manager.execute(signal, context)

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
            # Determine option direction from signal
            direction = "CALL" if signal.direction in ["CALL", "BUY", "LONG"] else "PUT"

            result = self._order_tools.place_bracket_order(
                ticker=signal.ticker,
                expiry=signal.expiry,
                strike=signal.strike,
                direction=direction,
                side="BUY",  # Always BUY to open option position
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

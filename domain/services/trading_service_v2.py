"""Trading service V2 - Pre-fetch all data, single LLM call.

Key differences from V1:
- All tool data is pre-fetched in parallel BEFORE LLM call
- Single LLM call with all data in the prompt
- AI still makes ALL decisions (skip/execute/schedule)
- No rule-based quick checks - AI decides everything
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, Optional

from config.settings import config
from config.redis_config import trading_config
from domain.models.signal import Signal
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


class TradingServiceV2:
    """Trading service with pre-fetched data - single LLM call."""

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
        """Process a signal from the queue - V2 with pre-fetch."""
        thread_id = task.get("thread_id", "")
        thread_name = task.get("thread_name", "")
        scheduled_context = task.get("scheduled_context")

        logger.info("=" * 50)
        if scheduled_context:
            retry_count = scheduled_context.get("retry_count", 1)
            logger.info(f"🔄 SCHEDULED REANALYSIS #{retry_count} (V2): {thread_name}")
        else:
            logger.info(f"📥 SIGNAL RECEIVED (V2): {thread_name}")
        logger.info(f"   Thread ID: {thread_id}")

        try:
            signal = self._load_signal(thread_id)
            if not signal:
                logger.error(f"❌ Signal not found in MongoDB: {thread_id}")
                return False

            logger.info(f"   Ticker: {signal.ticker or 'N/A'} | Direction: {signal.direction or 'N/A'}")

            # Basic validation only (emergency stop, whitelist/blacklist)
            validation_error = self._validate_preconditions(signal)
            if validation_error:
                logger.warning(f"⚠️ Validation failed: {validation_error}")
                self._save_skip_result(signal, validation_error)
                return True

            # PRE-FETCH ALL DATA IN PARALLEL
            logger.info("🔄 Pre-fetching all tool data...")
            prefetched_data = self._prefetch_all_data(signal)
            logger.info(f"   ✅ Pre-fetch complete")

            # SINGLE LLM CALL with all data - AI makes ALL decisions
            logger.info("🤖 Single AI decision call...")
            ai_response = self._analyze_with_prefetched_data(signal, prefetched_data, scheduled_context)

            # Handle DELAY decision
            if ai_response.decision.action == TradeAction.DELAY:
                logger.info(f"⏰ DECISION: DELAY | {ai_response.decision.reasoning}")
                self._save_delay_result(signal, ai_response)
                logger.info("=" * 50)
                return True

            # Execute if needed
            if ai_response.decision.action == TradeAction.EXECUTE and ai_response.trade_result is None:
                logger.info("💰 Executing trade...")
                trade_result = self._execute_trade(signal, ai_response)
                ai_response.trade_result = trade_result
                if trade_result.success:
                    logger.info(f"   ✅ Trade executed: {trade_result.order_id}")
                else:
                    logger.error(f"   ❌ Trade failed: {trade_result.error}")

            self._save_result(signal, ai_response)

            action_emoji = "✅" if ai_response.decision.action == TradeAction.EXECUTE else "⏭️"
            logger.info(f"📋 DECISION: {ai_response.decision.action.value.upper()}")
            logger.info(f"{action_emoji} {ai_response.decision.reasoning[:100]}")
            logger.info("=" * 50)
            return True

        except Exception as e:
            logger.error(f"Error processing signal {thread_id}: {e}", exc_info=True)
            return False

    def _prefetch_all_data(self, signal: Signal) -> Dict[str, Any]:
        """Pre-fetch all tool data in parallel."""
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
                    logger.debug(f"   ✓ {key} fetched")
                except Exception as e:
                    logger.warning(f"   ✗ {key} failed: {e}")
                    data[key] = {"error": str(e)}
        
        return data

    def _analyze_with_prefetched_data(
        self, 
        signal: Signal, 
        prefetched_data: Dict[str, Any],
        scheduled_context: Optional[Dict[str, Any]] = None
    ) -> AIResponse:
        """Single LLM call with all prefetched data - AI decides everything."""
        
        # Build comprehensive prompt with all data
        prompt = self._build_comprehensive_prompt(signal, prefetched_data, scheduled_context)
        
        # Get retry count from scheduled context
        retry_count = scheduled_context.get("retry_count", 0) if scheduled_context else 0
        
        # Decision tools - AI can skip, execute, OR schedule
        decision_tools = [
            {
                "type": "function",
                "function": {
                    "name": "skip_signal",
                    "description": "Skip this signal - do not trade",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "description": "Why skipping"},
                            "category": {
                                "type": "string",
                                "enum": ["timing", "risk", "market_conditions", "insufficient_data", "other"],
                            }
                        },
                        "required": ["reason", "category"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_trade",
                    "description": "Execute this trade with bracket order",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Option symbol to trade"},
                            "quantity": {"type": "integer", "description": "Number of contracts"},
                            "entry_price": {"type": "number", "description": "Limit entry price"},
                            "take_profit": {"type": "number", "description": "Take profit price"},
                            "stop_loss": {"type": "number", "description": "Stop loss price"},
                            "reasoning": {"type": "string", "description": "Why executing this trade"}
                        },
                        "required": ["symbol", "quantity", "entry_price", "take_profit", "stop_loss", "reasoning"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "schedule_reanalysis",
                    "description": "Schedule this signal for later reanalysis (e.g., market opens soon, waiting for event)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "delay_minutes": {
                                "type": "integer",
                                "description": "Minutes to wait before reanalysis (5-120)"
                            },
                            "reason": {"type": "string", "description": "Why scheduling for later"},
                            "question": {"type": "string", "description": "Question to answer on reanalysis"}
                        },
                        "required": ["delay_minutes", "reason", "question"]
                    }
                }
            }
        ]
        
        model = trading_config.current_llm_model
        
        from openai import OpenAI
        client = OpenAI(
            base_url=config.LITELLM_URL,
            api_key=config.LITELLM_API_KEY or "dummy",
        )
        
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": self._llm._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                tools=decision_tools,
                tool_choice="required",  # Must call one of the tools
                temperature=0.3,
                max_tokens=2000,
            )
            
            message = response.choices[0].message
            request_id = response.id
            
            # Log token usage
            usage = response.usage
            logger.info(f"   📊 Tokens: {usage.prompt_tokens} prompt + {usage.completion_tokens} completion = {usage.total_tokens} total")
            
            # Parse tool call
            if message.tool_calls:
                tc = message.tool_calls[0]
                func_name = tc.function.name
                args = json.loads(tc.function.arguments)
                
                if func_name == "skip_signal":
                    return AIResponse(
                        decision=TradeDecision(
                            action=TradeAction.SKIP,
                            reasoning=args.get("reason", "AI decided to skip"),
                            skip_reason=args.get("category", "other"),
                        ),
                        raw_response=json.dumps(args),
                        model_used=model,
                        trace_id=request_id,
                    )
                    
                elif func_name == "execute_trade":
                    return AIResponse(
                        decision=TradeDecision(
                            action=TradeAction.EXECUTE,
                            reasoning=args.get("reasoning", "AI decided to execute"),
                            confidence=0.8,
                            modified_entry=args.get("entry_price"),
                            modified_target=args.get("take_profit"),
                            modified_stop_loss=args.get("stop_loss"),
                            modified_size=args.get("quantity"),
                        ),
                        raw_response=json.dumps(args),
                        model_used=model,
                        trace_id=request_id,
                    )
                    
                elif func_name == "schedule_reanalysis":
                    # Handle schedule via schedule_tools
                    schedule_args = {
                        "delay_minutes": args.get("delay_minutes", 30),
                        "reason": args.get("reason", "Scheduled for reanalysis"),
                        "question": args.get("question", "Check if conditions changed"),
                        "_thread_id": signal.thread_id,
                        "_thread_name": signal.thread_name or signal.tickers_raw,
                        "_previous_tools": [],  # No previous tools in V2
                        "_retry_count": retry_count,
                        "_signal_data": signal.to_dict(),
                    }
                    
                    schedule_result = self._schedule_tools.get_handlers()["schedule_reanalysis"](**schedule_args)
                    
                    if schedule_result.get("success"):
                        return AIResponse(
                            decision=TradeDecision(
                                action=TradeAction.DELAY,
                                reasoning=args.get("reason", "Scheduled for reanalysis"),
                                skip_reason=None,
                            ),
                            raw_response=json.dumps(args),
                            model_used=model,
                            trace_id=request_id,
                            delay_info={
                                "reanalyze_at": schedule_result.get("reanalyze_at"),
                                "delay_minutes": args.get("delay_minutes"),
                                "question": args.get("question"),
                                "reason": args.get("reason"),
                            },
                        )
                    else:
                        # Schedule failed - skip instead
                        return AIResponse(
                            decision=TradeDecision(
                                action=TradeAction.SKIP,
                                reasoning=f"Schedule failed: {schedule_result.get('error', 'unknown')}",
                                skip_reason="schedule_failed",
                            ),
                            raw_response=json.dumps(schedule_result),
                            model_used=model,
                            trace_id=request_id,
                        )
            
            # Fallback if no tool call
            return AIResponse(
                decision=TradeDecision(
                    action=TradeAction.SKIP,
                    reasoning="No clear decision from AI",
                    skip_reason="parse_error",
                ),
                raw_response=message.content or "",
                model_used=model,
                trace_id=request_id,
            )
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return AIResponse(
                decision=TradeDecision(
                    action=TradeAction.SKIP,
                    reasoning=f"LLM error: {str(e)}",
                    skip_reason="error",
                ),
                raw_response="",
                model_used=model,
            )

    def _build_comprehensive_prompt(
        self, 
        signal: Signal, 
        data: Dict[str, Any],
        scheduled_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build prompt with all prefetched data included."""
        
        time_data = data.get("time", {})
        option_chain = data.get("option_chain", {})
        account = data.get("account", {})
        positions = data.get("positions", {})
        
        prompt = f"""## TRADING SIGNAL ANALYSIS

### Signal Details
- **Ticker:** {signal.ticker or signal.tickers_raw or 'UNKNOWN'}
- **Direction:** {signal.direction or 'UNKNOWN'}
- **Strike:** ${signal.strike:.2f if signal.strike else 'N/A'}
- **Expiry:** {signal.expiry or 'N/A'}
- **Entry Price (signal):** ${signal.entry_price:.2f if signal.entry_price else 'N/A'}
- **Target:** ${signal.target_price:.2f if signal.target_price else 'N/A'}
- **Stop Loss:** ${signal.stop_loss:.2f if signal.stop_loss else 'N/A'}
- **Confidence:** {f'{signal.confidence:.0%}' if signal.confidence else 'N/A'}

### Raw Signal Content
{signal.get_full_content()[:3000]}

---

## CURRENT MARKET DATA (Pre-fetched for you)

### Time
- **Current Time (ET):** {time_data.get('time_est', 'N/A')}
- **Date:** {time_data.get('date', 'N/A')}
- **Day:** {time_data.get('day_of_week', 'N/A')}
- **Market Status:** {time_data.get('market_status', 'N/A')}
- **Is Market Open:** {time_data.get('is_market_open', 'Unknown')}
- **Status Reason:** {time_data.get('status_reason', 'N/A')}
"""
        
        # Add option chain data
        if option_chain and not option_chain.get("error"):
            prompt += f"""
### Option Chain for {signal.ticker}
- **Current Underlying Price:** ${option_chain.get('current_price', 0):.2f}
- **Strike Range:** {option_chain.get('strike_range', 'N/A')}
- **Available Expiries:** {', '.join(option_chain.get('available_expiries', [])[:5])}
"""
            # Add relevant strikes
            if option_chain.get('calls'):
                prompt += "\n**Call Options (nearest strikes):**\n"
                for c in option_chain['calls'][:8]:
                    itm = "ITM" if c.get('inTheMoney') else "OTM"
                    prompt += f"  - Strike ${c.get('strike')}: Bid ${c.get('bid', 0):.2f} / Ask ${c.get('ask', 0):.2f} ({itm})\n"
            
            if option_chain.get('puts'):
                prompt += "\n**Put Options (nearest strikes):**\n"
                for p in option_chain['puts'][:8]:
                    itm = "ITM" if p.get('inTheMoney') else "OTM"
                    prompt += f"  - Strike ${p.get('strike')}: Bid ${p.get('bid', 0):.2f} / Ask ${p.get('ask', 0):.2f} ({itm})\n"
        else:
            prompt += f"\n### Option Chain: Error or not available - {option_chain.get('error', 'N/A')}\n"
        
        # Add account data
        prompt += f"""
### Account Summary
- **USD Available for Trading:** ${account.get('usd_available_for_trading', 0):,.2f}
- **USD Buying Power:** ${account.get('usd_buying_power', 0):,.2f}
- **USD Net Liquidation:** ${account.get('usd_net_liquidation', 0):,.2f}
"""
        if account.get('warning'):
            prompt += f"- **⚠️ Warning:** {account.get('warning')}\n"

        # Add positions
        prompt += f"""
### Current Positions
- **Open Positions Count:** {positions.get('count', 0)}
- **Tickers in Portfolio:** {', '.join(positions.get('tickers', [])) or 'None'}
"""
        
        # Add scheduled context if reanalysis
        if scheduled_context:
            prompt += f"""
---

## ⚠️ THIS IS A SCHEDULED REANALYSIS (Attempt #{scheduled_context.get('retry_count', 1)})

**Original delay reason:** {scheduled_context.get('delay_reason', 'N/A')}

**Question to answer NOW:** {scheduled_context.get('delay_question', 'N/A')}

**IMPORTANT:** Check if conditions have changed. Make your decision: EXECUTE, SKIP, or SCHEDULE again (max 3 retries).
"""
        
        # Decision instructions
        prompt += f"""
---

## YOUR DECISION

Based on ALL the data above, you must call ONE of these tools:

1. **skip_signal** - Skip this trade (market closed, poor R:R, bad timing, insufficient funds, etc.)
2. **execute_trade** - Execute with bracket order (specify symbol, quantity, entry, TP, SL)
3. **schedule_reanalysis** - Wait and check again later (e.g., market opens in 30 min)

Analyze the signal, check the current prices, calculate R:R, and make your decision.
"""
        
        return prompt

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
        """Validate ONLY hard stops - AI decides everything else."""
        # Emergency stop - immediate block
        if trading_config.emergency_stop:
            return "Emergency stop is active"

        ticker = signal.ticker
        if not ticker and signal.tickers_raw:
            ticker = signal.tickers_raw.split(',')[0].strip()

        # Whitelist check
        whitelist = trading_config.whitelist_tickers
        if whitelist and ticker and ticker not in whitelist:
            return f"Ticker {ticker} not in whitelist: {whitelist}"

        # Blacklist check
        blacklist = trading_config.blacklist_tickers
        if ticker and ticker in blacklist:
            return f"Ticker {ticker} is blacklisted"

        return None

    def _execute_trade(self, signal: Signal, ai_response: AIResponse) -> TradeResult:
        """Execute trade based on AI decision."""
        decision = ai_response.decision
        
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
            "reasoning": decision.reasoning[:500] if decision.reasoning else None,
        }

        # Dry run mode
        if not trading_config.execute_orders:
            logger.info(f"[DRY RUN] {signal.ticker} @ ${entry} | TP: ${target} | SL: ${stop_loss}")
            trade_data["order_id"] = "DRY_RUN_SIMULATED"
            trade_data["simulated"] = True
            trade_id = trades_repo.save_trade(trade_data)
            return TradeResult(success=True, order_id="DRY_RUN_SIMULATED", simulated=True, trade_id=trade_id)

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
                trade_data["order_id"] = order_id
                trade_data["conid"] = result.get("order", {}).get("conid")
                trade_id = trades_repo.save_trade(trade_data)
                return TradeResult(success=True, order_id=order_id, trade_id=trade_id)
            return TradeResult(success=False, error=result.get("error"))
            
        except Exception as e:
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
            if ai_response.trace_id:
                update_data["trace_id"] = ai_response.trace_id
            mongo.update_one(
                config.THREADS_COLLECTION,
                query={"thread_id": signal.thread_id},
                update_data=update_data,
            )

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
        """Save delay result to MongoDB."""
        with MongoHandler() as mongo:
            ai_data = ai_response.to_mongo_update()
            update_data = {
                "ai_processed": True,
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

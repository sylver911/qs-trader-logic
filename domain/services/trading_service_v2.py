"""Trading service V2 - Pre-fetch all data, single LLM call."""

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

    def process_signal(self, task: Dict[str, Any]) -> bool:
        """Process a signal from the queue - V2 with pre-fetch."""
        thread_id = task.get("thread_id", "")
        thread_name = task.get("thread_name", "")

        logger.info("=" * 50)
        logger.info(f"📥 SIGNAL RECEIVED (V2): {thread_name}")
        logger.info(f"   Thread ID: {thread_id}")

        try:
            signal = self._load_signal(thread_id)
            if not signal:
                logger.error(f"❌ Signal not found in MongoDB: {thread_id}")
                return False

            logger.info(f"   Ticker: {signal.ticker or 'N/A'} | Direction: {signal.direction or 'N/A'}")

            # Validation
            validation_error = self._validate_preconditions(signal)
            if validation_error:
                logger.warning(f"⚠️ Validation failed: {validation_error}")
                self._save_skip_result(signal, validation_error)
                return True

            # PRE-FETCH ALL DATA IN PARALLEL
            logger.info("🔄 Pre-fetching all tool data...")
            prefetched_data = self._prefetch_all_data(signal)
            
            # QUICK CHECKS before LLM call
            quick_skip = self._quick_checks(prefetched_data, signal)
            if quick_skip:
                logger.info(f"⏭️ Quick skip: {quick_skip}")
                self._save_skip_result(signal, quick_skip)
                return True

            # SINGLE LLM CALL with all data
            logger.info("🤖 Single AI decision call...")
            ai_response = self._analyze_with_prefetched_data(signal, prefetched_data)

            # Execute if needed
            if ai_response.decision.action == TradeAction.EXECUTE:
                logger.info("💰 Executing trade...")
                trade_result = self._execute_trade(signal, ai_response)
                ai_response.trade_result = trade_result

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
        
        handlers = self._market_tools.get_handlers()
        portfolio_handlers = self._portfolio_tools.get_handlers()
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            
            # 1. Current time (always needed)
            futures[executor.submit(handlers["get_current_time"])] = "time"
            
            # 2. Option chain (if ticker known)
            if signal.ticker and signal.expiry:
                futures[executor.submit(
                    handlers["get_option_chain"],
                    symbol=signal.ticker,
                    expiry=signal.expiry
                )] = "option_chain"
            elif signal.ticker:
                futures[executor.submit(
                    handlers["get_option_chain"],
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

    def _quick_checks(self, data: Dict[str, Any], signal: Signal) -> Optional[str]:
        """Quick rule-based checks before LLM call."""
        
        # 1. Market closed?
        time_data = data.get("time", {})
        if not time_data.get("is_market_open"):
            return f"Market is closed ({time_data.get('market_status', 'unknown')})"
        
        # 2. R:R check with current prices
        if signal.entry_price and signal.target_price and signal.stop_loss:
            risk = abs(signal.entry_price - signal.stop_loss)
            reward = abs(signal.target_price - signal.entry_price)
            if risk > 0:
                rr = reward / risk
                if rr < 1.5:
                    return f"R:R ratio {rr:.2f} below minimum 1.5"
        
        # 3. Insufficient balance
        account = data.get("account", {})
        available = account.get("usd_available_for_trading", 0)
        if available <= 0:
            return f"Insufficient account balance (${available:.2f})"
        
        return None

    def _analyze_with_prefetched_data(
        self, 
        signal: Signal, 
        prefetched_data: Dict[str, Any]
    ) -> AIResponse:
        """Single LLM call with all prefetched data."""
        
        # Build comprehensive prompt with all data
        prompt = self._build_comprehensive_prompt(signal, prefetched_data)
        
        # Define only decision tools (skip/execute)
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
                max_tokens=1500,
            )
            
            message = response.choices[0].message
            
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
                        trace_id=response.id,
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
                        trace_id=response.id,
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
                trace_id=response.id,
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
        data: Dict[str, Any]
    ) -> str:
        """Build prompt with all prefetched data included."""
        
        time_data = data.get("time", {})
        option_chain = data.get("option_chain", {})
        account = data.get("account", {})
        positions = data.get("positions", {})
        
        prompt = f"""## TRADING SIGNAL ANALYSIS

### Signal Details
- **Ticker:** {signal.ticker or 'UNKNOWN'}
- **Direction:** {signal.direction or 'UNKNOWN'}
- **Strike:** ${signal.strike:.2f if signal.strike else 'N/A'}
- **Expiry:** {signal.expiry or 'N/A'}
- **Entry Price (signal):** ${signal.entry_price:.2f if signal.entry_price else 'N/A'}
- **Target:** ${signal.target_price:.2f if signal.target_price else 'N/A'}
- **Stop Loss:** ${signal.stop_loss:.2f if signal.stop_loss else 'N/A'}
- **Confidence:** {signal.confidence:.0%if signal.confidence else 'N/A'}

### Raw Signal Content
{signal.get_full_content()[:2000]}

---

## CURRENT MARKET DATA (Pre-fetched)

### Time
- **Current Time (ET):** {time_data.get('time_est', 'N/A')}
- **Market Status:** {time_data.get('market_status', 'N/A')}
- **Is Open:** {time_data.get('is_market_open', False)}

### Option Chain for {signal.ticker}
- **Current Price:** ${option_chain.get('current_price', 0):.2f}
- **Available Expiries:** {', '.join(option_chain.get('available_expiries', [])[:5])}
"""
        
        # Add relevant strikes from option chain
        if option_chain.get('calls'):
            calls = option_chain['calls'][:10]  # Top 10 calls
            prompt += "\n**Nearest Call Options:**\n"
            for c in calls:
                prompt += f"  - Strike ${c.get('strike')}: Bid ${c.get('bid', 0):.2f} / Ask ${c.get('ask', 0):.2f}\n"
        
        prompt += f"""
### Account Summary
- **Available for Trading:** ${account.get('usd_available_for_trading', 0):,.2f}
- **Buying Power:** ${account.get('usd_buying_power', 0):,.2f}
- **Net Liquidation:** ${account.get('usd_net_liquidation', 0):,.2f}

### Current Positions
- **Open Positions:** {positions.get('count', 0)}
- **Tickers:** {', '.join(positions.get('tickers', [])) or 'None'}

---

## YOUR DECISION

Based on ALL the data above, decide:
1. **SKIP** - if market closed, poor R:R, insufficient balance, bad timing, etc.
2. **EXECUTE** - if everything checks out, specify exact bracket order parameters

Call either `skip_signal` or `execute_trade` with your decision.
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
        """Validate trading preconditions."""
        if trading_config.emergency_stop:
            return "Emergency stop is active"

        ticker = signal.ticker
        if not ticker and signal.tickers_raw:
            ticker = signal.tickers_raw.split(',')[0].strip()

        if not ticker:
            if signal.get_full_content() and len(signal.get_full_content()) > 50:
                return None
            return "No ticker found"

        whitelist = trading_config.whitelist_tickers
        if whitelist and ticker not in whitelist:
            return f"Ticker {ticker} not in whitelist"

        blacklist = trading_config.blacklist_tickers
        if ticker in blacklist:
            return f"Ticker {ticker} is blacklisted"

        return None

    def _execute_trade(self, signal: Signal, ai_response: AIResponse) -> TradeResult:
        """Execute trade."""
        decision = ai_response.decision
        
        entry = decision.modified_entry or signal.entry_price
        target = decision.modified_target or signal.target_price
        stop_loss = decision.modified_stop_loss or signal.stop_loss
        quantity = int(decision.modified_size) if decision.modified_size else 1

        if not trading_config.execute_orders:
            logger.info(f"[DRY RUN] {signal.ticker} @ ${entry}")
            return TradeResult(success=True, order_id="DRY_RUN", simulated=True)

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
                return TradeResult(success=True, order_id=order_id)
            return TradeResult(success=False, error=result.get("error"))
            
        except Exception as e:
            return TradeResult(success=False, error=str(e))

    def _save_result(self, signal: Signal, ai_response: AIResponse) -> None:
        """Save AI result to MongoDB."""
        with MongoHandler() as mongo:
            mongo.update_one(
                config.THREADS_COLLECTION,
                query={"thread_id": signal.thread_id},
                update_data={
                    "ai_processed": True,
                    "ai_processed_at": datetime.now().isoformat(),
                    "ai_result": ai_response.to_mongo_update(),
                    "trace_id": ai_response.trace_id,
                },
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

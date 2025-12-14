"""Order execution tools for AI - QS Optimized Version.

Only the essential order tool for QS:
- place_bracket_order (entry + TP + SL in one)
"""

import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import time

from config.redis_config import trading_config
from infrastructure.broker.ibkr_client import IBKRBroker

logger = logging.getLogger(__name__)


class OrderTools:
    """Order execution tools for AI - QS Optimized."""

    def __init__(self, broker: Optional[IBKRBroker] = None):
        """Initialize order tools."""
        self._broker = broker or IBKRBroker()

    @staticmethod
    def get_tool_definitions() -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool definitions.
        
        QS Optimized: Only bracket order - this is what we use for options.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "place_bracket_order",
                    "description": "Place a bracket order with entry, take profit, and stop loss. This is the primary order type for QS signals. The AI should calculate optimal bracket parameters based on current prices and R:R analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Underlying ticker symbol (e.g., 'SPY', 'QQQ', 'TSLA')",
                            },
                            "expiry": {
                                "type": "string",
                                "description": "Option expiry date in YYYY-MM-DD format (e.g., '2024-12-09')",
                            },
                            "strike": {
                                "type": "number",
                                "description": "Strike price (e.g., 605.0)",
                            },
                            "direction": {
                                "type": "string",
                                "enum": ["CALL", "PUT"],
                                "description": "Option direction - CALL or PUT",
                            },
                            "side": {
                                "type": "string",
                                "enum": ["BUY", "SELL"],
                                "description": "Order side - BUY to open, SELL to close",
                            },
                            "quantity": {
                                "type": "integer",
                                "description": "Number of option contracts",
                            },
                            "entry_price": {
                                "type": "number",
                                "description": "Entry limit price for the option",
                            },
                            "take_profit": {
                                "type": "number",
                                "description": "Take profit price",
                            },
                            "stop_loss": {
                                "type": "number",
                                "description": "Stop loss price",
                            },
                        },
                        "required": ["ticker", "expiry", "strike", "direction", "side", "quantity", "entry_price", "take_profit", "stop_loss"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "skip_signal",
                    "description": "Skip this signal and do not execute any trade. Use this when: (1) Signal has no actionable trade setup, (2) Market is closed, (3) Risk/reward is unfavorable, (4) Signal is just analysis without entry/target/stop, (5) Confidence is too low. ALWAYS call this tool when you decide not to trade - do not just output JSON.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Clear reason for skipping (e.g., 'No actionable trade signal - analysis only', 'Market closed', 'R:R below 1.5')",
                            },
                            "category": {
                                "type": "string",
                                "enum": ["no_signal", "market_closed", "bad_rr", "low_confidence", "timing", "position_exists", "other"],
                                "description": "Category of skip reason for analytics",
                            },
                        },
                        "required": ["reason", "category"],
                    },
                },
            },
        ]

    def get_handlers(self) -> Dict[str, callable]:
        """Get tool handler functions."""
        return {
            "place_bracket_order": self.place_bracket_order,
            "skip_signal": self.skip_signal,
        }

    def skip_signal(self, reason: str, category: str) -> Dict[str, Any]:
        """Skip the signal - explicit tool call for AI to indicate no trade."""
        result = {
            "action": "skip",
            "reason": reason,
            "category": category,
            "timestamp": datetime.now().isoformat(),
        }
        
        return result

    def _parse_option_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Parse OCC option symbol into components.
        
        Format: "SPY 241209C00605000" or "SPY241209C00605000"
        - Ticker: SPY
        - Date: 241209 (YYMMDD)
        - Right: C (Call) or P (Put)
        - Strike: 00605000 (605.000 with 3 implied decimals)
        
        Returns:
            Dict with: ticker, expiry_month, strike, right
            Or None if parsing fails
        """
        # Remove spaces and uppercase
        symbol = symbol.upper().replace(" ", "")
        
        # Match pattern: TICKER + YYMMDD + C/P + 8-digit strike
        # Ticker can be 1-6 characters
        pattern = r'^([A-Z]{1,6})(\d{6})([CP])(\d{8})$'
        match = re.match(pattern, symbol)
        
        if not match:
            logger.warning(f"Could not parse option symbol: {symbol}")
            return None
        
        ticker = match.group(1)
        date_str = match.group(2)  # YYMMDD
        right = match.group(3)  # C or P
        strike_str = match.group(4)  # 8 digits
        
        # Convert strike (00605000 -> 605.0)
        strike = int(strike_str) / 1000.0
        
        # Convert date to IBKR month format (YYMMDD -> DECYY format: DEC24)
        year = date_str[:2]  # "24"
        month_num = int(date_str[2:4])  # 12
        
        month_names = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", 
                       "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        month_name = month_names[month_num] if 1 <= month_num <= 12 else None
        
        if not month_name:
            logger.warning(f"Invalid month in symbol: {symbol}")
            return None
        
        expiry_month = f"{month_name}{year}"  # "DEC24"
        
        return {
            "ticker": ticker,
            "expiry_month": expiry_month,
            "expiry_date": f"20{date_str}",  # "20241209"
            "strike": strike,
            "right": right,
        }

    def _get_option_conid(self, symbol: str) -> Tuple[Optional[str], Optional[str]]:
        """Get contract ID for an option symbol.
        
        This performs the two-step IBKR lookup:
        1. Get underlying stock conid
        2. Use search_secdef_info_by_conid to get the specific option contract
        
        Args:
            symbol: OCC option symbol (e.g., "SPY 241209C00605000")
            
        Returns:
            Tuple of (conid, error_message)
        """
        # Parse the option symbol
        parsed = self._parse_option_symbol(symbol)
        if not parsed:
            return None, f"Could not parse option symbol: {symbol}"
        
        ticker = parsed["ticker"]
        expiry_month = parsed["expiry_month"]
        strike = parsed["strike"]
        right = parsed["right"]
        
        logger.info(f"Looking up option: {ticker} {expiry_month} {strike} {right}")
        
        try:
            # Step 1: Get underlying conid
            underlying = self._broker.search_contract(ticker, sec_type="STK")
            if not underlying:
                return None, f"Underlying {ticker} not found"
            
            underlying_conid = str(underlying.get("conid"))
            logger.debug(f"Underlying {ticker} conid: {underlying_conid}")
            
            # Step 2: Get option contract details
            client = self._broker._get_client()
            result = client.search_secdef_info_by_conid(
                conid=underlying_conid,
                sec_type="OPT",
                month=expiry_month,
                strike=str(strike),
                right=right,
            )
            
            if not result.data:
                return None, f"Option contract not found: {ticker} {expiry_month} {strike}{right}"
            
            # The result should contain the option contract(s)
            # Look for exact match or first result
            option_data = result.data
            if isinstance(option_data, list):
                if len(option_data) == 0:
                    return None, f"No option contracts returned for {symbol}"
                option_data = option_data[0]
            
            option_conid = str(option_data.get("conid"))
            logger.info(f"Option conid found: {option_conid} for {symbol}")
            
            return option_conid, None
            
        except Exception as e:
            logger.error(f"Error looking up option conid for {symbol}: {e}")
            return None, str(e)

    def _get_conid(self, symbol: str) -> Tuple[Optional[str], Optional[str]]:
        """Get contract ID for a symbol (stock or option).
        
        Returns:
            Tuple of (conid, error_message)
        """
        # Check if this looks like an option symbol
        # Options have format like "SPY 241209C00605000" or contain C/P followed by digits
        symbol_clean = symbol.upper().replace(" ", "")
        
        # Simple heuristic: if it has C or P followed by 8 digits, it's an option
        if re.search(r'[CP]\d{8}$', symbol_clean):
            return self._get_option_conid(symbol)
        
        # Otherwise treat as stock
        try:
            contract = self._broker.search_contract(symbol.upper(), sec_type="STK")
            if contract:
                return str(contract.get("conid")), None
            return None, f"Stock contract not found for {symbol}"
        except Exception as e:
            return None, str(e)

    def place_bracket_order(
        self,
        ticker: str,
        expiry: str,
        strike: float,
        direction: str,
        side: str,
        quantity: int,
        entry_price: float,
        take_profit: float,
        stop_loss: float,
    ) -> Dict[str, Any]:
        """Place a bracket order.

        This creates:
        1. Entry order (limit)
        2. Take profit order (limit, OCA with stop)
        3. Stop loss order (stop, OCA with TP)
        """
        # Build OCC symbol from components
        # Format: TICKER YYMMDD[C/P]STRIKE (e.g., SPY 241209C00605000)
        symbol = self._build_occ_symbol(ticker, expiry, strike, direction)

        # DRY RUN CHECK - simulate order without actually placing it
        if not trading_config.execute_orders:
            logger.info(f"[DRY RUN] Would place bracket order:")
            logger.info(f"  Symbol: {symbol}")
            logger.info(f"  Side: {side}, Qty: {quantity}")
            logger.info(f"  Entry: ${entry_price}, TP: ${take_profit}, SL: ${stop_loss}")
            return {
                "success": True,
                "order": {"order_id": "DRY_RUN_SIMULATED"},
                "conid": "DRY_RUN",
                "symbol": symbol,
                "product": {
                    "ticker": ticker,
                    "expiry": expiry,
                    "strike": strike,
                    "direction": direction.upper() if direction else None,
                },
                "side": side,
                "quantity": quantity,
                "entry_price": entry_price,
                "take_profit": take_profit,
                "stop_loss": stop_loss,
                "order_type": "BRACKET",
                "simulated": True,
                "timestamp": datetime.now().isoformat(),
            }
        logger.info(f"Built OCC symbol: {symbol}")

        conid, error = self._get_conid(symbol)
        logger.info(f"Contract lookup: conid={conid}, error={error}")

        if not conid:
            return {
                "success": False,
                "error": error or f"Contract not found for {symbol}",
                "timestamp": datetime.now().isoformat(),
            }

        logger.info(f"Placing bracket order: conid={conid}, side={side}, qty={quantity}")
        logger.info(f"  Entry: ${entry_price}, TP: ${take_profit}, SL: ${stop_loss}")

        result = self._broker.place_bracket_order(
            conid=conid,
            side=side.upper(),
            quantity=quantity,
            entry_price=entry_price,
            take_profit=take_profit,
            stop_loss=stop_loss,
        )

        logger.info(f"Bracket order result: {result}")

        # Check for actual success - result should contain order IDs
        success = False
        if result is not None:
            if isinstance(result, list) and len(result) > 0:
                # Should be list of 3 orders (parent + TP + SL)
                success = True
                logger.info(f"  ✅ Order placed successfully: {len(result)} orders created")
            elif isinstance(result, dict) and result.get("order_id"):
                success = True
                logger.info(f"  ✅ Order placed successfully: order_id={result.get('order_id')}")
            else:
                logger.warning(f"  ⚠️ Unexpected result format: {type(result)}")
        else:
            logger.error("  ❌ Order placement returned None")

        return {
            "success": success,
            "order": result,
            "conid": conid,
            "symbol": symbol,
            "product": {
                "ticker": ticker,
                "expiry": expiry,
                "strike": strike,
                "direction": direction.upper() if direction else None,
            },
            "side": side,
            "quantity": quantity,
            "entry_price": entry_price,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "order_type": "BRACKET",
            "timestamp": datetime.now().isoformat(),
        }
    
    def _build_occ_symbol(self, ticker: str, expiry: str, strike: float, direction: str) -> str:
        """Build OCC option symbol from components.
        
        Format: TICKER YYMMDD[C/P]STRIKE
        Example: SPY 241209C00605000 (SPY Dec 9 2024 $605 Call)
        """
        # Parse expiry (YYYY-MM-DD) to YYMMDD
        from datetime import datetime as dt
        exp_date = dt.strptime(expiry, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        
        # Direction: C or P
        dir_char = "C" if direction.upper() == "CALL" else "P"
        
        # Strike: 8 digits with 3 implied decimals (605.0 -> 00605000)
        strike_int = int(strike * 1000)
        strike_str = f"{strike_int:08d}"
        
        return f"{ticker.upper()} {exp_str}{dir_char}{strike_str}"

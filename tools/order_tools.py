"""Order execution tools for AI - QS Optimized Version.

Only the essential order tool for QS:
- place_bracket_order (entry + TP + SL in one)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import time

from infrastructure.broker.ibkr_client import IBKRBroker


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
                            "symbol": {
                                "type": "string",
                                "description": "Option symbol (e.g., 'SPY 241203C00605000' for SPY Dec 3 $605 Call)",
                            },
                            "side": {
                                "type": "string",
                                "enum": ["BUY", "SELL"],
                                "description": "Order side - BUY for calls/puts, SELL to close",
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
                        "required": ["symbol", "side", "quantity", "entry_price", "take_profit", "stop_loss"],
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
        """Skip the signal - explicit tool call for AI to indicate no trade.
        
        This provides a clean way for AI to skip signals instead of outputting JSON directly.
        """
        return {
            "action": "skip",
            "reason": reason,
            "category": category,
            "timestamp": datetime.now().isoformat(),
        }

    def _get_conid(self, symbol: str) -> Optional[str]:
        """Get contract ID for a symbol."""
        # For options, we need to handle the full symbol
        contract = self._broker.search_contract(symbol.upper())
        if contract:
            return str(contract.get("conid"))
        return None

    def place_bracket_order(
        self,
        symbol: str,
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
        conid = self._get_conid(symbol)
        if not conid:
            return {
                "success": False,
                "error": f"Contract not found for {symbol}",
                "timestamp": datetime.now().isoformat(),
            }

        result = self._broker.place_bracket_order(
            conid=conid,
            side=side.upper(),
            quantity=quantity,
            entry_price=entry_price,
            take_profit=take_profit,
            stop_loss=stop_loss,
        )

        return {
            "success": result is not None,
            "order": result,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "entry_price": entry_price,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "order_type": "BRACKET",
            "timestamp": datetime.now().isoformat(),
        }

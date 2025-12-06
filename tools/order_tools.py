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
        ]

    def get_handlers(self) -> Dict[str, callable]:
        """Get tool handler functions."""
        return {
            "place_bracket_order": self.place_bracket_order,
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

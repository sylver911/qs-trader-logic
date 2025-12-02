"""Order execution tools for AI."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from infrastructure.broker.ibkr_client import IBKRBroker


class OrderTools:
    """Order execution tools for AI function calling."""

    def __init__(self, broker: Optional[IBKRBroker] = None):
        """Initialize order tools.

        Args:
            broker: IBKR broker client
        """
        self._broker = broker or IBKRBroker()

    @staticmethod
    def get_tool_definitions() -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool definitions.

        Returns:
            List of tool definitions
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "place_market_order",
                    "description": "Place a market order to buy or sell",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "The ticker symbol",
                            },
                            "side": {
                                "type": "string",
                                "enum": ["BUY", "SELL"],
                                "description": "Order side",
                            },
                            "quantity": {
                                "type": "integer",
                                "description": "Number of shares/contracts",
                            },
                        },
                        "required": ["symbol", "side", "quantity"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "place_limit_order",
                    "description": "Place a limit order at a specific price",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "The ticker symbol",
                            },
                            "side": {
                                "type": "string",
                                "enum": ["BUY", "SELL"],
                                "description": "Order side",
                            },
                            "quantity": {
                                "type": "integer",
                                "description": "Number of shares/contracts",
                            },
                            "price": {
                                "type": "number",
                                "description": "Limit price",
                            },
                        },
                        "required": ["symbol", "side", "quantity", "price"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "place_bracket_order",
                    "description": "Place a bracket order with entry, take profit, and stop loss",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "The ticker symbol",
                            },
                            "side": {
                                "type": "string",
                                "enum": ["BUY", "SELL"],
                                "description": "Order side",
                            },
                            "quantity": {
                                "type": "integer",
                                "description": "Number of shares/contracts",
                            },
                            "entry_price": {
                                "type": "number",
                                "description": "Entry limit price",
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
                    "name": "cancel_order",
                    "description": "Cancel an existing order",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {
                                "type": "string",
                                "description": "The order ID to cancel",
                            },
                        },
                        "required": ["order_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "modify_order",
                    "description": "Modify an existing order's price or quantity",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {
                                "type": "string",
                                "description": "The order ID to modify",
                            },
                            "new_price": {
                                "type": "number",
                                "description": "New limit price (optional)",
                            },
                            "new_quantity": {
                                "type": "integer",
                                "description": "New quantity (optional)",
                            },
                        },
                        "required": ["order_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "close_position",
                    "description": "Close an existing position",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "The ticker symbol of the position to close",
                            },
                            "quantity": {
                                "type": "integer",
                                "description": "Quantity to close (optional, closes all if not specified)",
                            },
                        },
                        "required": ["symbol"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_stop_loss",
                    "description": "Adjust the stop loss on an existing position",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {
                                "type": "string",
                                "description": "The stop loss order ID",
                            },
                            "new_stop_price": {
                                "type": "number",
                                "description": "New stop loss price",
                            },
                        },
                        "required": ["order_id", "new_stop_price"],
                    },
                },
            },
        ]

    def get_handlers(self) -> Dict[str, callable]:
        """Get tool handler functions.

        Returns:
            Map of function names to handlers
        """
        return {
            "place_market_order": self.place_market_order,
            "place_limit_order": self.place_limit_order,
            "place_bracket_order": self.place_bracket_order,
            "cancel_order": self.cancel_order,
            "modify_order": self.modify_order,
            "close_position": self.close_position,
            "adjust_stop_loss": self.adjust_stop_loss,
        }

    def _get_conid(self, symbol: str) -> Optional[str]:
        """Get contract ID for a symbol.

        Args:
            symbol: Ticker symbol

        Returns:
            Contract ID or None
        """
        contract = self._broker.search_contract(symbol.upper())
        if contract:
            return str(contract.get("conid"))
        return None

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
    ) -> Dict[str, Any]:
        """Place a market order.

        Args:
            symbol: Ticker symbol
            side: BUY or SELL
            quantity: Number of shares/contracts

        Returns:
            Order result
        """
        conid = self._get_conid(symbol)
        if not conid:
            return {
                "success": False,
                "error": f"Contract not found for {symbol}",
                "timestamp": datetime.now().isoformat(),
            }

        result = self._broker.place_order(
            conid=conid,
            side=side.upper(),
            quantity=quantity,
            order_type="MKT",
        )

        return {
            "success": result is not None,
            "order": result,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "order_type": "MKT",
            "timestamp": datetime.now().isoformat(),
        }

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
    ) -> Dict[str, Any]:
        """Place a limit order.

        Args:
            symbol: Ticker symbol
            side: BUY or SELL
            quantity: Number of shares/contracts
            price: Limit price

        Returns:
            Order result
        """
        conid = self._get_conid(symbol)
        if not conid:
            return {
                "success": False,
                "error": f"Contract not found for {symbol}",
                "timestamp": datetime.now().isoformat(),
            }

        result = self._broker.place_order(
            conid=conid,
            side=side.upper(),
            quantity=quantity,
            order_type="LMT",
            price=price,
        )

        return {
            "success": result is not None,
            "order": result,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "order_type": "LMT",
            "timestamp": datetime.now().isoformat(),
        }

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

        Args:
            symbol: Ticker symbol
            side: BUY or SELL
            quantity: Number of shares/contracts
            entry_price: Entry limit price
            take_profit: Take profit price
            stop_loss: Stop loss price

        Returns:
            Order result
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

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order.

        Args:
            order_id: Order ID

        Returns:
            Cancellation result
        """
        success = self._broker.cancel_order(order_id)

        return {
            "success": success,
            "order_id": order_id,
            "timestamp": datetime.now().isoformat(),
        }

    def modify_order(
        self,
        order_id: str,
        new_price: Optional[float] = None,
        new_quantity: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Modify an order.

        Args:
            order_id: Order ID
            new_price: New price
            new_quantity: New quantity

        Returns:
            Modification result
        """
        success = self._broker.modify_order(
            order_id=order_id,
            price=new_price,
            quantity=new_quantity,
        )

        return {
            "success": success,
            "order_id": order_id,
            "new_price": new_price,
            "new_quantity": new_quantity,
            "timestamp": datetime.now().isoformat(),
        }

    def close_position(
        self,
        symbol: str,
        quantity: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Close a position.

        Args:
            symbol: Ticker symbol
            quantity: Quantity to close (all if not specified)

        Returns:
            Close result
        """
        positions = self._broker.get_positions()
        position = next(
            (p for p in positions if p.get("ticker", "").upper() == symbol.upper()),
            None,
        )

        if not position:
            return {
                "success": False,
                "error": f"No position found for {symbol}",
                "timestamp": datetime.now().isoformat(),
            }

        conid = str(position.get("conid"))
        pos_qty = abs(int(position.get("position", 0)))
        close_qty = quantity or pos_qty

        current_side = "BUY" if position.get("position", 0) > 0 else "SELL"

        result = self._broker.close_position(
            conid=conid,
            quantity=close_qty,
            side=current_side,
        )

        return {
            "success": result is not None,
            "order": result,
            "symbol": symbol,
            "quantity_closed": close_qty,
            "timestamp": datetime.now().isoformat(),
        }

    def adjust_stop_loss(
        self,
        order_id: str,
        new_stop_price: float,
    ) -> Dict[str, Any]:
        """Adjust stop loss price.

        Args:
            order_id: Stop loss order ID
            new_stop_price: New stop price

        Returns:
            Adjustment result
        """
        success = self._broker.modify_order(
            order_id=order_id,
            price=new_stop_price,
        )

        return {
            "success": success,
            "order_id": order_id,
            "new_stop_price": new_stop_price,
            "timestamp": datetime.now().isoformat(),
        }

"""IBKR client wrapper using IBind."""

import logging
import time
from typing import Any, Dict, List, Optional

from ibind import IbkrClient
from ibind.client.ibkr_utils import make_order_request

from config.settings import config

logger = logging.getLogger(__name__)


class IBKRBroker:
    """IBKR broker client wrapper."""

    def __init__(self):
        """Initialize IBKR client."""
        self._client: Optional[IbkrClient] = None
        self._account_id = config.IB_ACCOUNT_ID
        self._connected = False

    def _get_client(self) -> IbkrClient:
        """Get or create IBKR client."""
        if self._client is None:
            self._client = IbkrClient(
                url=f"{config.IBEAM_URL}/v1/api/",
                account_id=self._account_id,
                cacert=False,
                timeout=10,
            )
            logger.debug(f"IBKR client created for account {self._account_id}")

        return self._client

    def check_health(self) -> bool:
        """Check if IBKR connection is healthy.

        Returns:
            True if healthy
        """
        try:
            client = self._get_client()
            result = client.tickle()
            self._connected = result.data is not None
            return self._connected
        except Exception as e:
            logger.error(f"IBKR health check failed: {e}")
            self._connected = False
            return False

    def get_accounts(self) -> List[str]:
        """Get list of accounts.

        Returns:
            List of account IDs
        """
        try:
            client = self._get_client()
            result = client.portfolio_accounts()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to get accounts: {e}")
            return []

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions.

        Returns:
            List of positions
        """
        try:
            client = self._get_client()
            result = client.positions(account_id=self._account_id)
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    def get_account_summary(self) -> Optional[Dict[str, Any]]:
        """Get account summary.

        Returns:
            Account summary data
        """
        try:
            client = self._get_client()
            result = client.account_summary(account_id=self._account_id)
            return result.data if result.data else None
        except Exception as e:
            logger.error(f"Failed to get account summary: {e}")
            return None

    def get_pnl(self) -> Optional[Dict[str, Any]]:
        """Get account P&L.

        Returns:
            P&L data
        """
        try:
            client = self._get_client()
            result = client.account_profit_and_loss()
            return result.data if result.data else None
        except Exception as e:
            logger.error(f"Failed to get P&L: {e}")
            return None

    def get_trades(self, days: int = 1) -> List[Dict[str, Any]]:
        """Get recent trades.

        Args:
            days: Number of days of history

        Returns:
            List of trades
        """
        try:
            client = self._get_client()
            result = client.trades(days=str(days), account_id=self._account_id)
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []

    def get_live_orders(self) -> List[Dict[str, Any]]:
        """Get live orders.

        Returns:
            List of live orders
        """
        try:
            client = self._get_client()
            result = client.live_orders()
            return result.data.get("orders", []) if result.data else []
        except Exception as e:
            logger.error(f"Failed to get live orders: {e}")
            return []

    def search_contract(self, symbol: str, sec_type: str = "STK") -> Optional[Dict[str, Any]]:
        """Search for a contract.

        Args:
            symbol: Ticker symbol
            sec_type: Security type (STK, OPT, etc.)

        Returns:
            Contract data
        """
        try:
            client = self._get_client()
            result = client.search_contract_by_symbol(symbol=symbol, sec_type=sec_type)
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to search contract {symbol}: {e}")
            return None

    def get_option_chain(
        self,
        symbol: str,
        expiry: str,
        strike: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Get option chain for a symbol.

        Args:
            symbol: Underlying symbol
            expiry: Expiry date
            strike: Optional strike filter

        Returns:
            List of option contracts
        """
        try:
            client = self._get_client()

            # First get underlying conid
            underlying = self.search_contract(symbol)
            if not underlying:
                return []

            conid = underlying.get("conid")

            # Get strikes
            result = client.search_strikes_by_conid(
                conid=str(conid),
                sec_type="OPT",
                month=expiry,
            )

            return result.data if result.data else []

        except Exception as e:
            logger.error(f"Failed to get option chain for {symbol}: {e}")
            return []

    def place_order(
        self,
        conid: str,
        side: str,
        quantity: int,
        order_type: str = "MKT",
        price: Optional[float] = None,
        tif: str = "DAY",
    ) -> Optional[Dict[str, Any]]:
        """Place an order.

        Args:
            conid: Contract ID
            side: BUY or SELL
            quantity: Number of contracts/shares
            order_type: Order type (MKT, LMT, STP)
            price: Limit price (for LMT orders)
            tif: Time in force

        Returns:
            Order result
        """
        try:
            client = self._get_client()

            order_request = make_order_request(
                conid=conid,
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=price,
                tif=tif,
                acct_id=self._account_id,
            )

            # Auto-confirm orders
            answers = {"confirmed": True}

            result = client.place_order(
                order_request=order_request,
                answers=answers,
                account_id=self._account_id,
            )

            logger.info(f"Order placed: {side} {quantity} @ {price or 'MKT'}")
            return result.data

        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return None

    def place_bracket_order(
        self,
        conid: str,
        side: str,
        quantity: int,
        entry_price: float,
        take_profit: float,
        stop_loss: float,
        tif: str = "DAY",
    ) -> Optional[Dict[str, Any]]:
        """Place a bracket order (entry + TP + SL).

        Creates a parent-child order structure where:
        - Entry order is the parent
        - TP and SL are children with OCA (One-Cancels-All) grouping
        - When TP fills, SL is cancelled and vice versa

        Args:
            conid: Contract ID
            side: BUY or SELL
            quantity: Number of contracts/shares
            entry_price: Entry limit price
            take_profit: Take profit price
            stop_loss: Stop loss price
            tif: Time in force for entry order

        Returns:
            Order result
        """
        try:
            client = self._get_client()

            # Unique IDs for order linkage
            timestamp = int(time.time())
            parent_coid = f"parent_{conid}_{timestamp}"
            oca_group = f"oca_{conid}_{timestamp}"  # OCA group for TP and SL

            # Exit side is opposite of entry
            exit_side = "SELL" if side == "BUY" else "BUY"

            orders = [
                # Entry order (parent)
                make_order_request(
                    conid=conid,
                    side=side,
                    quantity=quantity,
                    order_type="LMT",
                    price=entry_price,
                    tif=tif,
                    acct_id=self._account_id,
                    coid=parent_coid,
                ),
                # Take profit (child, OCA with stop loss)
                make_order_request(
                    conid=conid,
                    side=exit_side,
                    quantity=quantity,
                    order_type="LMT",
                    price=take_profit,
                    tif="GTC",
                    acct_id=self._account_id,
                    parent_id=parent_coid,
                    is_single_group=True,  # Enable OCA grouping
                ),
                # Stop loss (child, OCA with take profit)
                make_order_request(
                    conid=conid,
                    side=exit_side,
                    quantity=quantity,
                    order_type="STP",
                    aux_price=stop_loss,
                    tif="GTC",
                    acct_id=self._account_id,
                    parent_id=parent_coid,
                    is_single_group=True,  # Enable OCA grouping
                ),
            ]

            answers = {"confirmed": True}

            result = client.place_order(
                order_request=orders,
                answers=answers,
                account_id=self._account_id,
            )

            logger.info(
                f"Bracket order placed: {side} {quantity} @ {entry_price}, "
                f"TP: {take_profit}, SL: {stop_loss}, OCA: {oca_group}"
            )
            return result.data

        except Exception as e:
            logger.error(f"Failed to place bracket order: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order.

        Args:
            order_id: Order ID

        Returns:
            True if successful
        """
        try:
            client = self._get_client()
            result = client.cancel_order(
                order_id=order_id,
                account_id=self._account_id,
            )
            logger.info(f"Order cancelled: {order_id}")
            return result.data is not None
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def modify_order(
        self,
        order_id: str,
        price: Optional[float] = None,
        quantity: Optional[int] = None,
    ) -> bool:
        """Modify an existing order.

        Args:
            order_id: Order ID
            price: New price
            quantity: New quantity

        Returns:
            True if successful
        """
        try:
            client = self._get_client()

            # Get existing order
            orders = self.get_live_orders()
            existing = next((o for o in orders if str(o.get("orderId")) == order_id), None)

            if not existing:
                logger.error(f"Order {order_id} not found")
                return False

            order_request = {
                "conid": existing.get("conid"),
                "side": existing.get("side"),
                "quantity": quantity or existing.get("quantity"),
                "orderType": existing.get("orderType"),
                "price": price or existing.get("price"),
                "tif": existing.get("tif", "DAY"),
            }

            answers = {"confirmed": True}

            result = client.modify_order(
                order_id=order_id,
                order_request=order_request,
                answers=answers,
                account_id=self._account_id,
            )

            logger.info(f"Order modified: {order_id}")
            return result.data is not None

        except Exception as e:
            logger.error(f"Failed to modify order {order_id}: {e}")
            return False

    def close_position(self, conid: str, quantity: int, side: str) -> Optional[Dict[str, Any]]:
        """Close a position.

        Args:
            conid: Contract ID
            quantity: Quantity to close
            side: Original position side (will be reversed)

        Returns:
            Order result
        """
        close_side = "SELL" if side == "BUY" else "BUY"
        return self.place_order(
            conid=conid,
            side=close_side,
            quantity=quantity,
            order_type="MKT",
        )

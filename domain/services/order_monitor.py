"""Order Monitor Service - Polls IBKR for order fills and updates P&L tracking.

This service periodically checks IBKR for filled orders and updates the
trades collection in MongoDB with exit prices and P&L calculations.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from infrastructure.broker.ibkr_client import IBKRBroker
from infrastructure.storage.trades_repository import trades_repo
from config.settings import config

logger = logging.getLogger(__name__)


class OrderMonitor:
    """Monitors IBKR orders and updates P&L tracking."""

    def __init__(self, broker: IBKRBroker, poll_interval: int = 30):
        """Initialize order monitor.

        Args:
            broker: IBKR broker client
            poll_interval: Seconds between polls (default: 30)
        """
        self._broker = broker
        self._poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_check = None

    def start(self) -> None:
        """Start the order monitor in a background thread."""
        if self._running:
            logger.warning("Order monitor already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"📊 Order monitor started (polling every {self._poll_interval}s)")

    def stop(self) -> None:
        """Stop the order monitor."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Order monitor stopped")

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                self._check_orders()
            except Exception as e:
                logger.error(f"Order monitor error: {e}", exc_info=True)

            time.sleep(self._poll_interval)

    def _check_orders(self) -> None:
        """Check IBKR for order updates and sync with trades collection."""
        # Get open trades from our DB
        open_trades = trades_repo.get_open_trades()
        if not open_trades:
            return

        logger.debug(f"Checking {len(open_trades)} open trades...")

        # Get trades from IBKR (executions from last 7 days)
        try:
            client = self._broker._get_client()
            
            # First, get live orders to check status
            live_orders_result = client.live_orders(filters=[])
            live_orders = live_orders_result.data.get("orders", []) if live_orders_result.data else []
            
            # Also get recent trades (executions)
            trades_result = client.trades(days="7")
            ibkr_trades = trades_result.data if trades_result.data else []

        except Exception as e:
            logger.error(f"Failed to fetch IBKR orders: {e}")
            return

        # Build lookup maps
        order_status_map = self._build_order_status_map(live_orders)
        execution_map = self._build_execution_map(ibkr_trades)

        # Check each open trade
        for trade in open_trades:
            order_id = trade.get("order_id")
            if not order_id or order_id == "DRY_RUN_SIMULATED":
                continue

            trade_id = str(trade.get("_id"))

            # Check if we have execution data
            if order_id in execution_map:
                exec_data = execution_map[order_id]
                self._close_trade_from_execution(trade_id, trade, exec_data)
                continue

            # Check order status
            if order_id in order_status_map:
                status = order_status_map[order_id]
                self._process_order_status(trade_id, trade, status)

        self._last_check = datetime.now()

    def _build_order_status_map(self, orders: List[Dict]) -> Dict[str, Dict]:
        """Build a map of order_id -> order status."""
        result = {}
        for order in orders:
            order_id = str(order.get("orderId", ""))
            if order_id:
                result[order_id] = order
        return result

    def _build_execution_map(self, trades: List[Dict]) -> Dict[str, Dict]:
        """Build a map of order_id -> execution data."""
        result = {}
        for trade in trades:
            # IBKR trades have 'execution_id' and 'order_ref' or similar
            order_id = str(trade.get("order_ref", trade.get("orderId", "")))
            if order_id:
                # If multiple executions for same order, keep the last one
                if order_id not in result:
                    result[order_id] = trade
                else:
                    # Aggregate if needed
                    result[order_id] = trade
        return result

    def _close_trade_from_execution(
        self, trade_id: str, trade: Dict, exec_data: Dict
    ) -> None:
        """Close a trade based on IBKR execution data."""
        try:
            exit_price = float(exec_data.get("price", 0))
            exec_side = exec_data.get("side", "").upper()

            # Calculate P&L
            entry_price = trade.get("entry_price", 0)
            quantity = trade.get("quantity", 1)
            direction = trade.get("direction", "").upper()

            # For options: (exit - entry) * 100 * quantity
            # Simplified: just use the difference
            if direction in ["CALL", "BUY"]:
                pnl = (exit_price - entry_price) * 100 * quantity
            else:
                pnl = (entry_price - exit_price) * 100 * quantity

            # Determine if TP or SL hit
            take_profit = trade.get("take_profit", 0)
            stop_loss = trade.get("stop_loss", 0)

            if exit_price >= take_profit:
                status = "closed_tp"
            elif exit_price <= stop_loss:
                status = "closed_sl"
            else:
                status = "closed_other"

            # Update trade
            trades_repo.close_trade(
                trade_id=trade_id,
                exit_price=exit_price,
                status=status,
                pnl=pnl,
                exit_reason=f"IBKR execution: {exec_data.get('execution_id', 'N/A')}",
            )

            logger.info(
                f"📊 Trade closed: {trade.get('ticker')} | "
                f"Exit: ${exit_price:.2f} | P&L: ${pnl:.2f} | Status: {status}"
            )

        except Exception as e:
            logger.error(f"Failed to close trade {trade_id}: {e}")

    def _process_order_status(
        self, trade_id: str, trade: Dict, order_status: Dict
    ) -> None:
        """Process order status updates."""
        status = order_status.get("status", "").lower()

        if status == "filled":
            # Order is filled - try to get fill price
            fill_price = order_status.get("avgPrice", order_status.get("lastFillPrice"))
            if fill_price:
                self._close_trade_from_status(trade_id, trade, order_status)

        elif status in ["cancelled", "inactive"]:
            # Order was cancelled
            logger.info(f"Order cancelled for trade {trade_id}")
            trades_repo.update_trade(trade_id, {
                "status": "cancelled",
                "exit_reason": f"Order cancelled: {order_status.get('warning_text', '')}",
            })

    def _close_trade_from_status(
        self, trade_id: str, trade: Dict, order_status: Dict
    ) -> None:
        """Close trade based on order status (fill info)."""
        try:
            exit_price = float(order_status.get("avgPrice", 0))
            if not exit_price:
                exit_price = float(order_status.get("lastFillPrice", 0))

            entry_price = trade.get("entry_price", 0)
            quantity = trade.get("quantity", 1)
            direction = trade.get("direction", "").upper()

            # Calculate P&L
            if direction in ["CALL", "BUY"]:
                pnl = (exit_price - entry_price) * 100 * quantity
            else:
                pnl = (entry_price - exit_price) * 100 * quantity

            # Determine status
            take_profit = trade.get("take_profit", 0)
            stop_loss = trade.get("stop_loss", 0)

            if take_profit and exit_price >= take_profit * 0.98:  # 2% tolerance
                status = "closed_tp"
            elif stop_loss and exit_price <= stop_loss * 1.02:  # 2% tolerance
                status = "closed_sl"
            else:
                status = "closed_filled"

            trades_repo.close_trade(
                trade_id=trade_id,
                exit_price=exit_price,
                status=status,
                pnl=pnl,
                exit_reason=f"Order filled at ${exit_price:.2f}",
            )

            logger.info(
                f"📊 Trade closed from status: {trade.get('ticker')} | "
                f"Exit: ${exit_price:.2f} | P&L: ${pnl:.2f}"
            )

        except Exception as e:
            logger.error(f"Failed to close trade from status {trade_id}: {e}")

    def check_now(self) -> Dict[str, Any]:
        """Manually trigger an order check.

        Returns:
            Summary of check results
        """
        try:
            open_trades = trades_repo.get_open_trades()
            self._check_orders()
            remaining = trades_repo.get_open_trades()

            return {
                "success": True,
                "open_before": len(open_trades),
                "open_after": len(remaining),
                "closed": len(open_trades) - len(remaining),
                "checked_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Manual order check failed: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance (initialized in main.py)
order_monitor: Optional[OrderMonitor] = None


def init_order_monitor(broker: IBKRBroker, poll_interval: int = 30) -> OrderMonitor:
    """Initialize the global order monitor.

    Args:
        broker: IBKR broker client
        poll_interval: Seconds between polls

    Returns:
        OrderMonitor instance
    """
    global order_monitor
    order_monitor = OrderMonitor(broker, poll_interval)
    return order_monitor

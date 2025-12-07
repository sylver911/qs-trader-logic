"""P&L Tracking - Trades Repository.

Manages the 'trades' collection in MongoDB for tracking executed trades and P&L.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from config.settings import config
from infrastructure.storage.mongo import MongoHandler

logger = logging.getLogger(__name__)

TRADES_COLLECTION = "trades"


class TradesRepository:
    """Repository for trade P&L tracking."""

    def save_trade(self, trade_data: Dict[str, Any]) -> Optional[str]:
        """Save a new trade to MongoDB.

        Args:
            trade_data: Trade details including:
                - thread_id: Source signal thread
                - ticker: Ticker symbol (e.g., "SPY")
                - direction: CALL/PUT or BUY/SELL
                - entry_price: Entry price
                - quantity: Number of contracts
                - take_profit: TP price
                - stop_loss: SL price
                - conid: IBKR contract ID (if available)
                - order_id: IBKR order ID
                - model_used: LLM model that made the decision
                - confidence: AI confidence score

        Returns:
            Trade ID if successful, None otherwise
        """
        try:
            with MongoHandler() as mongo:
                trade_doc = {
                    **trade_data,
                    "status": "open",
                    "entry_time": datetime.now().isoformat(),
                    "created_at": datetime.now().isoformat(),
                }
                result = mongo.db[TRADES_COLLECTION].insert_one(trade_doc)
                trade_id = str(result.inserted_id)
                logger.info(f"📊 Trade saved: {trade_id} | {trade_data.get('ticker')} @ ${trade_data.get('entry_price')}")
                return trade_id
        except Exception as e:
            logger.error(f"Failed to save trade: {e}")
            return None

    def update_trade(self, trade_id: str, updates: Dict[str, Any]) -> bool:
        """Update a trade document.

        Args:
            trade_id: MongoDB ObjectId as string
            updates: Fields to update

        Returns:
            True if updated successfully
        """
        try:
            with MongoHandler() as mongo:
                updates["updated_at"] = datetime.now().isoformat()
                result = mongo.db[TRADES_COLLECTION].update_one(
                    {"_id": ObjectId(trade_id)},
                    {"$set": updates}
                )
                return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update trade {trade_id}: {e}")
            return False

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        status: str,
        pnl: float,
        exit_reason: Optional[str] = None,
    ) -> bool:
        """Close a trade with exit details.

        Args:
            trade_id: Trade MongoDB ID
            exit_price: Exit price
            status: 'closed_tp' | 'closed_sl' | 'closed_manual' | 'closed_expired'
            pnl: Realized P&L
            exit_reason: Optional description

        Returns:
            True if closed successfully
        """
        return self.update_trade(trade_id, {
            "exit_price": exit_price,
            "exit_time": datetime.now().isoformat(),
            "status": status,
            "pnl": pnl,
            "exit_reason": exit_reason,
        })

    def find_trade_by_order_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Find a trade by IBKR order ID."""
        try:
            with MongoHandler() as mongo:
                return mongo.db[TRADES_COLLECTION].find_one({"order_id": order_id})
        except Exception as e:
            logger.error(f"Failed to find trade by order_id {order_id}: {e}")
            return None

    def find_trade_by_thread_id(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Find a trade by source thread ID."""
        try:
            with MongoHandler() as mongo:
                return mongo.db[TRADES_COLLECTION].find_one(
                    {"thread_id": thread_id, "status": "open"}
                )
        except Exception as e:
            logger.error(f"Failed to find trade by thread_id {thread_id}: {e}")
            return None

    def get_open_trades(self) -> List[Dict[str, Any]]:
        """Get all open trades."""
        try:
            with MongoHandler() as mongo:
                return list(mongo.db[TRADES_COLLECTION].find({"status": "open"}))
        except Exception as e:
            logger.error(f"Failed to get open trades: {e}")
            return []

    def get_trades_by_ticker(self, ticker: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get trades for a specific ticker."""
        try:
            with MongoHandler() as mongo:
                return list(
                    mongo.db[TRADES_COLLECTION]
                    .find({"ticker": ticker.upper()})
                    .sort("created_at", -1)
                    .limit(limit)
                )
        except Exception as e:
            logger.error(f"Failed to get trades for {ticker}: {e}")
            return []

    def get_recent_trades(self, days: int = 30, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent trades."""
        try:
            from datetime import timedelta
            with MongoHandler() as mongo:
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                return list(
                    mongo.db[TRADES_COLLECTION]
                    .find({"created_at": {"$gte": cutoff}})
                    .sort("created_at", -1)
                    .limit(limit)
                )
        except Exception as e:
            logger.error(f"Failed to get recent trades: {e}")
            return []

    def get_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get P&L statistics.

        Returns:
            Dict with: total_trades, wins, losses, win_rate, total_pnl, avg_win, avg_loss
        """
        try:
            from datetime import timedelta
            with MongoHandler() as mongo:
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()

                pipeline = [
                    {"$match": {"created_at": {"$gte": cutoff}}},
                    {"$group": {
                        "_id": None,
                        "total_trades": {"$sum": 1},
                        "open_trades": {"$sum": {"$cond": [{"$eq": ["$status", "open"]}, 1, 0]}},
                        "wins": {"$sum": {"$cond": [{"$gt": ["$pnl", 0]}, 1, 0]}},
                        "losses": {"$sum": {"$cond": [{"$lt": ["$pnl", 0]}, 1, 0]}},
                        "total_pnl": {"$sum": {"$ifNull": ["$pnl", 0]}},
                        "avg_win": {"$avg": {"$cond": [{"$gt": ["$pnl", 0]}, "$pnl", None]}},
                        "avg_loss": {"$avg": {"$cond": [{"$lt": ["$pnl", 0]}, "$pnl", None]}},
                        "max_win": {"$max": "$pnl"},
                        "max_loss": {"$min": "$pnl"},
                    }}
                ]

                results = list(mongo.db[TRADES_COLLECTION].aggregate(pipeline))

                if results:
                    stats = results[0]
                    del stats["_id"]
                    closed_trades = stats["wins"] + stats["losses"]
                    stats["win_rate"] = (stats["wins"] / closed_trades * 100) if closed_trades > 0 else 0
                    stats["closed_trades"] = closed_trades
                    return stats

                return {
                    "total_trades": 0, "open_trades": 0, "wins": 0, "losses": 0,
                    "total_pnl": 0, "win_rate": 0, "closed_trades": 0,
                    "avg_win": 0, "avg_loss": 0, "max_win": 0, "max_loss": 0,
                }
        except Exception as e:
            logger.error(f"Failed to get trade stats: {e}")
            return {}


# Singleton instance
trades_repo = TradesRepository()

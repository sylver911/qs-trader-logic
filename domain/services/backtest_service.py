"""Backtest service for validating signal quality against actual market data.

This service:
1. Fetches option prices via yfinance
2. Records signal-time prices when AI processes signals
3. Records EOD prices via scheduled job
4. Calculates outcomes (profit/loss) for backtesting
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

from config.settings import config
from infrastructure.storage.mongo import MongoHandler

logger = logging.getLogger(__name__)


class BacktestService:
    """Service for backtesting signal quality."""
    
    def __init__(self):
        if not HAS_YFINANCE:
            logger.warning("yfinance not installed - backtest features disabled")
    
    def get_option_price(
        self, 
        ticker: str, 
        expiry: str, 
        strike: float, 
        direction: str
    ) -> Optional[float]:
        """Get current option price from yfinance.
        
        Args:
            ticker: Underlying ticker (e.g., 'SPY')
            expiry: Expiry date in YYYY-MM-DD format
            strike: Strike price
            direction: 'CALL' or 'PUT'
            
        Returns:
            Last price of the option, or None if not found
        """
        if not HAS_YFINANCE:
            logger.warning("yfinance not available")
            return None
            
        try:
            tk = yf.Ticker(ticker)
            
            # Get option chain for expiry
            opt = tk.option_chain(expiry)
            
            # Select calls or puts
            if direction.upper() == "CALL":
                chain = opt.calls
            else:
                chain = opt.puts
            
            # Filter by strike
            row = chain[chain['strike'] == strike]
            
            if not row.empty:
                return float(row['lastPrice'].iloc[0])
            
            # Try to find closest strike if exact not found
            if not chain.empty:
                closest_idx = (chain['strike'] - strike).abs().idxmin()
                closest_row = chain.loc[closest_idx]
                logger.warning(
                    f"Exact strike {strike} not found for {ticker} {expiry}, "
                    f"using closest: {closest_row['strike']}"
                )
                return float(closest_row['lastPrice'])
                
            return None
            
        except Exception as e:
            logger.error(f"Error getting option price: {e}")
            return None
    
    def record_signal_price(
        self,
        thread_id: str,
        product: Dict[str, Any],
    ) -> bool:
        """Record the option price at signal processing time.
        
        Called immediately after AI processes a signal (execute/skip/schedule).
        
        Args:
            thread_id: The thread being processed
            product: Dict with ticker, expiry, strike, direction
            
        Returns:
            True if successful
        """
        if not product:
            logger.warning(f"No product info for thread {thread_id}")
            return False
        
        ticker = product.get("ticker")
        expiry = product.get("expiry")
        strike = product.get("strike")
        direction = product.get("direction")
        
        if not all([ticker, expiry, strike, direction]):
            logger.warning(f"Incomplete product info for thread {thread_id}: {product}")
            return False
        
        # Get current price
        price = self.get_option_price(ticker, expiry, strike, direction)
        
        if price is None:
            logger.warning(f"Could not get price for {ticker} {expiry} {strike} {direction}")
            return False
        
        # Save to MongoDB
        try:
            with MongoHandler() as mongo:
                mongo.update_one(
                    config.THREADS_COLLECTION,
                    query={"thread_id": thread_id},
                    update_data={
                        "backtest": {
                            "product": product,
                            "signal_time": datetime.now().isoformat(),
                            "signal_price": price,
                            "eod_price": None,
                            "eod_checked_at": None,
                            "outcome": None,
                        }
                    }
                )
            logger.info(f"Recorded signal price ${price} for {thread_id} ({ticker} {strike} {direction})")
            return True
            
        except Exception as e:
            logger.error(f"Error saving signal price: {e}")
            return False
    
    def run_eod_backtest(self, date: str = None) -> Dict[str, Any]:
        """Run EOD backtest for all signals from a given date.
        
        This should be called after market close (e.g., 4:30 PM EST).
        
        Args:
            date: Date to backtest in YYYY-MM-DD format. Defaults to today.
            
        Returns:
            Summary of backtest results
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"Running EOD backtest for {date}")
        
        results = {
            "date": date,
            "total": 0,
            "updated": 0,
            "failed": 0,
            "skipped": 0,
            "profitable": 0,
            "losing": 0,
        }
        
        try:
            with MongoHandler() as mongo:
                # Find all threads from today with backtest.product but no eod_price
                start_of_day = f"{date}T00:00:00"
                end_of_day = f"{date}T23:59:59"
                
                threads = mongo.find(
                    config.MONGO_DB_NAME,
                    config.THREADS_COLLECTION,
                    query={
                        "backtest.product": {"$exists": True},
                        "backtest.signal_time": {
                            "$gte": start_of_day,
                            "$lte": end_of_day,
                        },
                        "backtest.eod_price": None,
                    }
                )
                
                threads = list(threads)
                results["total"] = len(threads)
                logger.info(f"Found {len(threads)} threads to backtest")
                
                for thread in threads:
                    thread_id = thread.get("thread_id")
                    backtest = thread.get("backtest", {})
                    product = backtest.get("product", {})
                    signal_price = backtest.get("signal_price")
                    
                    if not product or not signal_price:
                        results["skipped"] += 1
                        continue
                    
                    ticker = product.get("ticker")
                    expiry = product.get("expiry")
                    strike = product.get("strike")
                    direction = product.get("direction")
                    
                    # Get EOD price
                    eod_price = self.get_option_price(ticker, expiry, strike, direction)
                    
                    if eod_price is None:
                        # Option might have expired worthless (0DTE)
                        # Check if expiry was today
                        if expiry == date:
                            eod_price = 0.0
                            logger.info(f"{thread_id}: Option expired, setting EOD price to 0")
                        else:
                            logger.warning(f"Could not get EOD price for {thread_id}")
                            results["failed"] += 1
                            continue
                    
                    # Calculate outcome
                    price_change = eod_price - signal_price
                    price_change_pct = (price_change / signal_price * 100) if signal_price > 0 else 0
                    
                    # Determine outcome based on direction
                    # For BUY CALL/PUT: profit if price went up
                    outcome = "PROFIT" if price_change > 0 else "LOSS" if price_change < 0 else "FLAT"
                    
                    # Update MongoDB
                    mongo.update_one(
                        config.MONGO_DB_NAME,
                        config.THREADS_COLLECTION,
                        query={"thread_id": thread_id},
                        update_data={
                            "backtest.eod_price": eod_price,
                            "backtest.eod_checked_at": datetime.now().isoformat(),
                            "backtest.price_change": round(price_change, 2),
                            "backtest.price_change_pct": round(price_change_pct, 2),
                            "backtest.outcome": outcome,
                        }
                    )
                    
                    results["updated"] += 1
                    if outcome == "PROFIT":
                        results["profitable"] += 1
                    elif outcome == "LOSS":
                        results["losing"] += 1
                    
                    logger.info(
                        f"{thread_id}: {ticker} {strike}{direction[0]} "
                        f"${signal_price} -> ${eod_price} ({price_change_pct:+.1f}%) = {outcome}"
                    )
                
        except Exception as e:
            logger.error(f"Error running EOD backtest: {e}")
            results["error"] = str(e)
        
        logger.info(f"EOD backtest complete: {results}")
        return results
    
    def get_backtest_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get summary statistics for backtested signals.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Summary statistics
        """
        try:
            with MongoHandler() as mongo:
                start_date = (datetime.now() - timedelta(days=days)).isoformat()
                
                threads = mongo.find(
                    config.MONGO_DB_NAME,
                    config.THREADS_COLLECTION,
                    query={
                        "backtest.outcome": {"$exists": True, "$ne": None},
                        "backtest.signal_time": {"$gte": start_date},
                    }
                )
                
                threads = list(threads)
                
                if not threads:
                    return {"total": 0, "message": "No backtested signals found"}
                
                # Calculate statistics
                total = len(threads)
                profitable = sum(1 for t in threads if t.get("backtest", {}).get("outcome") == "PROFIT")
                losing = sum(1 for t in threads if t.get("backtest", {}).get("outcome") == "LOSS")
                flat = sum(1 for t in threads if t.get("backtest", {}).get("outcome") == "FLAT")
                
                # By action
                executes = [t for t in threads if t.get("ai_result", {}).get("act") == "execute"]
                skips = [t for t in threads if t.get("ai_result", {}).get("act") == "skip"]
                
                exec_profitable = sum(1 for t in executes if t.get("backtest", {}).get("outcome") == "PROFIT")
                skip_profitable = sum(1 for t in skips if t.get("backtest", {}).get("outcome") == "PROFIT")
                
                return {
                    "days": days,
                    "total": total,
                    "profitable": profitable,
                    "losing": losing,
                    "flat": flat,
                    "win_rate": round(profitable / total * 100, 1) if total > 0 else 0,
                    "executed": {
                        "total": len(executes),
                        "profitable": exec_profitable,
                        "win_rate": round(exec_profitable / len(executes) * 100, 1) if executes else 0,
                    },
                    "skipped": {
                        "total": len(skips),
                        "profitable": skip_profitable,
                        "missed_rate": round(skip_profitable / len(skips) * 100, 1) if skips else 0,
                    },
                }
                
        except Exception as e:
            logger.error(f"Error getting backtest summary: {e}")
            return {"error": str(e)}


# Singleton instance
_backtest_service: Optional[BacktestService] = None


def get_backtest_service() -> BacktestService:
    """Get singleton backtest service instance."""
    global _backtest_service
    if _backtest_service is None:
        _backtest_service = BacktestService()
    return _backtest_service

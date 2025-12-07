"""Schedule tools - Delayed reanalysis for event-driven signals."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis

from config.settings import config

logger = logging.getLogger(__name__)


class ScheduleTools:
    """Tools for scheduling delayed signal reanalysis."""
    
    # Limits
    MAX_DELAY_MINUTES = 240  # 4 hours max
    MIN_DELAY_MINUTES = 5    # At least 5 minutes
    MAX_RETRIES = 2          # Max 2 reanalysis attempts
    
    def __init__(self, redis_client: redis.Redis = None):
        """Initialize with Redis client."""
        self._redis = redis_client or self._get_redis()
    
    def _get_redis(self) -> redis.Redis:
        """Get Redis connection."""
        redis_url = getattr(config, 'REDIS_URL', None)
        if redis_url:
            return redis.from_url(redis_url, decode_responses=True)
        return redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    @staticmethod
    def get_tool_definitions() -> List[Dict[str, Any]]:
        """Get tool definitions for LLM."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "schedule_reanalysis",
                    "description": """Schedule this signal for reanalysis at a later time. 
                    
USE THIS WHEN:
- Signal mentions waiting for specific event (PCE, FOMC, CPI, jobs report, etc.)
- Signal says "wait for market open" or "wait for first 30 minutes"
- Entry timing is not right NOW but will be valid LATER today
- You need fresh market data after a specific time

DO NOT USE WHEN:
- Event is more than 4 hours away (just SKIP instead)
- Signal is already stale or expired
- You've already reanalyzed this signal twice (check retry_count)

The signal will be automatically reanalyzed at the specified time with fresh market data.
You will receive the previous analysis context when reanalyzing.""",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reanalyze_at": {
                                "type": "string",
                                "description": "ISO timestamp when to reanalyze (e.g., '2024-12-06T10:05:00'). Must be 5-240 minutes from now."
                            },
                            "reason": {
                                "type": "string",
                                "description": "Why scheduling delay (e.g., 'Waiting for PCE data release at 10:00 AM')"
                            },
                            "question": {
                                "type": "string",
                                "description": "Question to answer when reanalyzing (e.g., 'Has the market reacted to PCE? Is the short entry still valid?')"
                            },
                            "key_levels": {
                                "type": "object",
                                "description": "Key price levels to check on reanalysis",
                                "properties": {
                                    "entry_price": {"type": "number"},
                                    "target_price": {"type": "number"},
                                    "stop_loss": {"type": "number"},
                                    "underlying_price": {"type": "number"}
                                }
                            }
                        },
                        "required": ["reanalyze_at", "reason", "question"]
                    }
                }
            }
        ]
    
    def get_handlers(self) -> Dict[str, callable]:
        """Get tool handlers."""
        return {
            "schedule_reanalysis": self.schedule_reanalysis,
        }
    
    def schedule_reanalysis(
        self,
        reanalyze_at: str,
        reason: str,
        question: str,
        key_levels: Dict[str, float] = None,
        # These are injected by TradingService
        _thread_id: str = None,
        _thread_name: str = None,
        _previous_tools: List[Dict] = None,
        _retry_count: int = 0,
        _signal_data: Dict = None,
    ) -> Dict[str, Any]:
        """Schedule signal for delayed reanalysis.
        
        Args:
            reanalyze_at: ISO timestamp when to reanalyze
            reason: Why scheduling delay
            question: Question to answer on reanalysis
            key_levels: Key price levels to check
            _thread_id: Injected by TradingService
            _thread_name: Injected by TradingService
            _previous_tools: Tool calls made so far
            _retry_count: Current retry count
            _signal_data: Original signal data
        
        Returns:
            Result dict with scheduling status
        """
        if not _thread_id:
            return {"success": False, "error": "No thread_id provided (internal error)"}
        
        # Check retry limit
        if _retry_count >= self.MAX_RETRIES:
            return {
                "success": False, 
                "error": f"Max retries ({self.MAX_RETRIES}) reached. Must decide now: EXECUTE or SKIP.",
                "force_decision": True
            }
        
        # Parse and validate reanalyze_at
        try:
            reanalyze_time = datetime.fromisoformat(reanalyze_at.replace('Z', '+00:00'))
            # Remove timezone for comparison if naive
            if reanalyze_time.tzinfo:
                reanalyze_time = reanalyze_time.replace(tzinfo=None)
        except ValueError as e:
            return {"success": False, "error": f"Invalid timestamp format: {e}"}
        
        now = datetime.now()
        delay_minutes = (reanalyze_time - now).total_seconds() / 60
        
        # Validate delay bounds
        if delay_minutes < self.MIN_DELAY_MINUTES:
            return {
                "success": False,
                "error": f"Delay too short ({delay_minutes:.0f} min). Minimum is {self.MIN_DELAY_MINUTES} minutes. Decide now or pick a later time."
            }
        
        if delay_minutes > self.MAX_DELAY_MINUTES:
            return {
                "success": False,
                "error": f"Delay too long ({delay_minutes:.0f} min). Maximum is {self.MAX_DELAY_MINUTES} minutes ({self.MAX_DELAY_MINUTES/60:.0f} hours). Consider SKIP instead."
            }
        
        # Build scheduled data
        scheduled_data = {
            "thread_id": _thread_id,
            "thread_name": _thread_name or "Unknown",
            "scheduled_at": now.isoformat(),
            "reanalyze_at": reanalyze_time.isoformat(),
            "retry_count": _retry_count + 1,
            "max_retries": self.MAX_RETRIES,
            
            # Context for reanalysis
            "delay_reason": reason,
            "delay_question": question,
            "key_levels": key_levels or {},
            
            # Previous analysis context
            "previous_analysis": {
                "tools_called": [t.get("name") or t.get("function") for t in (_previous_tools or [])],
                "tool_results_summary": self._summarize_tool_results(_previous_tools or []),
            },
            
            # Original signal (summarized)
            "signal_summary": {
                "ticker": _signal_data.get("ticker") if _signal_data else None,
                "direction": _signal_data.get("direction") if _signal_data else None,
                "entry_price": _signal_data.get("entry_price") if _signal_data else None,
                "target_price": _signal_data.get("target_price") if _signal_data else None,
                "stop_loss": _signal_data.get("stop_loss") if _signal_data else None,
            }
        }
        
        # Store in Redis sorted set (score = reanalyze timestamp)
        try:
            score = reanalyze_time.timestamp()
            
            # Store the full data
            data_key = f"scheduled:data:{_thread_id}"
            self._redis.set(data_key, json.dumps(scheduled_data))
            # Set expiry for cleanup (24 hours after scheduled time)
            self._redis.expireat(data_key, int(score + 86400))
            
            # Add to sorted set for polling
            self._redis.zadd("queue:scheduled", {_thread_id: score})
            
            logger.info(f"Scheduled reanalysis for {_thread_id} at {reanalyze_time} (in {delay_minutes:.0f} min)")
            
            return {
                "success": True,
                "scheduled": True,
                "reanalyze_at": reanalyze_time.isoformat(),
                "delay_minutes": int(delay_minutes),
                "reason": reason,
                "question": question,
                "retry_count": _retry_count + 1,
                "message": f"Signal scheduled for reanalysis in {int(delay_minutes)} minutes. Will check: {question}"
            }
            
        except Exception as e:
            logger.error(f"Failed to schedule reanalysis: {e}")
            return {"success": False, "error": str(e)}
    
    def _summarize_tool_results(self, tools: List[Dict]) -> Dict[str, Any]:
        """Summarize tool results for context (avoid storing huge option chains)."""
        summary = {}
        for tool in tools:
            name = tool.get("name") or tool.get("function", "unknown")
            result = tool.get("result", {})
            
            if name == "get_current_time":
                summary["market_status"] = result.get("market_status")
                summary["time_est"] = result.get("time_est")
            elif name == "get_option_chain":
                # Just store key info, not entire chain
                summary["option_checked"] = True
            elif name == "get_account_summary":
                summary["cash_available"] = result.get("usd_available_for_trading")
            elif name == "get_positions":
                summary["position_count"] = result.get("count", 0)
            elif name == "get_ticker_price":
                summary["underlying_price"] = result.get("price")
            elif name == "get_vix":
                summary["vix"] = result.get("vix")
        
        return summary
    
    def get_scheduled_items(self) -> List[Dict[str, Any]]:
        """Get all scheduled items (for dashboard)."""
        try:
            # Get all from sorted set with scores
            items = self._redis.zrange("queue:scheduled", 0, -1, withscores=True)
            result = []
            
            for thread_id, score in items:
                data_key = f"scheduled:data:{thread_id}"
                data = self._redis.get(data_key)
                if data:
                    item = json.loads(data)
                    item["reanalyze_timestamp"] = score
                    result.append(item)
                else:
                    # Data expired but still in set - clean up
                    self._redis.zrem("queue:scheduled", thread_id)
            
            return result
        except Exception as e:
            logger.error(f"Error getting scheduled items: {e}")
            return []
    
    def get_due_items(self) -> List[Dict[str, Any]]:
        """Get items due for reanalysis (score <= now)."""
        try:
            now = datetime.now().timestamp()
            due_ids = self._redis.zrangebyscore("queue:scheduled", 0, now)
            
            result = []
            for thread_id in due_ids:
                data_key = f"scheduled:data:{thread_id}"
                data = self._redis.get(data_key)
                if data:
                    result.append(json.loads(data))
                
                # Remove from scheduled set
                self._redis.zrem("queue:scheduled", thread_id)
            
            return result
        except Exception as e:
            logger.error(f"Error getting due items: {e}")
            return []
    
    def cancel_scheduled(self, thread_id: str) -> bool:
        """Cancel a scheduled reanalysis."""
        try:
            self._redis.zrem("queue:scheduled", thread_id)
            self._redis.delete(f"scheduled:data:{thread_id}")
            return True
        except Exception as e:
            logger.error(f"Error canceling scheduled item: {e}")
            return False
    
    def get_scheduled_count(self) -> int:
        """Get count of scheduled items."""
        try:
            return self._redis.zcard("queue:scheduled")
        except Exception:
            return 0

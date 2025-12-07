"""Redis queue consumer for trading signals."""

import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, List

import redis

from config.settings import config

logger = logging.getLogger(__name__)


class RedisConsumer:
    """Redis queue consumer with BRPOP blocking."""

    def __init__(self, redis_url: str = None):
        """Initialize Redis consumer.

        Args:
            redis_url: Redis connection URL
        """
        self._redis_url = redis_url or config.REDIS_URL
        self._client: Optional[redis.Redis] = None
        self._running = False

    def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def pop_task(self, timeout: int = 0) -> Optional[Dict[str, Any]]:
        """Pop a task from the queue (blocking).

        Args:
            timeout: Timeout in seconds (0 = infinite)

        Returns:
            Task data or None
        """
        client = self._get_client()

        try:
            result = client.brpop(config.QUEUE_KEY, timeout=timeout)

            if result:
                _, data = result
                task = json.loads(data)

                # Move to processing set
                client.sadd(config.PROCESSING_KEY, task.get("thread_id", ""))

                logger.debug(f"Popped task: {task.get('thread_id')}")
                return task

        except redis.RedisError as e:
            logger.error(f"Redis error: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in queue: {e}")

        return None

    def complete_task(self, thread_id: str) -> None:
        """Mark a task as completed.

        Args:
            thread_id: Thread ID
        """
        client = self._get_client()

        try:
            client.srem(config.PROCESSING_KEY, thread_id)
            client.sadd("queue:threads:completed", thread_id)
            client.expire("queue:threads:completed", 86400 * 7)  # 7 days TTL
            logger.debug(f"Completed task: {thread_id}")

        except redis.RedisError as e:
            logger.error(f"Redis error marking complete: {e}")

    def fail_task(self, thread_id: str, error: str) -> None:
        """Mark a task as failed.

        Args:
            thread_id: Thread ID
            error: Error message
        """
        client = self._get_client()

        try:
            client.srem(config.PROCESSING_KEY, thread_id)
            client.hset("queue:threads:failed", thread_id, error)
            logger.debug(f"Failed task: {thread_id}")

        except redis.RedisError as e:
            logger.error(f"Redis error marking failed: {e}")

    def run(
        self,
        handler: Callable[[Dict[str, Any]], bool],
        timeout: int = 0,
    ) -> None:
        """Run the consumer loop.

        Args:
            handler: Function to handle each task, returns True on success
            timeout: BRPOP timeout (0 = infinite)
        """
        self._running = True
        logger.info("Starting Redis consumer loop...")
        
        last_scheduled_check = 0
        scheduled_check_interval = 30  # Check scheduled queue every 30 seconds

        while self._running:
            try:
                # Check scheduled queue periodically
                now = time.time()
                if now - last_scheduled_check >= scheduled_check_interval:
                    self._process_scheduled_items(handler)
                    last_scheduled_check = now
                
                task = self.pop_task(timeout=timeout if timeout > 0 else 5)

                if task:
                    thread_id = task.get("thread_id", "")

                    try:
                        success = handler(task)

                        if success:
                            self.complete_task(thread_id)
                        else:
                            self.fail_task(thread_id, "Handler returned False")

                    except Exception as e:
                        logger.error(f"Handler error for {thread_id}: {e}")
                        self.fail_task(thread_id, str(e))

            except KeyboardInterrupt:
                logger.info("Consumer interrupted")
                break
            except Exception as e:
                logger.error(f"Consumer loop error: {e}")

        self._running = False
        logger.info("Consumer loop stopped")

    def stop(self) -> None:
        """Stop the consumer loop."""
        self._running = False

    def _process_scheduled_items(self, handler: Callable[[Dict[str, Any]], bool]) -> None:
        """Check and process any due scheduled reanalysis items.
        
        Args:
            handler: Function to handle each task
        """
        client = self._get_client()
        
        try:
            now = datetime.now().timestamp()
            
            # Get all items due for reanalysis (score <= now)
            due_ids = client.zrangebyscore("queue:scheduled", 0, now)
            
            if due_ids:
                logger.info(f"📅 Found {len(due_ids)} scheduled item(s) due for reanalysis")
            
            for thread_id in due_ids:
                # Get the scheduled data
                data_key = f"scheduled:data:{thread_id}"
                data = client.get(data_key)
                
                if data:
                    scheduled_data = json.loads(data)
                    logger.info(f"🔄 Processing scheduled reanalysis: {scheduled_data.get('thread_name', thread_id)}")
                    
                    # Build task with scheduled context
                    task = {
                        "thread_id": thread_id,
                        "thread_name": scheduled_data.get("thread_name", ""),
                        "scheduled_context": scheduled_data,
                    }
                    
                    try:
                        success = handler(task)
                        
                        if success:
                            self.complete_task(thread_id)
                            logger.info(f"✅ Scheduled reanalysis completed: {thread_id}")
                        else:
                            self.fail_task(thread_id, "Scheduled handler returned False")
                            
                    except Exception as e:
                        logger.error(f"Error in scheduled reanalysis for {thread_id}: {e}")
                        self.fail_task(thread_id, str(e))
                
                # Remove from scheduled set (whether successful or not)
                client.zrem("queue:scheduled", thread_id)
                # Clean up data
                client.delete(data_key)
                
        except redis.RedisError as e:
            logger.error(f"Redis error processing scheduled items: {e}")
        except Exception as e:
            logger.error(f"Error processing scheduled items: {e}")

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics.

        Returns:
            Queue stats
        """
        client = self._get_client()

        try:
            return {
                "pending": client.llen(config.QUEUE_KEY),
                "processing": client.scard(config.PROCESSING_KEY),
                "scheduled": client.zcard("queue:scheduled"),
                "completed": client.scard("queue:threads:completed"),
                "failed": client.hlen("queue:threads:failed"),
            }
        except redis.RedisError as e:
            logger.error(f"Redis error getting stats: {e}")
            return {}

    def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            self._client.close()
            self._client = None
            logger.debug("Redis consumer closed")

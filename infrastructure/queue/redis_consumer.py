"""Redis queue consumer for trading signals."""

import json
import logging
from typing import Any, Callable, Dict, Optional

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

        while self._running:
            try:
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

"""Redis queue consumer for trading signals.

Uses reliable queue pattern:
- BRPOPLPUSH for atomic move from pending to processing
- Processing stores full task JSON (not just thread_id)
- Dead letter queue for invalid/unparseable tasks
- Duplicate detection against completed/processing
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import redis

from config.settings import config

logger = logging.getLogger(__name__)


class RedisConsumer:
    """Redis queue consumer with reliable queue pattern."""

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

    def _move_to_dead_letter(self, raw_data: str, reason: str) -> None:
        """Move invalid task to dead letter queue.

        Args:
            raw_data: Raw task data that couldn't be processed
            reason: Why the task was rejected
        """
        client = self._get_client()
        try:
            dead_letter_entry = json.dumps({
                "raw_data": raw_data[:1000],  # Truncate if too large
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            })
            client.lpush(config.DEAD_LETTER_KEY, dead_letter_entry)
            # Keep only last 100 dead letter items
            client.ltrim(config.DEAD_LETTER_KEY, 0, 99)
            logger.warning(f"☠️ Moved to dead letter queue: {reason}")
        except redis.RedisError as e:
            logger.error(f"Failed to move to dead letter: {e}")

    def _extract_thread_id(self, raw_data: str) -> Optional[str]:
        """Extract thread_id from raw task data.

        Args:
            raw_data: JSON string of task

        Returns:
            thread_id or None if invalid
        """
        try:
            task = json.loads(raw_data)
            thread_id = task.get("thread_id", "")
            if isinstance(thread_id, str):
                return thread_id.strip() or None
            return str(thread_id) if thread_id else None
        except (json.JSONDecodeError, TypeError):
            return None

    def pop_task(self, timeout: int = 0) -> Optional[Dict[str, Any]]:
        """Pop a task from the queue using reliable queue pattern.

        Uses BRPOPLPUSH for atomic move from pending to processing.
        This ensures no task is lost even if process crashes.

        Args:
            timeout: Timeout in seconds (0 = infinite)

        Returns:
            Task data or None
        """
        client = self._get_client()

        try:
            # BRPOPLPUSH atomically moves task from pending to processing
            # The task stays in processing until explicitly removed
            raw_data = client.brpoplpush(
                config.QUEUE_KEY,
                config.PROCESSING_KEY,
                timeout=timeout
            )

            if not raw_data:
                return None

            # Parse JSON
            try:
                task = json.loads(raw_data)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in queue: {e}")
                # Remove from processing (it's invalid)
                client.lrem(config.PROCESSING_KEY, 1, raw_data)
                self._move_to_dead_letter(raw_data, f"JSON decode error: {e}")
                return None

            # Validate thread_id
            thread_id = task.get("thread_id", "")
            if isinstance(thread_id, str):
                thread_id = thread_id.strip()
            else:
                thread_id = str(thread_id) if thread_id else ""

            if not thread_id:
                logger.error(f"Task missing thread_id")
                client.lrem(config.PROCESSING_KEY, 1, raw_data)
                self._move_to_dead_letter(raw_data, "Missing or empty thread_id")
                return None

            # Check for duplicates - already completed?
            if client.sismember(config.COMPLETED_KEY, thread_id):
                logger.info(f"⏭️ Skipping already completed: {thread_id}")
                client.lrem(config.PROCESSING_KEY, 1, raw_data)
                return None

            # Check for duplicates - already processing?
            # Count how many times this thread_id appears in processing
            processing_items = client.lrange(config.PROCESSING_KEY, 0, -1)
            same_thread_count = sum(
                1 for item in processing_items
                if self._extract_thread_id(item) == thread_id
            )

            if same_thread_count > 1:
                # This task is a duplicate (we just added one, so >1 means duplicate)
                logger.warning(f"⚠️ Duplicate task in processing: {thread_id}")
                client.lrem(config.PROCESSING_KEY, 1, raw_data)
                return None

            # Store the raw_data in task for later removal
            task["_raw_data"] = raw_data

            logger.debug(f"Popped task: {thread_id}")
            return task

        except redis.RedisError as e:
            logger.error(f"Redis error in pop_task: {e}")
            return None

    def complete_task(self, thread_id: str, raw_data: str = None) -> None:
        """Mark a task as completed.

        Args:
            thread_id: Thread ID
            raw_data: Raw task data to remove from processing list
        """
        client = self._get_client()

        try:
            # Remove from processing list
            if raw_data:
                removed = client.lrem(config.PROCESSING_KEY, 1, raw_data)
                if removed == 0:
                    logger.warning(f"Task not found in processing list: {thread_id}")

            # Add to completed set with per-item expiry via sorted set
            # Using current timestamp as score for potential cleanup
            client.sadd(config.COMPLETED_KEY, thread_id)

            logger.debug(f"Completed task: {thread_id}")

        except redis.RedisError as e:
            logger.error(f"Redis error marking complete: {e}")

    def fail_task(self, thread_id: str, error: str, raw_data: str = None) -> None:
        """Mark a task as failed.

        Args:
            thread_id: Thread ID
            error: Error message
            raw_data: Raw task data to remove from processing list
        """
        client = self._get_client()

        try:
            # Remove from processing list
            if raw_data:
                client.lrem(config.PROCESSING_KEY, 1, raw_data)

            # Add to failed hash with error and timestamp
            fail_info = json.dumps({
                "error": error,
                "timestamp": datetime.now().isoformat(),
            })
            client.hset(config.FAILED_KEY, thread_id, fail_info)

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

        # Clean up any stale processing items from previous runs
        self._recover_stale_processing()

        # Clean up old completed items
        self._cleanup_old_completed()

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
                    raw_data = task.pop("_raw_data", None)

                    try:
                        success = handler(task)

                        if success:
                            self.complete_task(thread_id, raw_data)
                        else:
                            self.fail_task(thread_id, "Handler returned False", raw_data)

                    except Exception as e:
                        logger.error(f"Handler error for {thread_id}: {e}")
                        self.fail_task(thread_id, str(e), raw_data)

            except KeyboardInterrupt:
                logger.info("Consumer interrupted")
                break
            except Exception as e:
                logger.error(f"Consumer loop error: {e}")
                time.sleep(1)  # Prevent tight loop on persistent errors

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
                # Check if already completed (avoid reprocessing)
                if client.sismember(config.COMPLETED_KEY, thread_id):
                    logger.info(f"⏭️ Scheduled task already completed: {thread_id}")
                    client.zrem("queue:scheduled", thread_id)
                    client.delete(f"scheduled:data:{thread_id}")
                    continue

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

    def _recover_stale_processing(self) -> None:
        """Recover stale items from processing list on startup.

        Items in processing list from previous crashed runs are moved back
        to the pending queue for reprocessing.
        """
        client = self._get_client()

        try:
            # Get all items in processing list
            processing_items = client.lrange(config.PROCESSING_KEY, 0, -1)

            if processing_items:
                count = len(processing_items)
                logger.warning(f"🧹 Found {count} stale item(s) in processing from previous run")

                # Move each item back to pending queue (LIFO order preserved)
                for raw_data in reversed(processing_items):
                    thread_id = self._extract_thread_id(raw_data)

                    # Check if already completed
                    if thread_id and client.sismember(config.COMPLETED_KEY, thread_id):
                        logger.info(f"  ⏭️ Stale item already completed: {thread_id}")
                        client.lrem(config.PROCESSING_KEY, 1, raw_data)
                        continue

                    # Move back to pending for reprocessing
                    client.lrem(config.PROCESSING_KEY, 1, raw_data)
                    client.rpush(config.QUEUE_KEY, raw_data)
                    logger.info(f"  🔄 Requeued stale item: {thread_id}")

                logger.info(f"🧹 Recovered {count} stale item(s)")

        except redis.RedisError as e:
            logger.error(f"Redis error recovering stale items: {e}")

    def _cleanup_old_completed(self) -> None:
        """Remove completed items older than 7 days.

        Since we use a SET, we can't track per-item age.
        This is a simple approach that limits the set size.
        """
        client = self._get_client()

        try:
            completed_count = client.scard(config.COMPLETED_KEY)

            # If set is too large, remove random items
            # This is a simple heuristic - ideally use ZSET with timestamps
            if completed_count > 10000:
                # Remove oldest ~1000 items (random for SET)
                members = client.srandmember(config.COMPLETED_KEY, 1000)
                if members:
                    client.srem(config.COMPLETED_KEY, *members)
                    logger.info(f"🧹 Cleaned up {len(members)} old completed items")

        except redis.RedisError as e:
            logger.error(f"Redis error cleaning completed items: {e}")

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics.

        Returns:
            Queue stats
        """
        client = self._get_client()

        try:
            return {
                "pending": client.llen(config.QUEUE_KEY),
                "processing": client.llen(config.PROCESSING_KEY),
                "scheduled": client.zcard("queue:scheduled"),
                "completed": client.scard(config.COMPLETED_KEY),
                "failed": client.hlen(config.FAILED_KEY),
                "dead_letter": client.llen(config.DEAD_LETTER_KEY),
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

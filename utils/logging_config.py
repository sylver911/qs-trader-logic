"""Logging configuration with Discord webhook support."""

import logging
import logging.handlers
import os
import sys
import threading
import queue
from typing import Optional

import requests

from config.settings import config

WEBHOOK_URL = config.LOG_WEBHOOK_URL


class AsyncDiscordHandler(logging.Handler):
    """Async Discord webhook handler - non-blocking."""

    def __init__(self, webhook_url: str, level: int = logging.INFO):
        super().__init__(level)
        self.webhook_url = webhook_url
        self.queue = queue.Queue(maxsize=1000)
        self.session = requests.Session()
        self.session.timeout = 5

        self.worker = threading.Thread(
            target=self._worker,
            daemon=True,
            name="DiscordWebhookWorker"
        )
        self.worker.start()

    def _worker(self):
        """Background thread - sends messages."""
        while True:
            try:
                message = self.queue.get()
                if message is None:
                    break
                self.session.post(
                    self.webhook_url,
                    json={"content": message},
                    timeout=5
                )
            except Exception:
                pass
            finally:
                self.queue.task_done()

    def emit(self, record):
        """Add log record to queue."""
        try:
            message = self.format(record)
            self.queue.put_nowait(message)
        except queue.Full:
            pass
        except Exception:
            self.handleError(record)

    def close(self):
        """Cleanup."""
        try:
            self.queue.join()
            self.queue.put(None)
            self.worker.join(timeout=5)
        except Exception:
            pass
        finally:
            super().close()


def setup_logging(
    name: str,
    level: int = logging.INFO,
    fmt: Optional[str] = None
) -> logging.Logger:
    """Setup and return a logger instance.

    Args:
        name: Logger name
        level: Logging level
        fmt: Log format string

    Returns:
        Configured logger
    """
    if fmt is None:
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        # Console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)

        # Discord webhook handler (INFO only)
        if WEBHOOK_URL:
            discord_handler = AsyncDiscordHandler(WEBHOOK_URL, level=logging.INFO)
            discord_handler.setFormatter(
                logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            )
            logger.addHandler(discord_handler)

    return logger

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


class AsyncDiscordHandler(logging.Handler):
    """Async Discord webhook handler - non-blocking."""

    def __init__(self, webhook_url: str, level: int = logging.INFO):
        """Initialize Discord handler.

        Args:
            webhook_url: Discord webhook URL
            level: Minimum log level
        """
        super().__init__(level)
        self.webhook_url = webhook_url
        self.queue = queue.Queue(maxsize=1000)
        self.session = requests.Session()
        self.session.timeout = 5

        # Start background worker
        self.worker = threading.Thread(
            target=self._worker,
            daemon=True,
            name="DiscordWebhookWorker",
        )
        self.worker.start()

    def _worker(self):
        """Background thread - sends messages from queue."""
        while True:
            try:
                message = self.queue.get()

                if message is None:  # Shutdown signal
                    break

                self.session.post(
                    self.webhook_url,
                    json={"content": message},
                    timeout=5,
                )

            except requests.RequestException:
                pass
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
    level: Optional[int] = None,
    fmt: Optional[str] = None,
) -> logging.Logger:
    """Setup and return a logger instance.

    Args:
        name: Logger name
        level: Log level
        fmt: Log format string

    Returns:
        Configured logger
    """
    if level is None:
        level = logging.DEBUG if config.DEBUG else logging.INFO

    if fmt is None:
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(
            logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(console_handler)

        # File handler
        os.makedirs("logs", exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename="logs/trading_service.log",
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)

        # Discord webhook handler (INFO only)
        if config.LOG_WEBHOOK_URL:
            discord_handler = AsyncDiscordHandler(
                config.LOG_WEBHOOK_URL,
                level=logging.INFO,
            )
            discord_handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] %(levelname)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(discord_handler)

    return logger

#!/usr/bin/env python3
"""Trading Service - Main entry point.

Runs a continuous BRPOP loop consuming signals from Redis queue.
Also starts the Order Monitor for P&L tracking.
"""

import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.settings import config
from config.redis_config import trading_config
from infrastructure.queue.redis_consumer import RedisConsumer
from infrastructure.broker.ibkr_client import IBKRBroker
from domain.services.trading_service import TradingService
from domain.services.order_monitor import init_order_monitor
from utils.logging_config import setup_logging

logger = setup_logging(
    "trading_service",
    level=logging.DEBUG if config.DEBUG else logging.INFO
)

consumer: RedisConsumer = None
order_monitor = None


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info("Shutdown signal received...")
    if order_monitor:
        order_monitor.stop()
    if consumer:
        consumer.stop()


def main() -> int:
    """Main entry point."""
    global consumer, order_monitor

    logger.info("=" * 50)
    logger.info("Trading Service Starting")
    logger.info("=" * 50)

    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1

    logger.info(f"LiteLLM URL: {config.LITELLM_URL}")
    logger.info(f"IBKR URL: {config.IBEAM_URL}")
    logger.info(f"Account: {config.IB_ACCOUNT_ID}")
    logger.info(f"Model: {trading_config.current_llm_model}")

    params = trading_config.get_all()
    logger.info(f"Emergency Stop: {'ACTIVE' if params['emergency_stop'] else 'Off'}")
    logger.info(f"Execute Orders: {'LIVE' if params['execute_orders'] else 'DRY RUN (simulated)'}")
    logger.info(f"Max VIX: {params['max_vix_level']}")
    logger.info(f"Min Confidence: {params['min_ai_confidence_score']:.0%}")
    # Note: Ticker whitelists are now per-strategy in StrategyConfig

    # Initialize services
    trading_service = TradingService()
    consumer = RedisConsumer()
    
    # Start Order Monitor for P&L tracking (only in live mode)
    if params['execute_orders']:
        broker = IBKRBroker()
        order_monitor = init_order_monitor(broker, poll_interval=30)
        order_monitor.start()
        logger.info("📊 Order Monitor started for P&L tracking")
    else:
        logger.info("📊 Order Monitor disabled (dry run mode)")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    stats = consumer.get_stats()
    logger.info(f"Queue stats: {stats}")

    logger.info("Starting consumer loop (BRPOP)...")
    logger.info("=" * 50)

    try:
        consumer.run(
            handler=trading_service.process_signal,
            timeout=0,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1
    finally:
        if order_monitor:
            order_monitor.stop()
        consumer.close()
        logger.info("Trading Service stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
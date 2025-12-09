#!/usr/bin/env python3
"""EOD Backtest Job - Run after market close to validate signal quality.

This script:
1. Fetches EOD prices for all signals processed today
2. Calculates outcomes (profit/loss)
3. Updates MongoDB with results

Run via Railway cron at 4:30 PM EST (21:30 UTC):
railway run python eod_backtest.py
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from domain.services.backtest_service import get_backtest_service
from utils.logging_config import setup_logging

logger = setup_logging(
    "eod_backtest",
    level=logging.INFO
)


def main() -> int:
    """Run EOD backtest."""
    logger.info("=" * 50)
    logger.info("EOD Backtest Job Starting")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info("=" * 50)
    
    try:
        backtest_svc = get_backtest_service()
        
        # Run backtest for today
        results = backtest_svc.run_eod_backtest()
        
        logger.info("=" * 50)
        logger.info("EOD Backtest Results")
        logger.info("=" * 50)
        logger.info(f"Date: {results.get('date')}")
        logger.info(f"Total signals: {results.get('total')}")
        logger.info(f"Updated: {results.get('updated')}")
        logger.info(f"Failed: {results.get('failed')}")
        logger.info(f"Skipped: {results.get('skipped')}")
        logger.info(f"Profitable: {results.get('profitable')}")
        logger.info(f"Losing: {results.get('losing')}")
        
        if results.get("error"):
            logger.error(f"Error: {results.get('error')}")
            return 1
        
        # Also log summary stats
        summary = backtest_svc.get_backtest_summary(days=7)
        logger.info("=" * 50)
        logger.info("7-Day Summary")
        logger.info("=" * 50)
        logger.info(f"Total signals: {summary.get('total')}")
        logger.info(f"Win rate: {summary.get('win_rate')}%")
        logger.info(f"Executed: {summary.get('executed', {}).get('total')} (win rate: {summary.get('executed', {}).get('win_rate')}%)")
        logger.info(f"Skipped: {summary.get('skipped', {}).get('total')} (missed rate: {summary.get('skipped', {}).get('missed_rate')}%)")
        
        return 0
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

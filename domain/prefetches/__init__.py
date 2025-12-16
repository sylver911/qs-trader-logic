"""Prefetches module - Modular data fetching for LLM analysis.

This module provides a Discord cog-like pattern for prefetching data
before LLM analysis. Each prefetch runs in parallel and provides
Jinja2-compatible data for templates.

Usage:
    from domain.prefetches import PrefetchManager

    manager = PrefetchManager()
    context = manager.fetch_all(signal, {
        "broker": broker,
        "market_data": market_data,
        "trading_config": trading_config,
    })

    # Use in Jinja2 template:
    # {{ time.is_market_open }}
    # {{ account.buying_power }}
    # {{ option_chain.calls[0].strike }}

Adding a new prefetch:
    1. Create file: domain/prefetches/my_prefetch.py
    2. Create class inheriting from Prefetch
    3. Add to ALL_PREFETCHES list below
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from domain.prefetches.base import Prefetch, PrefetchResult
from domain.prefetches.time_prefetch import TimePrefetch
from domain.prefetches.option_chain import OptionChainPrefetch
from domain.prefetches.account import AccountPrefetch
from domain.prefetches.positions import PositionsPrefetch
from domain.prefetches.vix import VixPrefetch

if TYPE_CHECKING:
    from domain.models.signal import Signal

logger = logging.getLogger(__name__)


# All registered prefetches - add new ones here
ALL_PREFETCHES: List[Prefetch] = [
    TimePrefetch(),
    OptionChainPrefetch(),
    AccountPrefetch(),
    PositionsPrefetch(),
    VixPrefetch(),
]


@dataclass
class PrefetchContext:
    """Container for all prefetched data.

    Provides both dict-style and attribute access for Jinja2 templates.
    Access data via: context.time.is_market_open or context["time"]["is_market_open"]
    """
    _results: Dict[str, PrefetchResult]

    def __getattr__(self, name: str) -> Any:
        """Allow dot notation: context.time.is_market_open"""
        if name.startswith('_'):
            raise AttributeError(name)
        result = self._results.get(name)
        if result:
            return result
        raise AttributeError(f"No prefetch with key '{name}'")

    def __getitem__(self, key: str) -> Dict[str, Any]:
        """Allow dict access: context['time']"""
        result = self._results.get(key)
        if result:
            return result.to_template_context()
        return {"error": f"No prefetch with key '{key}'"}

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-compatible get."""
        return self._results.get(key, default)

    def to_template_context(self) -> Dict[str, Any]:
        """Convert all results to a dict for Jinja2 template context.

        Returns a flat dict where each key is the prefetch key,
        and value is the prefetched data.

        Example output:
        {
            "time": {"is_market_open": True, "time_est": "10:30", ...},
            "account": {"available": 10000, "buying_power": 20000, ...},
            "option_chain": {"calls": [...], "puts": [...], ...},
            "positions": {"count": 2, "tickers": ["SPY", "QQQ"], ...},
            "vix": {"value": 18.5, "level": "normal", ...},
        }
        """
        return {
            key: result.to_template_context()
            for key, result in self._results.items()
        }

    def keys(self) -> List[str]:
        """Get all prefetch keys."""
        return list(self._results.keys())

    @property
    def all_successful(self) -> bool:
        """Check if all prefetches succeeded."""
        return all(r.success for r in self._results.values())

    @property
    def errors(self) -> Dict[str, str]:
        """Get all errors."""
        return {
            key: result.error
            for key, result in self._results.items()
            if not result.success and result.error
        }


class PrefetchManager:
    """Manages and runs prefetches in parallel.

    Prefetches are run concurrently using ThreadPoolExecutor.
    Results are collected into a PrefetchContext for easy template access.
    """

    def __init__(self, prefetches: Optional[List[Prefetch]] = None):
        """Initialize with prefetches.

        Args:
            prefetches: List of prefetches to run. Defaults to ALL_PREFETCHES.
        """
        self._prefetches = prefetches if prefetches is not None else ALL_PREFETCHES

    def fetch_all(
        self,
        signal: "Signal",
        context: Dict[str, Any],
        max_workers: int = 5,
    ) -> PrefetchContext:
        """Run all prefetches in parallel.

        Args:
            signal: The trading signal
            context: Shared context (broker, market_data, trading_config)
            max_workers: Max parallel threads

        Returns:
            PrefetchContext with all results
        """
        results: Dict[str, PrefetchResult] = {}

        # Filter prefetches that should run
        prefetches_to_run = [
            p for p in self._prefetches
            if p.should_run(signal, context)
        ]

        logger.info(f"Running {len(prefetches_to_run)} prefetches...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all prefetches
            future_to_prefetch = {
                executor.submit(self._safe_fetch, p, signal, context): p
                for p in prefetches_to_run
            }

            # Collect results as they complete
            for future in as_completed(future_to_prefetch):
                prefetch = future_to_prefetch[future]
                try:
                    result = future.result()
                    results[prefetch.key] = result
                    status = "OK" if result.success else f"ERROR: {result.error}"
                    logger.debug(f"  {prefetch.key}: {status}")
                except Exception as e:
                    logger.error(f"  {prefetch.key}: EXCEPTION: {e}")
                    results[prefetch.key] = PrefetchResult.from_error(str(e))

        # Add empty results for prefetches that were skipped
        for prefetch in self._prefetches:
            if prefetch.key not in results:
                results[prefetch.key] = PrefetchResult.from_error("Skipped")

        logger.info(f"Prefetch complete: {len(results)} results")
        return PrefetchContext(_results=results)

    def _safe_fetch(
        self,
        prefetch: Prefetch,
        signal: "Signal",
        context: Dict[str, Any],
    ) -> PrefetchResult:
        """Safely run a single prefetch with error handling."""
        try:
            return prefetch.fetch(signal, context)
        except Exception as e:
            logger.error(f"Prefetch {prefetch.name} failed: {e}")
            return PrefetchResult.from_error(str(e))

    @property
    def prefetches(self) -> List[Prefetch]:
        """Get list of all prefetches."""
        return self._prefetches

    def add_prefetch(self, prefetch: Prefetch) -> None:
        """Add a prefetch to the manager."""
        self._prefetches.append(prefetch)

    def remove_prefetch(self, key: str) -> bool:
        """Remove a prefetch by key."""
        for i, p in enumerate(self._prefetches):
            if p.key == key:
                self._prefetches.pop(i)
                return True
        return False

    def get_all_docs(self) -> Dict[str, Any]:
        """Get documentation for all prefetches.

        Returns a structured dict with all prefetch documentation,
        suitable for dashboard display and autocomplete.

        Returns:
            {
                "prefetches": [
                    {
                        "key": "time",
                        "name": "current_time",
                        "description": "Current time in EST...",
                        "variables": [
                            {"name": "is_market_open", "type": "bool", "description": "...", "example": "true"},
                            ...
                        ],
                        "example_usage": "{{ time.is_market_open }}"
                    },
                    ...
                ],
                "all_variables": [
                    {"key": "time", "variable": "is_market_open", "type": "bool", "full_path": "time.is_market_open"},
                    ...
                ]
            }
        """
        prefetch_docs = []
        all_variables = []

        for prefetch in self._prefetches:
            doc = prefetch.get_docs()
            prefetch_docs.append(doc)

            # Flatten variables for autocomplete
            for var in doc.get("variables", []):
                all_variables.append({
                    "key": prefetch.key,
                    "variable": var["name"],
                    "type": var["type"],
                    "description": var["description"],
                    "example": var["example"],
                    "full_path": f"{prefetch.key}.{var['name']}",
                    "jinja_syntax": f"{{{{ {prefetch.key}.{var['name']} }}}}",
                })

        return {
            "prefetches": prefetch_docs,
            "all_variables": all_variables,
            "count": len(prefetch_docs),
            "variable_count": len(all_variables),
        }


# Convenience function
def fetch_all(signal: "Signal", context: Dict[str, Any]) -> PrefetchContext:
    """Convenience function to fetch all data."""
    return PrefetchManager().fetch_all(signal, context)


def get_all_docs() -> Dict[str, Any]:
    """Get documentation for all prefetches."""
    return PrefetchManager().get_all_docs()


def sync_docs_to_redis(redis_client=None) -> bool:
    """Sync prefetch documentation to Redis for dashboard access.

    Stores documentation at: config:prefetch_docs

    Args:
        redis_client: Optional Redis client. If None, creates one from settings.

    Returns:
        True if sync successful, False otherwise.

    Dashboard Usage:
        ```python
        import json
        from django.conf import settings
        import redis

        r = redis.from_url(settings.REDIS_URL)
        docs = json.loads(r.get("config:prefetch_docs"))

        # Access prefetches
        for prefetch in docs["prefetches"]:
            print(f"{prefetch['key']}: {prefetch['description']}")
            for var in prefetch["variables"]:
                print(f"  {{ {prefetch['key']}.{var['name']} }} - {var['description']}")

        # For autocomplete, use all_variables
        for var in docs["all_variables"]:
            # var["jinja_syntax"] = "{{ time.is_market_open }}"
            # var["description"] = "NYSE is currently open"
        ```
    """
    import json

    try:
        if redis_client is None:
            import redis
            import os
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            redis_client = redis.from_url(redis_url)

        docs = get_all_docs()
        docs["synced_at"] = __import__("datetime").datetime.now().isoformat()

        redis_client.set(
            "config:prefetch_docs",
            json.dumps(docs, ensure_ascii=False),
        )
        logger.info(f"Synced prefetch docs to Redis: {docs['count']} prefetches, {docs['variable_count']} variables")
        return True

    except Exception as e:
        logger.error(f"Failed to sync prefetch docs to Redis: {e}")
        return False


__all__ = [
    "Prefetch",
    "PrefetchResult",
    "PrefetchContext",
    "PrefetchManager",
    "fetch_all",
    "get_all_docs",
    "sync_docs_to_redis",
    "ALL_PREFETCHES",
    # Individual prefetches
    "TimePrefetch",
    "OptionChainPrefetch",
    "AccountPrefetch",
    "PositionsPrefetch",
    "VixPrefetch",
]

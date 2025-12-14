"""Pytest configuration and shared fixtures - QS Optimized."""

import os
import sys
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Mock external modules before any project imports
# =============================================================================

# Mock ibind (IBKR client library) to avoid connection issues during testing
mock_ibkr_client_instance = MagicMock()
mock_ibkr_client_class = MagicMock(return_value=mock_ibkr_client_instance)

mock_ibind = MagicMock()
mock_ibind.IbkrClient = mock_ibkr_client_class
mock_ibind_client = MagicMock()
mock_ibind_client_ibkr_utils = MagicMock()
mock_ibind_client_ibkr_utils.make_order_request = MagicMock(return_value={})

sys.modules["ibind"] = mock_ibind
sys.modules["ibind.client"] = mock_ibind_client
sys.modules["ibind.client.ibkr_utils"] = mock_ibind_client_ibkr_utils

# Mock Redis to avoid connection issues during testing
mock_redis_client = MagicMock()
mock_redis_module = MagicMock()
mock_redis_module.from_url.return_value = mock_redis_client
sys.modules["redis"] = mock_redis_module


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017/")
    monkeypatch.setenv("MONGO_DB_NAME", "qs_test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("LITELLM_URL", "http://localhost:4000")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.setenv("IBEAM_URL", "http://localhost:5000")
    monkeypatch.setenv("IB_ACCOUNT_ID", "DU1234567")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DEBUG", "true")


@pytest.fixture
def sample_signal_doc() -> Dict[str, Any]:
    """Sample MongoDB signal document."""
    return {
        "_id": "692dc7ab8b19c22400c25705",
        "forum_id": "1373531558274666496",
        "forum_name": "⏰live-0dte-signals",
        "thread_id": "144477652490S4534197",
        "thread_name": "SPY 2025-11-30",
        "created_at": "2025-11-30T19:46:06.187000+00:00",
        "message_count": 2,
        "messages": [
            {
                "content": """SPY QuantSignals V3 0DTE 2025-11-30
**SPY 0DTE Signal | 2025-11-30**
• Direction: BUY CALLS | Confidence: 65%
• Expiry: 2025-12-01
• Strike Focus: $683.00
• Entry Range: $1.77
• Target 1: $2.10
• Stop Loss: $1.40""",
                "timestamp": "2025-11-30T20:46:06.187+01:00",
                "ai": None,
            },
        ],
        "scraped": True,
        "scrape_ready": True,
    }


@pytest.fixture
def sample_option_chain() -> Dict[str, Any]:
    """Sample option chain response."""
    return {
        "symbol": "SPY",
        "expiry": "2024-12-03",
        "available_expiries": ["2024-12-03", "2024-12-06"],
        "calls": [
            {
                "strike": 605.0,
                "lastPrice": 1.85,
                "bid": 1.80,
                "ask": 1.90,
                "volume": 1500,
                "openInterest": 5000,
            },
        ],
        "puts": [],
    }


@pytest.fixture
def sample_position_data() -> List[Dict[str, Any]]:
    """Sample IBKR position data."""
    return [
        {
            "conid": "265598",
            "contractDesc": "SPY",
            "ticker": "SPY",
            "position": 10,
            "avgCost": 450.50,
            "mktValue": 4550.00,
            "unrealizedPnl": 45.00,
        }
    ]


@pytest.fixture
def sample_account_summary() -> Dict[str, Any]:
    """Sample IBKR account summary."""
    return {
        "accountId": "DU1234567",
        "totalcashvalue-s": {"amount": 5000.0, "currency": "USD"},
        "buyingpower": {"amount": 10000.0, "currency": "USD"},
        "netliquidation": {"amount": 15000.0, "currency": "USD"},
    }


@pytest.fixture
def sample_llm_execute_response() -> Dict[str, Any]:
    """Sample LLM response with execute decision."""
    return {
        "content": """{
            "action": "execute",
            "reasoning": "Market open, good R:R of 2.1:1",
            "confidence": 0.75,
            "risk_reward_ratio": 2.1,
            "bracket": {
                "entry_price": 1.85,
                "take_profit": 2.50,
                "stop_loss": 1.40,
                "quantity": 2
            }
        }""",
        "tool_calls": [],
        "model": "deepseek/deepseek-reasoner",
    }


@pytest.fixture
def sample_llm_skip_response() -> Dict[str, Any]:
    """Sample LLM response with skip decision."""
    return {
        "content": """{
            "action": "skip",
            "reasoning": "Market is closed",
            "confidence": 0.95,
            "risk_reward_ratio": null,
            "bracket": null
        }""",
        "tool_calls": [],
        "model": "deepseek/deepseek-reasoner",
    }


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch("redis.from_url") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_mongo():
    """Mock MongoDB client."""
    with patch("pymongo.MongoClient") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_ibkr_client():
    """Mock IBind client."""
    with patch("ibind.IbkrClient") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_litellm():
    """Mock LiteLLM completion."""
    with patch("litellm.completion") as mock:
        yield mock


@pytest.fixture
def mock_yfinance():
    """Mock yfinance."""
    with patch("yfinance.Ticker") as mock:
        ticker = MagicMock()
        mock.return_value = ticker
        yield ticker

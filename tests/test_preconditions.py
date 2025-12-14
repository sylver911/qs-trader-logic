"""Tests for Preconditions - Discord cog-style validation checks."""

import pytest
from unittest.mock import MagicMock

from domain.preconditions import PreconditionManager
from domain.preconditions.base import Precondition
from domain.preconditions.emergency_stop import EmergencyStopPrecondition
from domain.preconditions.ticker_required import TickerRequiredPrecondition
from domain.preconditions.ticker_whitelist import TickerWhitelistPrecondition
from domain.preconditions.ticker_blacklist import TickerBlacklistPrecondition
from domain.preconditions.signal_confidence import SignalConfidencePrecondition
from domain.preconditions.vix_level import VixLevelPrecondition
from domain.preconditions.max_positions import MaxPositionsPrecondition
from domain.preconditions.duplicate_position import DuplicatePositionPrecondition


def create_mock_signal(
    ticker: str = "SPY",
    confidence: float = 0.8,
    content: str = "SPY 0DTE Signal - BUY CALLS @ $2.50",
):
    """Create a mock signal for testing."""
    signal = MagicMock()
    signal.ticker = ticker
    signal.confidence = confidence
    signal.get_full_content.return_value = content
    return signal


def create_mock_context(
    emergency_stop: bool = False,
    execute_orders: bool = False,
    whitelist: list = None,
    blacklist: list = None,
    min_confidence: float = 0.5,
    max_vix: float = 25.0,
    max_positions: int = 5,
    ticker: str = "SPY",
    positions: list = None,
    vix: float = 15.0,
):
    """Create a mock context for testing."""
    trading_config = MagicMock()
    trading_config.emergency_stop = emergency_stop
    trading_config.execute_orders = execute_orders
    trading_config.whitelist_tickers = whitelist or []
    trading_config.blacklist_tickers = blacklist or []
    trading_config.min_ai_confidence_score = min_confidence
    trading_config.max_vix_level = max_vix
    trading_config.max_concurrent_positions = max_positions

    broker = MagicMock()
    broker.get_positions.return_value = positions or []

    market_data = MagicMock()
    market_data.get_vix.return_value = vix

    return {
        "trading_config": trading_config,
        "broker": broker,
        "market_data": market_data,
        "ticker": ticker,
    }


class TestEmergencyStopPrecondition:
    """Tests for EmergencyStopPrecondition."""

    def test_passes_when_inactive(self):
        precondition = EmergencyStopPrecondition()
        signal = create_mock_signal()
        context = create_mock_context(emergency_stop=False)

        result = precondition.check(signal, context)
        assert result is None

    def test_fails_when_active(self):
        precondition = EmergencyStopPrecondition()
        signal = create_mock_signal()
        context = create_mock_context(emergency_stop=True)

        result = precondition.check(signal, context)
        assert result is not None
        assert "emergency stop" in result.lower()

    def test_is_not_live_mode_only(self):
        precondition = EmergencyStopPrecondition()
        assert precondition.live_mode_only is False


class TestTickerRequiredPrecondition:
    """Tests for TickerRequiredPrecondition."""

    def test_passes_with_ticker(self):
        precondition = TickerRequiredPrecondition()
        signal = create_mock_signal(ticker="SPY")
        context = create_mock_context(ticker="SPY")

        result = precondition.check(signal, context)
        assert result is None

    def test_passes_without_ticker_but_with_content(self):
        precondition = TickerRequiredPrecondition()
        signal = create_mock_signal(
            ticker=None,
            content="This is a long signal content that has more than 50 characters for AI analysis"
        )
        context = create_mock_context(ticker=None)

        result = precondition.check(signal, context)
        assert result is None

    def test_fails_without_ticker_and_short_content(self):
        precondition = TickerRequiredPrecondition()
        signal = create_mock_signal(ticker=None, content="Short")
        context = create_mock_context(ticker=None)

        result = precondition.check(signal, context)
        assert result is not None
        assert "no ticker" in result.lower()


class TestTickerWhitelistPrecondition:
    """Tests for TickerWhitelistPrecondition."""

    def test_passes_when_whitelist_empty(self):
        precondition = TickerWhitelistPrecondition()
        signal = create_mock_signal(ticker="AAPL")
        context = create_mock_context(ticker="AAPL", whitelist=[])

        result = precondition.check(signal, context)
        assert result is None

    def test_passes_when_ticker_in_whitelist(self):
        precondition = TickerWhitelistPrecondition()
        signal = create_mock_signal(ticker="SPY")
        context = create_mock_context(ticker="SPY", whitelist=["SPY", "QQQ"])

        result = precondition.check(signal, context)
        assert result is None

    def test_fails_when_ticker_not_in_whitelist(self):
        precondition = TickerWhitelistPrecondition()
        signal = create_mock_signal(ticker="AAPL")
        context = create_mock_context(ticker="AAPL", whitelist=["SPY", "QQQ"])

        result = precondition.check(signal, context)
        assert result is not None
        assert "AAPL" in result
        assert "whitelist" in result.lower()


class TestTickerBlacklistPrecondition:
    """Tests for TickerBlacklistPrecondition."""

    def test_passes_when_blacklist_empty(self):
        precondition = TickerBlacklistPrecondition()
        signal = create_mock_signal(ticker="AAPL")
        context = create_mock_context(ticker="AAPL", blacklist=[])

        result = precondition.check(signal, context)
        assert result is None

    def test_passes_when_ticker_not_in_blacklist(self):
        precondition = TickerBlacklistPrecondition()
        signal = create_mock_signal(ticker="SPY")
        context = create_mock_context(ticker="SPY", blacklist=["MEME", "GME"])

        result = precondition.check(signal, context)
        assert result is None

    def test_fails_when_ticker_in_blacklist(self):
        precondition = TickerBlacklistPrecondition()
        signal = create_mock_signal(ticker="GME")
        context = create_mock_context(ticker="GME", blacklist=["GME", "AMC"])

        result = precondition.check(signal, context)
        assert result is not None
        assert "GME" in result
        assert "blacklist" in result.lower()


class TestSignalConfidencePrecondition:
    """Tests for SignalConfidencePrecondition."""

    def test_passes_when_confidence_above_minimum(self):
        precondition = SignalConfidencePrecondition()
        signal = create_mock_signal(confidence=0.8)
        context = create_mock_context(min_confidence=0.5)

        result = precondition.check(signal, context)
        assert result is None

    def test_passes_when_no_confidence(self):
        """If signal has no confidence score, let it through."""
        precondition = SignalConfidencePrecondition()
        signal = create_mock_signal(confidence=None)
        context = create_mock_context(min_confidence=0.5)

        result = precondition.check(signal, context)
        assert result is None

    def test_fails_when_confidence_below_minimum(self):
        precondition = SignalConfidencePrecondition()
        signal = create_mock_signal(confidence=0.3)
        context = create_mock_context(min_confidence=0.5)

        result = precondition.check(signal, context)
        assert result is not None
        assert "confidence" in result.lower()


class TestVixLevelPrecondition:
    """Tests for VixLevelPrecondition."""

    def test_passes_when_vix_below_max(self):
        precondition = VixLevelPrecondition()
        signal = create_mock_signal()
        context = create_mock_context(max_vix=25.0, vix=15.0)

        result = precondition.check(signal, context)
        assert result is None

    def test_fails_when_vix_above_max(self):
        precondition = VixLevelPrecondition()
        signal = create_mock_signal()
        context = create_mock_context(max_vix=25.0, vix=30.0)

        result = precondition.check(signal, context)
        assert result is not None
        assert "VIX" in result
        assert "30" in result

    def test_passes_when_vix_unavailable(self):
        precondition = VixLevelPrecondition()
        signal = create_mock_signal()
        context = create_mock_context(max_vix=25.0)
        context["market_data"].get_vix.return_value = None

        result = precondition.check(signal, context)
        assert result is None

    def test_is_live_mode_only(self):
        precondition = VixLevelPrecondition()
        assert precondition.live_mode_only is True


class TestMaxPositionsPrecondition:
    """Tests for MaxPositionsPrecondition."""

    def test_passes_when_below_max(self):
        precondition = MaxPositionsPrecondition()
        signal = create_mock_signal()
        context = create_mock_context(
            max_positions=5,
            positions=[{"symbol": "SPY"}, {"symbol": "QQQ"}]
        )

        result = precondition.check(signal, context)
        assert result is None

    def test_fails_when_at_max(self):
        precondition = MaxPositionsPrecondition()
        signal = create_mock_signal()
        context = create_mock_context(
            max_positions=2,
            positions=[{"symbol": "SPY"}, {"symbol": "QQQ"}]
        )

        result = precondition.check(signal, context)
        assert result is not None
        assert "max" in result.lower()

    def test_passes_when_no_positions(self):
        precondition = MaxPositionsPrecondition()
        signal = create_mock_signal()
        context = create_mock_context(max_positions=5, positions=[])

        result = precondition.check(signal, context)
        assert result is None

    def test_is_live_mode_only(self):
        precondition = MaxPositionsPrecondition()
        assert precondition.live_mode_only is True


class TestDuplicatePositionPrecondition:
    """Tests for DuplicatePositionPrecondition."""

    def test_passes_when_no_existing_position(self):
        precondition = DuplicatePositionPrecondition()
        signal = create_mock_signal(ticker="SPY")
        context = create_mock_context(
            ticker="SPY",
            positions=[{"symbol": "QQQ 241206C00500000"}]
        )

        result = precondition.check(signal, context)
        assert result is None

    def test_fails_when_duplicate_position(self):
        precondition = DuplicatePositionPrecondition()
        signal = create_mock_signal(ticker="SPY")
        context = create_mock_context(
            ticker="SPY",
            positions=[{"symbol": "SPY 241206C00605000"}]
        )

        result = precondition.check(signal, context)
        assert result is not None
        assert "SPY" in result
        assert "duplicate" in result.lower()

    def test_passes_when_no_ticker(self):
        precondition = DuplicatePositionPrecondition()
        signal = create_mock_signal(ticker=None)
        context = create_mock_context(ticker=None)

        result = precondition.check(signal, context)
        assert result is None

    def test_passes_when_no_positions(self):
        precondition = DuplicatePositionPrecondition()
        signal = create_mock_signal(ticker="SPY")
        context = create_mock_context(ticker="SPY", positions=[])

        result = precondition.check(signal, context)
        assert result is None

    def test_is_live_mode_only(self):
        precondition = DuplicatePositionPrecondition()
        assert precondition.live_mode_only is True


class TestPreconditionManager:
    """Tests for PreconditionManager."""

    def test_all_preconditions_registered(self):
        manager = PreconditionManager()

        assert len(manager.preconditions) == 8
        names = [p.name for p in manager.preconditions]
        assert "emergency_stop" in names
        assert "ticker_required" in names
        assert "ticker_whitelist" in names
        assert "ticker_blacklist" in names
        assert "signal_confidence" in names
        assert "vix_level" in names
        assert "max_positions" in names
        assert "duplicate_position" in names

    def test_returns_none_when_all_pass(self):
        manager = PreconditionManager()
        signal = create_mock_signal()
        context = create_mock_context()

        result = manager.check_all(signal, context)
        assert result is None

    def test_returns_first_failure(self):
        manager = PreconditionManager()
        signal = create_mock_signal()
        context = create_mock_context(emergency_stop=True)

        result = manager.check_all(signal, context)
        assert result is not None
        assert "emergency" in result.lower()

    def test_skips_live_only_in_dry_run(self):
        manager = PreconditionManager()
        signal = create_mock_signal(ticker="SPY")
        context = create_mock_context(
            execute_orders=False,  # Dry run mode
            ticker="SPY",
            positions=[{"symbol": "SPY 241206C00605000"}],  # Would fail DuplicatePosition
            vix=50.0,  # Would fail VixLevel
        )

        # Should pass because VixLevel and DuplicatePosition are live_mode_only
        result = manager.check_all(signal, context)
        assert result is None

    def test_runs_live_only_in_live_mode(self):
        manager = PreconditionManager()
        signal = create_mock_signal(ticker="SPY")
        context = create_mock_context(
            execute_orders=True,  # Live mode
            ticker="SPY",
            vix=50.0,  # Should fail VixLevel
        )

        result = manager.check_all(signal, context)
        assert result is not None
        assert "VIX" in result


class TestPreconditionOrder:
    """Tests for precondition execution order."""

    def test_emergency_stop_runs_first(self):
        """Emergency stop should block everything else."""
        manager = PreconditionManager()
        signal = create_mock_signal(ticker="GME", confidence=0.1)
        context = create_mock_context(
            emergency_stop=True,
            blacklist=["GME"],  # Also blacklisted
            min_confidence=0.5,  # Also low confidence
        )

        result = manager.check_all(signal, context)
        # Emergency stop should be the failure reason, not blacklist or confidence
        assert "emergency" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

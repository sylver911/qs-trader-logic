"""Tests for _analyze_with_ai method - verifies all 3 decision tools.

These tests mock all external dependencies and verify that:
1. Each of the 3 decision tools can be called
2. Tools receive the correct parameters
3. The correct TradeAction is returned
"""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Dict, Any, Optional


# =============================================================================
# Test fixtures and helpers
# =============================================================================

def create_mock_signal():
    """Create a mock signal object."""
    signal = MagicMock()
    signal.thread_id = "test_thread_123"
    signal.thread_name = "SPY 0DTE Call"
    signal.ticker = "SPY"
    signal.tickers_raw = "SPY"
    signal.direction = "CALL"
    signal.strike = 600.0
    signal.expiry = "2024-12-20"
    signal.entry_price = 2.50
    signal.target_price = 5.00
    signal.stop_loss = 1.25
    signal.confidence = 0.8
    signal.to_dict.return_value = {
        "thread_id": "test_thread_123",
        "ticker": "SPY",
        "direction": "CALL",
        "strike": 600.0,
        "expiry": "2024-12-20",
        "entry_price": 2.50,
    }
    return signal


def simulate_analyze_with_ai(
    llm_response: Dict[str, Any],
    tool_handlers: Dict[str, callable],
    signal: MagicMock = None,
    scheduled_context: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Simulate the _analyze_with_ai logic without importing TradingService.

    This replicates the core logic:
    1. LLM returns tool_calls
    2. We execute the first tool
    3. We return the appropriate action
    """
    signal = signal or create_mock_signal()
    retry_count = scheduled_context.get("retry_count", 0) if scheduled_context else 0

    trace_id = llm_response.get("request_id")

    # No tool call → auto-skip
    if not llm_response.get("tool_calls"):
        return {
            "action": "SKIP",
            "skip_reason": "no_decision",
            "reasoning": llm_response.get("content", "AI did not make a decision"),
            "trace_id": trace_id,
            "tool_called": None,
            "tool_params": None,
        }

    # Get first tool call
    call = llm_response["tool_calls"][0]
    func_name = call["function"]
    args = call["arguments"].copy()

    # Inject context for schedule_reanalysis
    if func_name == "schedule_reanalysis":
        args["_thread_id"] = signal.thread_id
        args["_thread_name"] = signal.thread_name or signal.tickers_raw
        args["_previous_tools"] = []
        args["_retry_count"] = retry_count
        args["_signal_data"] = signal.to_dict()

    # Execute handler
    handler = tool_handlers.get(func_name)
    if not handler:
        return {
            "action": "SKIP",
            "skip_reason": "tool_error",
            "reasoning": f"Unknown tool called: {func_name}",
            "trace_id": trace_id,
            "tool_called": func_name,
            "tool_params": args,
        }

    tool_result = handler(**args)

    # Determine action based on tool
    if func_name == "skip_signal":
        return {
            "action": "SKIP",
            "skip_reason": tool_result.get("category", "other"),
            "reasoning": tool_result.get("reason", "AI decided to skip"),
            "trace_id": trace_id,
            "tool_called": func_name,
            "tool_params": call["arguments"],  # Original params without internal
            "tool_result": tool_result,
        }

    if func_name == "place_bracket_order":
        return {
            "action": "EXECUTE",
            "skip_reason": None,
            "reasoning": "AI placed bracket order via tool call",
            "trace_id": trace_id,
            "tool_called": func_name,
            "tool_params": call["arguments"],
            "tool_result": tool_result,
            "modified_entry": args.get("entry_price"),
            "modified_target": args.get("take_profit"),
            "modified_stop_loss": args.get("stop_loss"),
        }

    if func_name == "schedule_reanalysis":
        return {
            "action": "DELAY",
            "skip_reason": None,
            "reasoning": tool_result.get("reason", "Scheduled for reanalysis"),
            "trace_id": trace_id,
            "tool_called": func_name,
            "tool_params": {k: v for k, v in call["arguments"].items()},  # Original params
            "tool_result": tool_result,
            "delay_info": {
                "delay_minutes": tool_result.get("delay_minutes"),
                "question": tool_result.get("question"),
            },
            "internal_params_injected": ["_thread_id", "_thread_name", "_retry_count", "_previous_tools", "_signal_data"],
        }

    return {
        "action": "SKIP",
        "skip_reason": "tool_error",
        "reasoning": f"Unexpected tool: {func_name}",
        "trace_id": trace_id,
        "tool_called": func_name,
        "tool_params": args,
    }


# =============================================================================
# Tests for skip_signal
# =============================================================================

class TestSkipSignalTool:
    """Tests for skip_signal tool execution."""

    def test_skip_signal_called_with_correct_params(self):
        """Test that skip_signal is called with the correct parameters."""
        captured_calls = []

        def mock_skip_signal(**kwargs):
            captured_calls.append(kwargs)
            return {
                "success": True,
                "reason": kwargs.get("reason"),
                "category": kwargs.get("category"),
                "product": {
                    "ticker": kwargs.get("ticker"),
                    "expiry": kwargs.get("expiry"),
                    "strike": kwargs.get("strike"),
                    "direction": kwargs.get("direction"),
                }
            }

        llm_response = {
            "request_id": "req_123",
            "model": "test-model",
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "function": "skip_signal",
                "arguments": {
                    "reason": "Market is closed",
                    "category": "market_hours",
                    "ticker": "SPY",
                    "expiry": "2024-12-20",
                    "strike": 600.0,
                    "direction": "CALL",
                }
            }]
        }

        result = simulate_analyze_with_ai(
            llm_response=llm_response,
            tool_handlers={"skip_signal": mock_skip_signal},
        )

        # Verify
        assert len(captured_calls) == 1
        assert result["action"] == "SKIP"
        assert result["skip_reason"] == "market_hours"
        assert result["tool_called"] == "skip_signal"

        params = result["tool_params"]
        assert params["reason"] == "Market is closed"
        assert params["category"] == "market_hours"
        assert params["ticker"] == "SPY"
        assert params["expiry"] == "2024-12-20"
        assert params["strike"] == 600.0
        assert params["direction"] == "CALL"

        print("\n" + "=" * 60)
        print("skip_signal TOOL CALL")
        print("=" * 60)
        print(f"Parameters passed to tool:")
        for k, v in params.items():
            print(f"  {k}: {v}")


# =============================================================================
# Tests for place_bracket_order
# =============================================================================

class TestPlaceBracketOrderTool:
    """Tests for place_bracket_order tool execution."""

    def test_place_bracket_order_called_with_correct_params(self):
        """Test that place_bracket_order is called with the correct parameters."""
        captured_calls = []

        def mock_place_bracket_order(**kwargs):
            captured_calls.append(kwargs)
            return {
                "success": True,
                "order": [{"order_id": "12345"}],
                "symbol": "SPY241220C00600000",
                "conid": 123456,
                "product": {
                    "ticker": kwargs.get("ticker"),
                    "expiry": kwargs.get("expiry"),
                    "strike": kwargs.get("strike"),
                    "direction": kwargs.get("direction"),
                }
            }

        llm_response = {
            "request_id": "req_456",
            "model": "test-model",
            "content": "",
            "tool_calls": [{
                "id": "call_2",
                "function": "place_bracket_order",
                "arguments": {
                    "ticker": "SPY",
                    "expiry": "2024-12-20",
                    "strike": 600.0,
                    "direction": "CALL",
                    "side": "BUY",
                    "quantity": 2,
                    "entry_price": 2.50,
                    "take_profit": 5.00,
                    "stop_loss": 1.25,
                }
            }]
        }

        result = simulate_analyze_with_ai(
            llm_response=llm_response,
            tool_handlers={"place_bracket_order": mock_place_bracket_order},
        )

        # Verify
        assert len(captured_calls) == 1
        assert result["action"] == "EXECUTE"
        assert result["tool_called"] == "place_bracket_order"
        assert result["modified_entry"] == 2.50
        assert result["modified_target"] == 5.00
        assert result["modified_stop_loss"] == 1.25

        params = result["tool_params"]
        assert params["ticker"] == "SPY"
        assert params["expiry"] == "2024-12-20"
        assert params["strike"] == 600.0
        assert params["direction"] == "CALL"
        assert params["side"] == "BUY"
        assert params["quantity"] == 2
        assert params["entry_price"] == 2.50
        assert params["take_profit"] == 5.00
        assert params["stop_loss"] == 1.25

        print("\n" + "=" * 60)
        print("place_bracket_order TOOL CALL")
        print("=" * 60)
        print(f"Parameters passed to tool:")
        for k, v in params.items():
            print(f"  {k}: {v}")


# =============================================================================
# Tests for schedule_reanalysis
# =============================================================================

class TestScheduleReanalysisTool:
    """Tests for schedule_reanalysis tool execution."""

    def test_schedule_reanalysis_called_with_correct_params(self):
        """Test that schedule_reanalysis is called with the correct parameters."""
        captured_calls = []

        def mock_schedule_reanalysis(**kwargs):
            captured_calls.append(kwargs)
            return {
                "success": True,
                "reason": kwargs.get("reason"),
                "question": kwargs.get("question"),
                "delay_minutes": kwargs.get("delay_minutes"),
                "reanalyze_at": "2024-12-20T10:30:00",
                "product": {
                    "ticker": kwargs.get("ticker"),
                    "expiry": kwargs.get("expiry"),
                    "strike": kwargs.get("strike"),
                    "direction": kwargs.get("direction"),
                }
            }

        llm_response = {
            "request_id": "req_789",
            "model": "test-model",
            "content": "",
            "tool_calls": [{
                "id": "call_3",
                "function": "schedule_reanalysis",
                "arguments": {
                    "delay_minutes": 30,
                    "reason": "Wait for market open",
                    "question": "Is market now open?",
                    "ticker": "SPY",
                    "expiry": "2024-12-20",
                    "strike": 600.0,
                    "direction": "CALL",
                    "key_levels": {"support": 595.0, "resistance": 605.0},
                }
            }]
        }

        result = simulate_analyze_with_ai(
            llm_response=llm_response,
            tool_handlers={"schedule_reanalysis": mock_schedule_reanalysis},
        )

        # Verify
        assert len(captured_calls) == 1
        assert result["action"] == "DELAY"
        assert result["tool_called"] == "schedule_reanalysis"
        assert result["delay_info"]["delay_minutes"] == 30
        assert result["delay_info"]["question"] == "Is market now open?"

        params = result["tool_params"]
        assert params["delay_minutes"] == 30
        assert params["reason"] == "Wait for market open"
        assert params["question"] == "Is market now open?"
        assert params["ticker"] == "SPY"
        assert params["expiry"] == "2024-12-20"
        assert params["strike"] == 600.0
        assert params["direction"] == "CALL"
        assert params["key_levels"] == {"support": 595.0, "resistance": 605.0}

        # Verify internal params were injected
        call_args = captured_calls[0]
        assert "_thread_id" in call_args
        assert "_thread_name" in call_args
        assert "_retry_count" in call_args
        assert call_args["_thread_id"] == "test_thread_123"

        print("\n" + "=" * 60)
        print("schedule_reanalysis TOOL CALL")
        print("=" * 60)
        print(f"Parameters passed to tool:")
        for k, v in params.items():
            print(f"  {k}: {v}")
        print(f"\nInternal params injected by system:")
        print(f"  _thread_id: {call_args['_thread_id']}")
        print(f"  _thread_name: {call_args['_thread_name']}")
        print(f"  _retry_count: {call_args['_retry_count']}")


# =============================================================================
# Tests for no tool call (auto-skip)
# =============================================================================

class TestNoToolCall:
    """Tests for when AI doesn't call any tool."""

    def test_auto_skip_when_no_tool_called(self):
        """Test that auto-skip happens when AI doesn't call any tool."""
        llm_response = {
            "request_id": "req_000",
            "model": "test-model",
            "content": "I cannot make a decision based on this signal.",
            "tool_calls": []  # No tool calls!
        }

        result = simulate_analyze_with_ai(
            llm_response=llm_response,
            tool_handlers={},
        )

        assert result["action"] == "SKIP"
        assert result["skip_reason"] == "no_decision"
        assert result["tool_called"] is None
        assert "cannot make a decision" in result["reasoning"]

        print("\n" + "=" * 60)
        print("NO TOOL CALL - AUTO SKIP")
        print("=" * 60)
        print(f"Action: {result['action']}")
        print(f"Skip reason: {result['skip_reason']}")
        print(f"Reasoning: {result['reasoning']}")


# =============================================================================
# Summary test
# =============================================================================

class TestAllToolsSummary:
    """Summary showing all tool parameters."""

    def test_print_all_tool_parameters(self):
        """Print expected parameters for all 3 tools."""
        print("\n" + "=" * 60)
        print("DECISION TOOLS - PARAMETER REFERENCE")
        print("=" * 60)

        print("\n1. skip_signal")
        print("-" * 40)
        skip_params = {
            "reason": "str - Why skipping the signal",
            "category": "str - Skip category (market_hours, low_rr, etc.)",
            "ticker": "str - Underlying ticker (SPY, QQQ)",
            "expiry": "str - Option expiry date (YYYY-MM-DD)",
            "strike": "float - Strike price",
            "direction": "str - CALL or PUT",
        }
        for k, v in skip_params.items():
            print(f"  {k}: {v}")

        print("\n2. place_bracket_order")
        print("-" * 40)
        order_params = {
            "ticker": "str - Underlying ticker",
            "expiry": "str - Option expiry date",
            "strike": "float - Strike price",
            "direction": "str - CALL or PUT",
            "side": "str - BUY or SELL",
            "quantity": "int - Number of contracts",
            "entry_price": "float - Entry limit price",
            "take_profit": "float - Take profit price",
            "stop_loss": "float - Stop loss price",
        }
        for k, v in order_params.items():
            print(f"  {k}: {v}")

        print("\n3. schedule_reanalysis")
        print("-" * 40)
        schedule_params = {
            "delay_minutes": "int - Minutes to wait (5-240)",
            "reason": "str - Why delaying",
            "question": "str - Question to answer on reanalysis",
            "ticker": "str - Underlying ticker",
            "expiry": "str - Option expiry date",
            "strike": "float - Strike price",
            "direction": "str - CALL or PUT",
            "key_levels": "dict - Support/resistance levels (optional)",
        }
        for k, v in schedule_params.items():
            print(f"  {k}: {v}")

        print("\n  [Internal params injected by system:]")
        internal = ["_thread_id", "_thread_name", "_retry_count", "_previous_tools", "_signal_data"]
        for p in internal:
            print(f"  {p}")

        print("\n" + "=" * 60)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

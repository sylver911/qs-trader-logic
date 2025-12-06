"""Tests for LLM Client."""

import json
import pytest
from unittest.mock import MagicMock, patch, ANY
from pathlib import Path

from infrastructure.ai.llm_client import LLMClient


class TestLLMClientInit:
    """Test LLM client initialization."""

    def test_default_template_dir(self):
        """Test default template directory is set."""
        client = LLMClient()

        assert client._template_dir is not None
        assert "templates" in client._template_dir

    def test_custom_template_dir(self, tmp_path):
        """Test custom template directory."""
        client = LLMClient(template_dir=str(tmp_path))

        assert client._template_dir == str(tmp_path)


class TestRenderPrompt:
    """Test prompt rendering."""

    def test_render_simple_template(self, tmp_path):
        """Test rendering a simple template."""
        # Create test template
        template_file = tmp_path / "test.j2"
        template_file.write_text("Hello {{ name }}!")

        client = LLMClient(template_dir=str(tmp_path))
        result = client.render_prompt("test.j2", {"name": "World"})

        assert result == "Hello World!"

    def test_render_missing_template_raises(self, tmp_path):
        """Test that missing template raises error."""
        client = LLMClient(template_dir=str(tmp_path))

        with pytest.raises(Exception):
            client.render_prompt("nonexistent.j2", {})


class TestAnalyzeSignal:
    """Test analyze_signal function."""

    @patch("infrastructure.ai.llm_client.completion")
    def test_analyze_signal_returns_response(self, mock_completion, tmp_path):
        """Test that analyze_signal returns proper response structure."""
        # Setup mock
        mock_message = MagicMock()
        mock_message.content = '{"action": "skip", "reasoning": "test"}'
        mock_message.tool_calls = None

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )

        mock_completion.return_value = mock_response

        # Create minimal template
        template_file = tmp_path / "signal_analysis.j2"
        template_file.write_text("Analyze: {{ signal.ticker }}")

        client = LLMClient(template_dir=str(tmp_path))
        result = client.analyze_signal(
            signal_data={"ticker": "SPY"},
            market_data={},
            portfolio_data={},
            trading_params={},
        )

        assert "content" in result
        assert "tool_calls" in result
        assert "model" in result
        assert "usage" in result

    @patch("infrastructure.ai.llm_client.completion")
    def test_analyze_signal_with_tools(self, mock_completion, tmp_path):
        """Test analyze_signal passes tools correctly."""
        mock_message = MagicMock()
        mock_message.content = ""
        mock_message.tool_calls = [
            MagicMock(
                id="call_123",
                function=MagicMock(
                    name="get_current_time",
                    arguments="{}",
                ),
            )
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )

        mock_completion.return_value = mock_response

        template_file = tmp_path / "signal_analysis.j2"
        template_file.write_text("Test")

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get time",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        client = LLMClient(template_dir=str(tmp_path))
        result = client.analyze_signal(
            signal_data={"ticker": "SPY"},
            market_data={},
            portfolio_data={},
            trading_params={},
            tools=tools,
        )

        # Verify tools were passed
        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["tools"] == tools
        assert call_kwargs["tool_choice"] == "auto"

        # Verify tool calls extracted
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"] == "get_current_time"

    @patch("infrastructure.ai.llm_client.completion")
    def test_analyze_signal_error_handling(self, mock_completion, tmp_path):
        """Test analyze_signal handles errors gracefully."""
        mock_completion.side_effect = Exception("API Error")

        template_file = tmp_path / "signal_analysis.j2"
        template_file.write_text("Test")

        client = LLMClient(template_dir=str(tmp_path))
        result = client.analyze_signal(
            signal_data={"ticker": "SPY"},
            market_data={},
            portfolio_data={},
            trading_params={},
        )

        assert result["content"] == ""
        assert result["tool_calls"] == []
        assert "error" in result


class TestExecuteToolCalls:
    """Test execute_tool_calls function."""

    def test_execute_tool_calls_success(self):
        """Test successful tool execution."""
        client = LLMClient()

        tool_calls = [
            {"id": "call_1", "function": "test_func", "arguments": {"x": 1}},
        ]

        handlers = {
            "test_func": lambda x: {"result": x * 2},
        }

        results = client.execute_tool_calls(tool_calls, handlers)

        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["result"] == {"result": 2}
        assert results[0]["call_id"] == "call_1"

    def test_execute_tool_calls_unknown_function(self):
        """Test handling of unknown function."""
        client = LLMClient()

        tool_calls = [
            {"id": "call_1", "function": "unknown_func", "arguments": {}},
        ]

        handlers = {}

        results = client.execute_tool_calls(tool_calls, handlers)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "Unknown function" in results[0]["error"]

    def test_execute_tool_calls_handler_error(self):
        """Test handling of handler exception."""
        client = LLMClient()

        tool_calls = [
            {"id": "call_1", "function": "bad_func", "arguments": {}},
        ]

        handlers = {
            "bad_func": lambda: 1 / 0,  # Will raise ZeroDivisionError
        }

        results = client.execute_tool_calls(tool_calls, handlers)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "division" in results[0]["error"].lower()

    def test_execute_multiple_tool_calls(self):
        """Test executing multiple tool calls."""
        client = LLMClient()

        tool_calls = [
            {"id": "call_1", "function": "func_a", "arguments": {}},
            {"id": "call_2", "function": "func_b", "arguments": {"n": 5}},
            {"id": "call_3", "function": "unknown", "arguments": {}},
        ]

        handlers = {
            "func_a": lambda: "result_a",
            "func_b": lambda n: n * 2,
        }

        results = client.execute_tool_calls(tool_calls, handlers)

        assert len(results) == 3
        assert results[0]["success"] is True
        assert results[0]["result"] == "result_a"
        assert results[1]["success"] is True
        assert results[1]["result"] == 10
        assert results[2]["success"] is False


class TestContinueWithToolResults:
    """Test continue_with_tool_results function - CRITICAL TESTS."""

    @patch("infrastructure.ai.llm_client.completion")
    def test_continue_with_messages_parameter(self, mock_completion):
        """Test that messages parameter is used correctly."""
        mock_message = MagicMock()
        mock_message.content = '{"action": "skip"}'
        mock_message.tool_calls = None

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]

        mock_completion.return_value = mock_response

        client = LLMClient()

        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User message"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "test", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": '{"result": "ok"}'},
        ]

        result = client.continue_with_tool_results(messages=messages)

        # Verify messages were passed to completion
        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["messages"] == messages

    @patch("infrastructure.ai.llm_client.completion")
    def test_continue_preserves_tool_results_in_messages(self, mock_completion):
        """Test that tool results in messages are preserved and sent."""
        mock_message = MagicMock()
        mock_message.content = "Final response"
        mock_message.tool_calls = None

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]

        mock_completion.return_value = mock_response

        client = LLMClient()

        # Simulate real message history with tool results
        messages = [
            {"role": "system", "content": "You are a trading AI"},
            {"role": "user", "content": "Analyze SPY"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "get_current_time",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_abc123",
                "content": json.dumps({
                    "timestamp": "2024-12-03T11:00:00-05:00",
                    "market_status": "open",
                }),
            },
        ]

        result = client.continue_with_tool_results(messages=messages)

        # Verify the full message history was sent
        call_kwargs = mock_completion.call_args.kwargs
        sent_messages = call_kwargs["messages"]

        assert len(sent_messages) == 4
        assert sent_messages[3]["role"] == "tool"
        assert "market_status" in sent_messages[3]["content"]

    @patch("infrastructure.ai.llm_client.completion")
    def test_continue_can_return_more_tool_calls(self, mock_completion):
        """Test that continue can return additional tool calls."""
        mock_message = MagicMock()
        mock_message.content = ""
        mock_message.tool_calls = [
            MagicMock(
                id="call_456",
                function=MagicMock(
                    name="get_ticker_price",
                    arguments='{"symbol": "SPY"}',
                ),
            )
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]

        mock_completion.return_value = mock_response

        client = LLMClient()

        result = client.continue_with_tool_results(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "get_ticker_price"}}],
        )

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"] == "get_ticker_price"

    @patch("infrastructure.ai.llm_client.completion")
    def test_continue_error_handling(self, mock_completion):
        """Test error handling in continue."""
        mock_completion.side_effect = Exception("Network error")

        client = LLMClient()

        result = client.continue_with_tool_results(
            messages=[{"role": "user", "content": "test"}],
        )

        assert result["content"] == ""
        assert result["tool_calls"] == []
        assert "error" in result


class TestDeepSeekReasonerSupport:
    """Test DeepSeek Reasoner specific features."""

    @patch("infrastructure.ai.llm_client.completion")
    def test_extracts_reasoning_content(self, mock_completion, tmp_path):
        """Test that reasoning_content is extracted for DeepSeek."""
        mock_message = MagicMock()
        mock_message.content = '{"action": "execute"}'
        mock_message.tool_calls = None
        mock_message.reasoning_content = "Let me think about this step by step..."

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )

        mock_completion.return_value = mock_response

        template_file = tmp_path / "signal_analysis.j2"
        template_file.write_text("Test")

        client = LLMClient(template_dir=str(tmp_path))
        result = client.analyze_signal(
            signal_data={"ticker": "SPY"},
            market_data={},
            portfolio_data={},
            trading_params={},
        )

        assert result.get("reasoning_content") == "Let me think about this step by step..."

    @patch("infrastructure.ai.llm_client.completion")
    def test_extracts_reasoning_from_provider_specific(self, mock_completion, tmp_path):
        """Test extracting reasoning from provider_specific_fields."""
        mock_message = MagicMock()
        mock_message.content = '{"action": "skip"}'
        mock_message.tool_calls = None
        mock_message.reasoning_content = None
        mock_message.provider_specific_fields = {
            "reasoning_content": "Alternative reasoning location"
        }

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )

        mock_completion.return_value = mock_response

        template_file = tmp_path / "signal_analysis.j2"
        template_file.write_text("Test")

        client = LLMClient(template_dir=str(tmp_path))
        result = client.analyze_signal(
            signal_data={"ticker": "SPY"},
            market_data={},
            portfolio_data={},
            trading_params={},
        )

        assert result.get("reasoning_content") == "Alternative reasoning location"

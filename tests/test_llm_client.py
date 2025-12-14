"""Tests for LLM Client.

These tests mock all external dependencies:
- Redis (trading_config)
- OpenAI client
- MongoDB prompts
"""

import json
import sys
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path


# =============================================================================
# Mock external dependencies before importing LLMClient
# =============================================================================

# Mock Redis config
mock_trading_config = MagicMock()
mock_trading_config.current_llm_model = "gpt-4o"

# Mock MongoDB prompts
mock_prompts = MagicMock()
mock_prompts.get_system_prompt.return_value = "You are a trading AI assistant."
mock_prompts.get_user_template.return_value = None  # Use file-based template

# Patch modules before import
sys.modules["config.redis_config"] = MagicMock(trading_config=mock_trading_config)
sys.modules["infrastructure.prompts"] = mock_prompts

from infrastructure.ai.llm_client import LLMClient


# =============================================================================
# Test fixtures
# =============================================================================

@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI API response."""
    def _create(content="", tool_calls=None, reasoning_content=None):
        mock_message = MagicMock()
        mock_message.content = content
        mock_message.tool_calls = tool_calls
        mock_message.reasoning_content = reasoning_content
        mock_message.provider_specific_fields = {}

        mock_response = MagicMock()
        mock_response.id = "req_test123"
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        return mock_response
    return _create


@pytest.fixture
def mock_openai_client(mock_openai_response):
    """Create a mock OpenAI client."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_openai_response()
    return mock_client


# =============================================================================
# Tests for LLMClient initialization
# =============================================================================

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


# =============================================================================
# Tests for render_prompt
# =============================================================================

class TestRenderPrompt:
    """Test prompt rendering."""

    def test_render_simple_template(self, tmp_path):
        """Test rendering a simple template."""
        # Create test template
        template_file = tmp_path / "test.j2"
        template_file.write_text("Hello {{ name }}!")

        # Mock get_user_template to return None (use file-based)
        with patch("infrastructure.ai.llm_client.get_user_template", return_value=None):
            client = LLMClient(template_dir=str(tmp_path))
            result = client.render_prompt("test.j2", {"name": "World"})

        assert result == "Hello World!"

    def test_render_missing_template_raises(self, tmp_path):
        """Test that missing template raises error."""
        with patch("infrastructure.ai.llm_client.get_user_template", return_value=None):
            client = LLMClient(template_dir=str(tmp_path))

            with pytest.raises(Exception):
                client.render_prompt("nonexistent.j2", {})


# =============================================================================
# Tests for analyze_signal
# =============================================================================

class TestAnalyzeSignal:
    """Test analyze_signal function."""

    @patch("infrastructure.ai.llm_client.OpenAI")
    @patch("infrastructure.ai.llm_client.get_user_template", return_value=None)
    @patch("infrastructure.ai.llm_client.get_system_prompt", return_value="System prompt")
    def test_analyze_signal_returns_response(
        self, mock_sys_prompt, mock_user_template, mock_openai_class, tmp_path, mock_openai_response
    ):
        """Test that analyze_signal returns proper response structure."""
        # Setup mock
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_openai_response(
            content='{"action": "skip", "reasoning": "test"}'
        )
        mock_openai_class.return_value = mock_client

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
        assert result["content"] == '{"action": "skip", "reasoning": "test"}'

    @patch("infrastructure.ai.llm_client.OpenAI")
    @patch("infrastructure.ai.llm_client.get_user_template", return_value=None)
    @patch("infrastructure.ai.llm_client.get_system_prompt", return_value="System prompt")
    def test_analyze_signal_with_tools(
        self, mock_sys_prompt, mock_user_template, mock_openai_class, tmp_path
    ):
        """Test analyze_signal passes tools correctly."""
        # Create tool call mock
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "place_bracket_order"
        mock_tool_call.function.arguments = '{"ticker": "SPY", "quantity": 1}'

        mock_message = MagicMock()
        mock_message.content = ""
        mock_message.tool_calls = [mock_tool_call]
        mock_message.reasoning_content = None
        mock_message.provider_specific_fields = {}

        mock_response = MagicMock()
        mock_response.id = "req_456"
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        template_file = tmp_path / "signal_analysis.j2"
        template_file.write_text("Test")

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "place_bracket_order",
                    "description": "Place order",
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
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["tools"] == tools
        assert call_kwargs["tool_choice"] == "auto"

        # Verify tool calls extracted
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"] == "place_bracket_order"
        assert result["tool_calls"][0]["arguments"] == {"ticker": "SPY", "quantity": 1}

    @patch("infrastructure.ai.llm_client.OpenAI")
    @patch("infrastructure.ai.llm_client.get_user_template", return_value=None)
    @patch("infrastructure.ai.llm_client.get_system_prompt", return_value="System prompt")
    def test_analyze_signal_error_handling(
        self, mock_sys_prompt, mock_user_template, mock_openai_class, tmp_path
    ):
        """Test analyze_signal handles errors gracefully with fallback."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai_class.return_value = mock_client

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

    @patch("infrastructure.ai.llm_client.OpenAI")
    @patch("infrastructure.ai.llm_client.get_user_template", return_value=None)
    @patch("infrastructure.ai.llm_client.get_system_prompt", return_value="System prompt")
    def test_analyze_signal_with_prefetched_data(
        self, mock_sys_prompt, mock_user_template, mock_openai_class, tmp_path, mock_openai_response
    ):
        """Test that prefetched data is included in the prompt."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_openai_response(content="OK")
        mock_openai_class.return_value = mock_client

        template_file = tmp_path / "signal_analysis.j2"
        template_file.write_text("Base prompt")

        prefetched_data = {
            "time": {
                "time_est": "10:30:00",
                "date": "2024-12-14",
                "day_of_week": "Saturday",
                "market_status": "closed",
                "is_market_open": False,
            },
            "option_chain": {
                "current_price": 605.50,
                "available_expiries": ["2024-12-16", "2024-12-20"],
            },
            "account": {
                "usd_available_for_trading": 10000.00,
                "usd_buying_power": 20000.00,
                "usd_net_liquidation": 50000.00,
            },
            "positions": {
                "count": 2,
                "tickers": ["AAPL", "MSFT"],
            },
        }

        client = LLMClient(template_dir=str(tmp_path))
        result = client.analyze_signal(
            signal_data={"ticker": "SPY"},
            market_data={},
            portfolio_data={},
            trading_params={},
            prefetched_data=prefetched_data,
        )

        # Verify prefetched data was included in prompt
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        user_message = messages[1]["content"]

        assert "PRE-FETCHED DATA" in user_message
        assert "10:30:00" in user_message
        assert "605.50" in user_message
        assert "10,000.00" in user_message


# =============================================================================
# Tests for DeepSeek Reasoner support
# =============================================================================

class TestDeepSeekReasonerSupport:
    """Test DeepSeek Reasoner specific features."""

    @patch("infrastructure.ai.llm_client.OpenAI")
    @patch("infrastructure.ai.llm_client.get_user_template", return_value=None)
    @patch("infrastructure.ai.llm_client.get_system_prompt", return_value="System prompt")
    def test_extracts_reasoning_content(
        self, mock_sys_prompt, mock_user_template, mock_openai_class, tmp_path
    ):
        """Test that reasoning_content is extracted for DeepSeek."""
        mock_message = MagicMock()
        mock_message.content = '{"action": "execute"}'
        mock_message.tool_calls = None
        mock_message.reasoning_content = "Let me think about this step by step..."
        mock_message.provider_specific_fields = {}

        mock_response = MagicMock()
        mock_response.id = "req_789"
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

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

    @patch("infrastructure.ai.llm_client.OpenAI")
    @patch("infrastructure.ai.llm_client.get_user_template", return_value=None)
    @patch("infrastructure.ai.llm_client.get_system_prompt", return_value="System prompt")
    def test_extracts_reasoning_from_provider_specific(
        self, mock_sys_prompt, mock_user_template, mock_openai_class, tmp_path
    ):
        """Test extracting reasoning from provider_specific_fields."""
        mock_message = MagicMock()
        mock_message.content = '{"action": "skip"}'
        mock_message.tool_calls = None
        mock_message.reasoning_content = None
        mock_message.provider_specific_fields = {
            "reasoning_content": "Alternative reasoning location"
        }

        mock_response = MagicMock()
        mock_response.id = "req_000"
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

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


# =============================================================================
# Tests for scheduled reanalysis context
# =============================================================================

class TestScheduledReanalysis:
    """Test scheduled reanalysis context handling."""

    @patch("infrastructure.ai.llm_client.OpenAI")
    @patch("infrastructure.ai.llm_client.get_user_template", return_value=None)
    @patch("infrastructure.ai.llm_client.get_system_prompt", return_value="System prompt")
    def test_scheduled_context_included_in_prompt(
        self, mock_sys_prompt, mock_user_template, mock_openai_class, tmp_path, mock_openai_response
    ):
        """Test that scheduled context is added to prompt."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_openai_response(content="OK")
        mock_openai_class.return_value = mock_client

        template_file = tmp_path / "signal_analysis.j2"
        template_file.write_text("Base prompt")

        scheduled_context = {
            "retry_count": 2,
            "delay_reason": "Waiting for market open",
            "delay_question": "Is the market open now?",
            "key_levels": {"support": 600.0, "resistance": 610.0},
            "previous_analysis": {
                "tools_called": ["get_current_time"],
                "tool_results_summary": {
                    "market_status": "pre-market",
                    "time_est": "09:15:00",
                },
            },
        }

        client = LLMClient(template_dir=str(tmp_path))
        result = client.analyze_signal(
            signal_data={"ticker": "SPY"},
            market_data={},
            portfolio_data={},
            trading_params={},
            scheduled_context=scheduled_context,
        )

        # Verify scheduled context was included in prompt
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        user_message = messages[1]["content"]

        assert "SCHEDULED REANALYSIS" in user_message
        assert "Attempt #2" in user_message
        assert "Waiting for market open" in user_message
        assert "Is the market open now?" in user_message


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

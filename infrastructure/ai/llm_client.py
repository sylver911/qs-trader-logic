"""LiteLLM client for AI signal analysis."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader
from litellm import completion

from config.settings import config
from config.redis_config import trading_config

logger = logging.getLogger(__name__)


class LLMClient:
    """LiteLLM client with Jinja2 templating."""

    def __init__(self, template_dir: Optional[str] = None):
        """Initialize LLM client.

        Args:
            template_dir: Path to Jinja2 templates
        """
        self._template_dir = template_dir or str(
            Path(__file__).parent.parent.parent / "templates"
        )
        self._env = Environment(
            loader=FileSystemLoader(self._template_dir),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Configure LiteLLM
        self._api_base = config.LITELLM_URL
        self._api_key = config.LITELLM_API_KEY

    def render_prompt(
        self,
        template_name: str,
        context: Dict[str, Any],
    ) -> str:
        """Render a Jinja2 template.

        Args:
            template_name: Template file name
            context: Template context variables

        Returns:
            Rendered prompt string
        """
        try:
            template = self._env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            logger.error(f"Template render error: {e}")
            raise

    def analyze_signal(
        self,
        signal_data: Dict[str, Any],
        market_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
        trading_params: Dict[str, Any],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Analyze a trading signal with AI.

        Args:
            signal_data: Signal information
            market_data: Current market data
            portfolio_data: Portfolio state
            trading_params: Trading configuration
            tools: Available tools for function calling

        Returns:
            AI response with decision
        """
        model = trading_config.current_llm_model

        # Render prompt
        context = {
            "signal": signal_data,
            "market": market_data,
            "portfolio": portfolio_data,
            "config": trading_params,
        }

        prompt = self.render_prompt("signal_analysis.j2", context)

        logger.debug(f"Sending prompt to {model}")
        logger.debug(f"Prompt length: {len(prompt)} chars")

        try:
            # Call LiteLLM
            response = completion(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                api_base=self._api_base,
                api_key=self._api_key or "dummy",  # Proxy handles auth
                tools=tools,
                tool_choice="auto" if tools else None,
                temperature=0.3,
                max_tokens=2000,
            )

            # Extract response
            message = response.choices[0].message
            content = message.content or ""

            # Check for tool calls
            tool_calls = []
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "function": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    }
                    for tc in message.tool_calls
                ]

            # Extract reasoning_content for DeepSeek Reasoner
            reasoning_content = getattr(message, "reasoning_content", None)
            if not reasoning_content and hasattr(message, "provider_specific_fields"):
                reasoning_content = message.provider_specific_fields.get("reasoning_content")

            result = {
                "content": content,
                "tool_calls": tool_calls,
                "reasoning_content": reasoning_content,  # Required for DeepSeek Reasoner
                "model": model,
                "_prompt": prompt,  # Store for message history
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            }

            logger.info(f"AI response received, {result['usage']['total_tokens']} tokens")

            return result

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {
                "content": "",
                "tool_calls": [],
                "error": str(e),
                "model": model,
            }

    def _get_system_prompt(self) -> str:
        return """You are a trading execution bot. Your job: execute good signals fast, skip bad ones fast.

    ## STRATEGY
    Small bets, tight stops, let winners run. 
    Trust the signal source. Your job is execution, not second-guessing.

    ## WHEN TO SKIP (only these)
    - Market closed + today's expiry
    - Price moved >3% past entry
    - Signal explicitly says "no trade" or "closed"

    ## WHEN TO EXECUTE
    Everything else. When in doubt → execute with smaller size.

    ## TOOL EFFICIENCY
    - Market closed? → SKIP immediately, no more tools needed
    - One time check is enough
    - Don't gather data after you've decided

    ## OUTPUT FORMAT
    After analysis, respond with:
    {
        "action": "skip" | "execute",
        "reasoning": "brief reason",
        "confidence": 0.0-1.0
    }"""

    def execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        tool_handlers: Dict[str, callable],
    ) -> List[Dict[str, Any]]:
        """Execute tool calls and return results.

        Args:
            tool_calls: List of tool calls from AI
            tool_handlers: Map of function names to handlers

        Returns:
            List of tool results
        """
        results = []

        for call in tool_calls:
            func_name = call["function"]
            args = call["arguments"]

            handler = tool_handlers.get(func_name)
            if handler:
                try:
                    result = handler(**args)
                    results.append({
                        "call_id": call["id"],
                        "function": func_name,
                        "result": result,
                        "success": True,
                    })
                    logger.info(f"Tool {func_name} executed successfully")
                except Exception as e:
                    results.append({
                        "call_id": call["id"],
                        "function": func_name,
                        "error": str(e),
                        "success": False,
                    })
                    logger.error(f"Tool {func_name} failed: {e}")
            else:
                results.append({
                    "call_id": call["id"],
                    "function": func_name,
                    "error": "Unknown function",
                    "success": False,
                })
                logger.warning(f"Unknown tool: {func_name}")

        return results

    def continue_with_tool_results(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Continue conversation after tool execution.

        Args:
            messages: Full message history including tool results
            tools: Available tools for further calls
            model: Model to use

        Returns:
            AI response (may contain more tool_calls)
        """
        model = model or trading_config.current_llm_model

        try:
            response = completion(
                model=model,
                messages=messages,
                api_base=self._api_base,
                api_key=self._api_key or "dummy",
                tools=tools,
                tool_choice="auto" if tools else None,
                temperature=0.3,
                max_tokens=2000,
            )

            message = response.choices[0].message
            content = message.content or ""

            # Check for more tool calls
            tool_calls = []
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "function": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    }
                    for tc in message.tool_calls
                ]

            # Extract reasoning_content for DeepSeek Reasoner
            reasoning_content = getattr(message, "reasoning_content", None)
            if not reasoning_content and hasattr(message, "provider_specific_fields"):
                reasoning_content = message.provider_specific_fields.get("reasoning_content")

            return {
                "content": content,
                "tool_calls": tool_calls,
                "reasoning_content": reasoning_content,  # Required for DeepSeek Reasoner
                "model": model,
            }

        except Exception as e:
            logger.error(f"Continue call failed: {e}")
            return {"content": "", "tool_calls": [], "error": str(e)}
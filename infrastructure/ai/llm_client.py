"""LiteLLM client for AI signal analysis - QS Optimized Version."""

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
        """Render a Jinja2 template."""
        try:
            template = self._env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            logger.error(f"Template render error: {e}")
            raise

    def _get_system_prompt(self) -> str:
        """Get the QS-optimized system prompt."""
        return """You are a QS (QuantSignals) Trade Execution Agent. Your job is to validate trading signals and design optimal bracket orders.

## YOUR ROLE
The QS signal has ALREADY been analyzed by sophisticated AI (Katy AI, 4D framework, options flow analysis). 
Your job is NOT to re-analyze the market. Your job is to:
1. Validate if the trade can be executed NOW (timing, account, market status)
2. Check current prices vs signal prices
3. Design optimal bracket parameters (entry, target, stop)
4. Calculate if Risk:Reward is acceptable

## DECISION FRAMEWORK

### STEP 1: Time Check
- Is market open? If no → SKIP
- Is this 0DTE and market closed? → SKIP
- Is option expired? → SKIP

### STEP 2: Price Validation  
- Get CURRENT option price (use get_option_chain tool)
- Compare to signal's entry price
- If current price >> signal entry (missed the move) → Consider SKIP or MODIFY

### STEP 3: Risk:Reward Calculation
- Risk = Entry - Stop Loss
- Reward = Target - Entry  
- R:R Ratio = Reward / Risk
- If R:R < 1.5 → SKIP (not worth the risk)
- If R:R >= 2.0 → Good trade

### STEP 4: Account Check
- Do we have enough cash? (check get_account_summary)
- Are we at max positions? (check get_positions)

### STEP 5: Design Bracket
If executing, specify:
- entry_price: The limit price to enter
- take_profit: Where to exit for profit
- stop_loss: Where to exit for loss protection
- quantity: Number of contracts (based on risk %)

## TOOL USAGE RULES

**BE EFFICIENT - Each tool call costs time and tokens:**

1. ALWAYS call get_current_time FIRST - if market closed, SKIP immediately
2. If skipping, DON'T call more tools - just provide decision
3. Call get_option_chain to get CURRENT option price for R:R calculation
4. Only call get_account_summary/get_positions if you plan to execute

**REQUIRED tools for EXECUTE decision:**
- get_current_time (market status)
- get_option_chain (current option price)
- get_account_summary (cash available)
- get_positions (position count)

**DO NOT call these if you already decided to SKIP.**

## OUTPUT FORMAT

After gathering info, provide your decision as JSON:

```json
{
    "action": "execute" | "skip",
    "reasoning": "Clear explanation of your decision",
    "confidence": 0.0-1.0,
    "risk_reward_ratio": 2.5,
    "bracket": {
        "entry_price": 1.85,
        "take_profit": 2.50,
        "stop_loss": 1.40,
        "quantity": 2
    }
}
```

For SKIP decisions, bracket can be null:
```json
{
    "action": "skip",
    "reasoning": "Market is closed, cannot execute 0DTE",
    "confidence": 0.95,
    "risk_reward_ratio": null,
    "bracket": null
}
```

## REMEMBER
- Trust the QS signal analysis - it's already done
- Your job is execution validation, not market analysis
- Be decisive - either execute with good R:R or skip
- Small position, tight stop, let winners run"""

    def analyze_signal(
        self,
        signal_data: Dict[str, Any],
        market_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
        trading_params: Dict[str, Any],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Analyze a trading signal with AI."""
        model = trading_config.current_llm_model

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
            response = completion(
                model=model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                api_base=self._api_base,
                api_key=self._api_key or "dummy",
                tools=tools,
                tool_choice="auto" if tools else None,
                temperature=0.3,
                max_tokens=2000,
            )

            message = response.choices[0].message
            content = message.content or ""

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

            reasoning_content = getattr(message, "reasoning_content", None)
            if not reasoning_content and hasattr(message, "provider_specific_fields"):
                reasoning_content = message.provider_specific_fields.get("reasoning_content")

            result = {
                "content": content,
                "tool_calls": tool_calls,
                "reasoning_content": reasoning_content,
                "model": model,
                "_prompt": prompt,
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

    def execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        tool_handlers: Dict[str, callable],
    ) -> List[Dict[str, Any]]:
        """Execute tool calls and return results."""
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
            messages: Full message history INCLUDING tool results already appended
            tools: Available tools for further calls
            model: Model to use

        Returns:
            AI response (may contain more tool_calls)
        """
        model = model or trading_config.current_llm_model

        logger.debug(f"continue_with_tool_results called with {len(messages)} messages")
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            if role == "tool":
                logger.debug(f"  Message {i}: role=tool, call_id={msg.get('tool_call_id', 'N/A')}")
            elif role == "assistant" and msg.get("tool_calls"):
                logger.debug(f"  Message {i}: role=assistant with {len(msg.get('tool_calls', []))} tool_calls")
            else:
                logger.debug(f"  Message {i}: role={role}")

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

            reasoning_content = getattr(message, "reasoning_content", None)
            if not reasoning_content and hasattr(message, "provider_specific_fields"):
                reasoning_content = message.provider_specific_fields.get("reasoning_content")

            logger.debug(f"continue_with_tool_results response: content_len={len(content)}, tool_calls={len(tool_calls)}")

            return {
                "content": content,
                "tool_calls": tool_calls,
                "reasoning_content": reasoning_content,
                "model": model,
            }

        except Exception as e:
            logger.error(f"Continue call failed: {e}", exc_info=True)
            return {"content": "", "tool_calls": [], "error": str(e)}

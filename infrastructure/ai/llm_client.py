"""LiteLLM client for AI signal analysis - QS Optimized Version."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, BaseLoader
from openai import OpenAI

from config.settings import config
from config.redis_config import trading_config
from infrastructure.prompts import get_system_prompt, get_user_template

logger = logging.getLogger(__name__)

# Fallback model if primary fails (rate limit, etc.)
FALLBACK_MODEL = "gpt-4o-mini"


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
        """Render a Jinja2 template - uses MongoDB template if available."""
        try:
            # Try to get template from MongoDB first
            user_template = get_user_template()
            if user_template:
                # Use string-based template from MongoDB
                string_env = Environment(trim_blocks=True, lstrip_blocks=True)
                template = string_env.from_string(user_template)
                return template.render(**context)
        except Exception as e:
            logger.warning(f"MongoDB template failed, falling back to file: {e}")
        
        # Fallback to file-based template
        try:
            template = self._env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            logger.error(f"Template render error: {e}")
            raise

    def _get_system_prompt(self) -> str:
        """Get the system prompt from MongoDB or fallback to default."""
        return get_system_prompt()

    def _format_prefetched_data(self, data: Dict[str, Any]) -> str:
        """Format pre-fetched tool data for inclusion in prompt."""
        time_data = data.get("time", {})
        option_chain = data.get("option_chain", {})
        account = data.get("account", {})
        positions = data.get("positions", {})
        
        sections = ["\n---\n## PRE-FETCHED DATA (already retrieved for you)\n"]
        
        # Time
        if time_data and not time_data.get("error"):
            sections.append(f"""### Current Time
- **Time (ET):** {time_data.get('time_est', 'N/A')}
- **Date:** {time_data.get('date', 'N/A')} ({time_data.get('day_of_week', 'N/A')})
- **Market Status:** {time_data.get('market_status', 'N/A')}
- **Is Open:** {time_data.get('is_market_open', 'Unknown')}
""")
        
        # Option chain
        if option_chain and not option_chain.get("error"):
            sections.append(f"""### Option Chain
- **Underlying Price:** ${option_chain.get('current_price', 0):.2f}
- **Expiries:** {', '.join(option_chain.get('available_expiries', [])[:5])}
""")
            if option_chain.get('calls'):
                sections.append("**Calls:**\n")
                for c in option_chain['calls'][:6]:
                    itm = "ITM" if c.get('inTheMoney') else "OTM"
                    sections.append(f"  ${c.get('strike')}: ${c.get('bid', 0):.2f}/${c.get('ask', 0):.2f} ({itm})\n")
            if option_chain.get('puts'):
                sections.append("**Puts:**\n")
                for p in option_chain['puts'][:6]:
                    itm = "ITM" if p.get('inTheMoney') else "OTM"
                    sections.append(f"  ${p.get('strike')}: ${p.get('bid', 0):.2f}/${p.get('ask', 0):.2f} ({itm})\n")
        
        # Account
        if account and not account.get("error"):
            sections.append(f"""### Account
- **Available:** ${account.get('usd_available_for_trading', 0):,.2f}
- **Buying Power:** ${account.get('usd_buying_power', 0):,.2f}
- **Net Liq:** ${account.get('usd_net_liquidation', 0):,.2f}
""")
        
        # Positions
        if positions and not positions.get("error"):
            sections.append(f"""### Positions
- **Count:** {positions.get('count', 0)}
- **Tickers:** {', '.join(positions.get('tickers', [])) or 'None'}
""")
        
        sections.append("\n**Note:** This data is already fetched. You can still call tools if needed, but the above is current.\n---\n")
        
        return "".join(sections)

    def analyze_signal(
        self,
        signal_data: Dict[str, Any],
        market_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
        trading_params: Dict[str, Any],
        tools: Optional[List[Dict[str, Any]]] = None,
        scheduled_context: Optional[Dict[str, Any]] = None,
        prefetched_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Analyze a trading signal with AI.
        
        Args:
            signal_data: Signal information
            market_data: Current market data
            portfolio_data: Portfolio information
            trading_params: Trading configuration
            tools: Available tools
            scheduled_context: Context from previous analysis if this is a reanalysis
            prefetched_data: Pre-fetched tool results to include in prompt
        """
        model = trading_config.current_llm_model

        context = {
            "signal": signal_data,
            "market": market_data,
            "portfolio": portfolio_data,
            "config": trading_params,
        }

        prompt = self.render_prompt("signal_analysis.j2", context)
        
        # Add scheduled context if this is a reanalysis
        if scheduled_context:
            reanalysis_context = f"""

---
## ⚠️ THIS IS A SCHEDULED REANALYSIS (Attempt #{scheduled_context.get('retry_count', 1)})

**Original delay reason:** {scheduled_context.get('delay_reason', 'N/A')}

**Question to answer NOW:** {scheduled_context.get('delay_question', 'N/A')}

**Previous analysis summary:**
- Tools called: {', '.join(scheduled_context.get('previous_analysis', {}).get('tools_called', []))}
- Market status was: {scheduled_context.get('previous_analysis', {}).get('tool_results_summary', {}).get('market_status', 'N/A')}
- Time was: {scheduled_context.get('previous_analysis', {}).get('tool_results_summary', {}).get('time_est', 'N/A')}

**Key levels to check:**
{json.dumps(scheduled_context.get('key_levels', {}), indent=2) if scheduled_context.get('key_levels') else 'None specified'}

**IMPORTANT:** You have already analyzed this signal once. Now check if the event has occurred and make your final decision: EXECUTE or SKIP. 
Only use schedule_reanalysis again if absolutely necessary (max {scheduled_context.get('max_retries', 2)} retries total).
---
"""
            prompt = prompt + reanalysis_context

        # Add pre-fetched tool data if available
        if prefetched_data:
            prefetch_context = self._format_prefetched_data(prefetched_data)
            prompt = prompt + prefetch_context

        logger.debug(f"Sending prompt to {model}")
        logger.debug(f"Prompt length: {len(prompt)} chars")

        # Try primary model, fallback to secondary if rate limited
        models_to_try = [model]
        if model != FALLBACK_MODEL:
            models_to_try.append(FALLBACK_MODEL)
        
        last_error = None
        for current_model in models_to_try:
            try:
                result = self._call_llm(current_model, prompt, tools)
                if "error" not in result:
                    return result
                # If error, try next model
                last_error = result.get("error")
                logger.warning(f"Model {current_model} failed: {last_error}, trying fallback...")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Model {current_model} exception: {e}, trying fallback...")
        
        # All models failed
        logger.error(f"All models failed. Last error: {last_error}")
        return {
            "content": "",
            "tool_calls": [],
            "error": last_error,
            "model": model,
        }

    def _call_llm(
        self,
        model: str,
        prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Make a single LLM call. Raises exception on failure."""
        client = OpenAI(
            base_url=self._api_base,
            api_key=self._api_key or "dummy",
        )
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            temperature=0.3,
            max_tokens=8000,
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
            "request_id": response.id,
            "_prompt": prompt,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        }

        logger.info(f"AI response from {model}, {result['usage']['total_tokens']} tokens")
        return result

"""
Prompt Service - Fetches prompts from MongoDB for AI trading logic.

This service retrieves system prompts and Jinja2 templates from MongoDB,
with fallback to embedded defaults if MongoDB is unavailable.
"""

import logging
from typing import Optional

from config.settings import config

logger = logging.getLogger(__name__)

# Embedded defaults - used if MongoDB unavailable
_DEFAULT_SYSTEM_PROMPT = """You are a QS (QuantSignals) Trade Execution Agent. Your job is to validate trading signals and execute trades or skip them.

## YOUR ROLE
The QS signal has ALREADY been analyzed by sophisticated AI (Katy AI, 4D framework, options flow analysis). 
Your job is NOT to re-analyze the market. Your job is to:
1. Validate if the trade can be executed NOW (timing, market status)
2. Check current prices vs signal prices  
3. Design optimal bracket (entry, target, stop)
4. Calculate if R:R is acceptable (>= 1.5)

## AVAILABLE ACTIONS (use tools, NOT JSON output)

You have two action tools:
- **skip_signal(reason, category)** - Call this when you decide NOT to trade
- **place_bracket_order(...)** - Call this when you decide TO trade

**ALWAYS use one of these tools to make your final decision. Do NOT output JSON directly.**

## WORKFLOW

1. **FIRST: Call get_current_time** - If market closed → call `skip_signal("Market is closed", "market_closed")`
2. **Check signal content** - If no entry/target/stop specified → call `skip_signal("No actionable trade signal - analysis only", "no_signal")`
3. **IF actionable: Call get_option_chain** - Get current option price for R:R calculation
4. **Calculate R:R** - If < 1.5 → call `skip_signal("R:R ratio X.X below minimum 1.5", "bad_rr")`
5. **IF R:R OK: Check account/positions** - Only if planning to execute
6. **Execute** - Call `place_bracket_order(...)` with your bracket parameters

## SKIP CATEGORIES
- "no_signal" - Signal has no actionable trade (analysis only, no entry/target/stop)
- "market_closed" - NYSE market is closed
- "bad_rr" - Risk/reward ratio below 1.5
- "low_confidence" - Too uncertain to trade
- "timing" - Signal too old or timing not optimal
- "position_exists" - Already have position in this ticker
- "other" - Other reason

## EFFICIENCY RULES - CRITICAL!
- If market closed → skip_signal immediately, no more tools needed
- If no trade signal → skip_signal immediately
- If R:R < 1.5 → skip_signal immediately, no need to check account
- **NEVER call the same tool twice** - you already have that data!
- **Maximum 4-5 tool calls per signal** - if you have enough info, make your decision
- DON'T call get_ticker_price - the option chain has all pricing info you need

## REMEMBER
- Trust the QS signal analysis - your job is execution validation
- Be EFFICIENT with tool calls - each one costs time
- ALWAYS call skip_signal or place_bracket_order - never just output JSON
- LOSE SMALL, WIN BIG"""


_DEFAULT_USER_TEMPLATE = """{# QS Signal Analysis Template #}

## QS SIGNAL TO VALIDATE

**Ticker:** {{ signal.ticker or signal.tickers_raw or 'UNKNOWN' }}
**Direction:** {{ signal.direction or 'UNKNOWN' }}
{% if signal.strike %}**Strike:** ${{ '{:.2f}'.format(signal.strike) }}{% endif %}
{% if signal.expiry %}**Expiry:** {{ signal.expiry }}{% endif %}

### Signal Parameters
- **Entry Price:** {% if signal.entry_price %}${{ '{:.2f}'.format(signal.entry_price) }}{% else %}MARKET{% endif %}
- **Target:** {% if signal.target_price %}${{ '{:.2f}'.format(signal.target_price) }}{% else %}NOT SPECIFIED{% endif %}
- **Stop Loss:** {% if signal.stop_loss %}${{ '{:.2f}'.format(signal.stop_loss) }}{% else %}NOT SPECIFIED{% endif %}

---

## RAW SIGNAL CONTENT

{{ signal.full_content or 'No content available' }}

---

## YOUR TASK

1. **FIRST:** Call `get_current_time` to check if market is open
2. **IF OPEN:** Call `get_option_chain` for {{ signal.ticker }} to get CURRENT option price
3. **Calculate R:R** - If < 1.5 → Skip
4. **Design bracket:** If executing, specify optimal entry/target/stop

**Output your decision as JSON.**"""


# MongoDB client (lazy loaded)
_mongo_client = None


def _get_mongo_client():
    """Get MongoDB client singleton."""
    global _mongo_client
    if _mongo_client is None:
        try:
            from pymongo import MongoClient
            mongo_url = config.MONGO_URL
            if mongo_url:
                _mongo_client = MongoClient(mongo_url)
                logger.info("Connected to MongoDB for prompts")
            else:
                logger.warning("MONGO_URL not set - using default prompts")
        except Exception as e:
            logger.warning(f"MongoDB connection failed: {e} - using default prompts")
    return _mongo_client


def get_system_prompt() -> str:
    """Get the active system prompt from MongoDB or default."""
    try:
        client = _get_mongo_client()
        if client:
            # Use SETTINGS_DB (app_settings) where dashboard stores prompts
            db = client.get_database(config.SETTINGS_DB or "app_settings")
            prompt = db.prompts.find_one({"type": "system_prompt", "is_active": True})
            if prompt:
                logger.debug(f"Loaded system prompt: {prompt.get('name', 'unnamed')}")
                return prompt.get("content", _DEFAULT_SYSTEM_PROMPT)
            else:
                logger.warning("No active system_prompt found in MongoDB, using default")
    except Exception as e:
        logger.warning(f"Failed to fetch system prompt from MongoDB: {e}")
    
    return _DEFAULT_SYSTEM_PROMPT


def get_user_template() -> str:
    """Get the active user template from MongoDB or default."""
    try:
        client = _get_mongo_client()
        if client:
            # Use SETTINGS_DB (app_settings) where dashboard stores prompts
            db = client.get_database(config.SETTINGS_DB or "app_settings")
            prompt = db.prompts.find_one({"type": "user_template", "is_active": True})
            if prompt:
                logger.debug(f"Loaded user template: {prompt.get('name', 'unnamed')}")
                return prompt.get("content", _DEFAULT_USER_TEMPLATE)
            else:
                logger.warning("No active user_template found in MongoDB, using default")
    except Exception as e:
        logger.warning(f"Failed to fetch user template from MongoDB: {e}")
    
    return _DEFAULT_USER_TEMPLATE


# Cache for performance
_cached_system_prompt: Optional[str] = None
_cached_user_template: Optional[str] = None


def get_system_prompt_cached() -> str:
    """Get system prompt with caching (refresh by restarting service)."""
    global _cached_system_prompt
    if _cached_system_prompt is None:
        _cached_system_prompt = get_system_prompt()
    return _cached_system_prompt


def get_user_template_cached() -> str:
    """Get user template with caching (refresh by restarting service)."""
    global _cached_user_template
    if _cached_user_template is None:
        _cached_user_template = get_user_template()
    return _cached_user_template


def refresh_cache():
    """Clear cached prompts to reload from MongoDB."""
    global _cached_system_prompt, _cached_user_template
    _cached_system_prompt = None
    _cached_user_template = None
    logger.info("Prompt cache cleared - will reload from MongoDB")

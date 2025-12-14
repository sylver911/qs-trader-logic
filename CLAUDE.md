# QS Trading Logic - Claude Project Context

## Current Status (2024-12-14)

### Legutóbbi Változtatások

1. **Single LLM Call**: Iteratív tool calling eltávolítva, egyetlen LLM hívás dönt
2. **Decision Tools Only**: AI csak 3 tool-t lát (skip, execute, delay)
3. **Preconditions Module**: Discord cog-szerű moduláris validáció
4. **Prefetch Always**: Mindig prefetch, konfig eltávolítva
5. **Redis Reliable Queue**: BRPOPLPUSH atomic move, dead letter queue

---

## Overview

AI-alapú 0DTE opciós kereskedő rendszer. QuantSignals Discord szignálok feldolgozása.

## Architektúra

```
Discord → Scraper → MongoDB → Redis Queue → Trading Logic (AI) → IBKR
```

## AI Flow (Single LLM Call)

```
Signal → Preconditions → Prefetch Data → LLM → Decision Tool → Done
```

1. **Preconditions**: Hard stopok AI nélkül (emergency, whitelist, VIX, stb.)
2. **Prefetch**: Párhuzamosan lekéri: time, option_chain, account, positions
3. **LLM hívás**: Egyetlen hívás, prefetched data a prompt-ban
4. **Decision Tool**: AI meghívja az egyik tool-t → visszatérés

## Decision Tools (AI csak ezeket látja)

| Tool | Action | Paraméterek |
|------|--------|-------------|
| `skip_signal` | SKIP | reason, category |
| `place_bracket_order` | EXECUTE | ticker, expiry, strike, direction, side, quantity, entry_price, take_profit, stop_loss |
| `schedule_reanalysis` | DELAY | delay_minutes, reason, question, key_levels |

## Preconditions (Discord Cog Pattern)

```
domain/preconditions/
├── __init__.py              # PreconditionManager
├── base.py                  # Precondition ABC
├── emergency_stop.py        # Kill switch
├── ticker_required.py       # Ticker vagy content kell
├── ticker_whitelist.py      # Csak whitelist tickers
├── ticker_blacklist.py      # Blacklist blokkolás
├── signal_confidence.py     # Min confidence check
├── vix_level.py             # Max VIX (live only)
├── max_positions.py         # Max pozíciók (live only)
└── duplicate_position.py    # Duplikált entry (live only)
```

**Új precondition hozzáadása:**
1. Új fájl: `domain/preconditions/my_check.py`
2. Osztály: `class MyCheckPrecondition(Precondition)`
3. Regisztráció: `__init__.py` listába

## Prefetch (Mindig Aktív)

Data tool-ok eredményei bekerülnek a prompt-ba:
- `get_current_time()` → market status
- `get_option_chain()` → bid/ask árak
- `get_account_summary()` → cash, buying power
- `get_positions()` → nyitott pozíciók

## Redis Queue (Reliable Pattern)

```
queue:threads:pending     → LIST (tasks várakoznak)
queue:threads:processing  → LIST (feldolgozás alatt, full JSON)
queue:threads:completed   → SET (kész thread_id-k)
queue:threads:failed      → HASH (hiba info)
queue:threads:dead_letter → LIST (invalid/unparseable)
queue:scheduled           → ZSET (delayed reanalysis)
```

**Atomic move**: `BRPOPLPUSH pending → processing`

## MongoDB (discord_threads)

```javascript
{
  "thread_id": "abc123",
  "ai_processed": true,
  "ai_processed_at": "2024-12-14T10:30:00",
  "trace_id": "langfuse-trace-id",
  "ai_result": {
    "act": "execute" | "skip" | "schedule",
    "reasoning": "...",
    "decision": { ... },
    "trade_result": { ... }
  }
}
```

## Projekt Struktúra

```
qs-trading-logic/
├── main.py
├── config/
│   ├── settings.py
│   └── redis_config.py
├── domain/
│   ├── models/
│   │   ├── signal.py
│   │   ├── trade.py
│   │   └── position.py
│   ├── services/
│   │   ├── trading_service.py    # Fő orchestráció
│   │   └── order_monitor.py      # P&L tracking
│   └── preconditions/            # Moduláris validáció
│       ├── __init__.py
│       ├── base.py
│       └── *.py                  # Egyedi precondition-ök
├── infrastructure/
│   ├── ai/llm_client.py          # Single LLM call
│   ├── broker/ibkr_client.py
│   ├── storage/mongo.py          # MongoHandler
│   ├── prompts/prompt_service.py
│   └── queue/redis_consumer.py   # Reliable queue
├── tools/
│   ├── market_tools.py           # Data tools (prefetch)
│   ├── portfolio_tools.py        # Data tools (prefetch)
│   ├── order_tools.py            # skip_signal, place_bracket_order
│   └── schedule_tools.py         # schedule_reanalysis
└── tests/
```

## Kapcsolódó Projektek

- `dashboard`: Django monitoring UI
- `qs-discord-chat-exporter`: Discord scraper

---

*Utolsó frissítés: 2024-12-14*

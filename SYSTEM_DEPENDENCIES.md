# QS Trading Logic - Teljes Rendszer Dokumentáció

## Tartalom

1. [Áttekintés](#áttekintés)
2. [Külső Rendszerek](#külső-rendszerek)
   - [MongoDB](#mongodb)
   - [Redis](#redis)
   - [LiteLLM Proxy](#litellm-proxy)
   - [IBKR (Interactive Brokers)](#ibkr-interactive-brokers)
   - [yfinance](#yfinance)
3. [Konfigurációk](#konfigurációk)
   - [Environment Variables](#environment-variables)
   - [Redis-alapú Runtime Config](#redis-alapú-runtime-config)
4. [Adatmodellek](#adatmodellek)
   - [Signal (Discord thread)](#signal-discord-thread)
   - [Trade](#trade)
   - [Position](#position)
5. [AI Tools](#ai-tools)
   - [Market Tools (Prefetch)](#market-tools-prefetch)
   - [Portfolio Tools (Prefetch)](#portfolio-tools-prefetch)
   - [Decision Tools (AI választás)](#decision-tools-ai-választás)
6. [Redis Queue Struktúra](#redis-queue-struktúra)
7. [MongoDB Collection Struktúrák](#mongodb-collection-struktúrák)
8. [Prompt Rendszer](#prompt-rendszer)
9. [Preconditions](#preconditions)
10. [Teljes Folyamat](#teljes-folyamat)

---

## Áttekintés

AI-alapú 0DTE opciós kereskedő rendszer. QuantSignals Discord szignálok feldolgozása automatizált döntéshozatallal.

**Architektúra:**
```
Discord → Scraper → MongoDB → Redis Queue → Trading Logic (AI) → IBKR
                                    ↓
                               Langfuse (Tracing)
```

---

## Külső Rendszerek

### MongoDB

**Kapcsolat:**
- **URL**: `MONGO_URL` env var (default: `mongodb://localhost:27017/`)
- **Python library**: `pymongo`
- **Handler**: `infrastructure/storage/mongo.py` → `MongoHandler` class

**Adatbázisok:**

| DB Név | Env Var | Leírás |
|--------|---------|--------|
| `qs` | `MONGO_DB_NAME` / `QS_DB` | Fő adatbázis (threads, trades) |
| `app_settings` | `SETTINGS_DB` | Dashboard által kezelt beállítások (promptok) |

**Collectionök:**

| Collection | DB | Forrás | Leírás |
|------------|-----|--------|--------|
| `discord_threads` | qs | qs-discord-chat-exporter | Discord szignál thread-ek |
| `trades` | qs | trading-logic | Trade execution history + P&L |
| `prompts` | app_settings | dashboard | System prompt + user template |

---

### Redis

**Kapcsolat:**
- **URL**: `REDIS_URL` env var (default: `redis://localhost:6379/0`)
- **Python library**: `redis-py`
- **Handler**: `infrastructure/queue/redis_consumer.py` → `RedisConsumer` class
- **Config**: `config/redis_config.py` → `TradingConfig` class

**Queue Kulcsok (Reliable Queue Pattern):**

| Kulcs | Típus | Leírás |
|-------|-------|--------|
| `queue:threads:pending` | LIST | Feldolgozásra váró task-ok |
| `queue:threads:processing` | LIST | Éppen feldolgozás alatt (full JSON) |
| `queue:threads:completed` | SET | Kész thread_id-k (deduplikáció) |
| `queue:threads:failed` | HASH | Sikertelen task-ok + error info |
| `queue:threads:dead_letter` | LIST | Invalid/unparseable task-ok |
| `queue:scheduled` | ZSET | Delayed reanalysis (score = timestamp) |
| `scheduled:data:{thread_id}` | STRING | Scheduled task context (JSON, TTL: 24h) |

**Config Kulcsok (prefix: `config:trading:`):**

| Kulcs | Típus | Default | Leírás |
|-------|-------|---------|--------|
| `emergency_stop` | bool | `false` | Kill switch |
| `execute_orders` | bool | `false` | `true` = live, `false` = dry run |
| `max_concurrent_positions` | int | `5` | Max nyitott pozíciók |
| `max_vix_level` | float | `25` | Max VIX szint |
| `min_ai_confidence_score` | float | `0.5` | Min signal confidence (0-1) |
| `whitelist_tickers` | list | `["SPY", "QQQ"]` | Globális whitelist |
| `blacklist_tickers` | list | `[]` | Globális blacklist |
| `max_position_size_percent` | float | `0.05` | 5% portfolio per trade |
| `current_llm_model` | str | `"deepseek/deepseek-reasoner"` | AI model |

---

### LiteLLM Proxy

**Kapcsolat:**
- **URL**: `LITELLM_URL` env var (default: `http://localhost:4000`)
- **API Key**: `LITELLM_API_KEY` env var
- **Python library**: `openai` (OpenAI-kompatibilis API)
- **Handler**: `infrastructure/ai/llm_client.py` → `LLMClient` class

**Felhasználás:**
- Proxy a különböző LLM providerekhez (OpenAI, DeepSeek, Anthropic, stb.)
- Model ID: Redis `config:trading:current_llm_model`
- Fallback model: `gpt-4o-mini` (rate limit esetén)

**Response struktúra:**
```python
{
    "content": str,           # Szöveges válasz
    "tool_calls": [           # Tool hívások
        {
            "id": str,
            "function": str,
            "arguments": dict
        }
    ],
    "reasoning_content": str,  # DeepSeek reasoner esetén
    "model": str,
    "request_id": str,         # Langfuse trace_id
    "usage": {
        "prompt_tokens": int,
        "completion_tokens": int,
        "total_tokens": int
    }
}
```

---

### IBKR (Interactive Brokers)

**Kapcsolat:**
- **IBeam URL**: `IBEAM_URL` env var (default: `http://localhost:5000`)
- **Account ID**: `IB_ACCOUNT_ID` env var
- **Python library**: `ibind` (v0.1.21)
- **Handler**: `infrastructure/broker/ibkr_client.py` → `IBKRBroker` class

**Szolgáltatások:**

| Funkció | Leírás |
|---------|--------|
| `check_health()` | Connection ellenőrzés |
| `get_accounts()` | Account lista |
| `get_positions()` | Nyitott pozíciók |
| `get_account_summary()` | Cash, buying power |
| `get_live_orders()` | Aktív megbízások |
| `search_contract()` | Conid lookup (STK, OPT) |
| `place_bracket_order()` | Entry + TP + SL együtt |
| `cancel_order()` | Megbízás törlés |

**OCC Option Symbol Format:**
```
SPY 241209C00605000
└─┬┘ └──┬──┘└┘└───┬──┘
  │     │    │     │
  │     │    │     └─ Strike * 1000 (605.000)
  │     │    └─ C=Call, P=Put
  │     └─ YYMMDD (2024-12-09)
  └─ Ticker
```

---

### yfinance

**Kapcsolat:**
- Nincs API key (ingyenes)
- **Python library**: `yfinance`
- **Handler**: `infrastructure/broker/market_data.py` → `MarketDataProvider` class

**Felhasználás:**
- **Mindig**: VIX, option chains, historical data
- **Fallback**: Stock árak (ha IBKR nem elérhető)

**Index szimbólumok:**
```python
# yfinance prefix: ^
'^SPX', '^VIX', '^NDX', '^RUT', '^DJX'
```

---

## Konfigurációk

### Environment Variables

**Fájl:** `.env` (projekt gyökér)
**Handler:** `config/settings.py` → `Settings` dataclass

```bash
# MongoDB
MONGO_URL=mongodb://localhost:27017/
MONGO_DB_NAME=qs              # Alternatív: QS_DB
SETTINGS_DB=app_settings      # Prompt storage

# Redis
REDIS_URL=redis://localhost:6379/0

# LiteLLM
LITELLM_URL=http://localhost:4000
LITELLM_API_KEY=              # Opcionális

# IBKR
IBEAM_URL=http://localhost:5000
IB_ACCOUNT_ID=DU1234567       # Kötelező

# Market Data
USE_IBKR_MARKET_DATA=false    # true = IBKR subscription, false = yfinance

# Logging
LOG_LEVEL=INFO
LOG_WEBHOOK_URL=              # Discord webhook
DEBUG=false
```

### Redis-alapú Runtime Config

**Fájl:** `config/redis_config.py` → `TradingConfig` class

Dinamikusan módosítható a dashboard-ból vagy CLI-ből, nem kell újraindítani a service-t.

```python
TradingConfig.DEFAULTS = {
    "emergency_stop": False,
    "execute_orders": False,
    "max_concurrent_positions": 5,
    "max_vix_level": 25,
    "min_ai_confidence_score": 0.5,
    "whitelist_tickers": [],  # EMPTY = all tickers allowed (set in dashboard)
    "blacklist_tickers": [],
    "max_position_size_percent": 0.05,
    "current_llm_model": "deepseek/deepseek-reasoner",
}
```

**FONTOS:** A `whitelist_tickers` és `blacklist_tickers` a **dashboard-ból** állítandó!
- Üres lista (`[]`) = minden ticker megengedett
- A strategy fájlok NEM tartalmaznak hardcode-olt whitelist-et
- Prioritás: Redis config (dashboard) > Strategy defaults

**Getterek:**
```python
trading_config = TradingConfig()
trading_config.emergency_stop       # bool
trading_config.execute_orders       # bool
trading_config.current_llm_model    # str
trading_config.get_all()            # Dict[str, Any]
```

---

## Adatmodellek

### Signal (Discord thread)

**Fájl:** `domain/models/signal.py`
**MongoDB collection:** `qs.discord_threads`
**Forrás:** qs-discord-chat-exporter projekt

```python
@dataclass
class Signal:
    # MongoDB eredeti mezők
    id: str                      # _id (ObjectId string)
    thread_id: str               # Discord thread ID
    forum_id: str                # Discord forum ID
    forum_name: str              # "⏰live-0dte-signals"
    thread_name: str             # "SPY 2024-12-09"
    created_at: Optional[str]    # ISO timestamp
    message_count: int
    messages: List[Message]      # Thread üzenetei
    scraped: bool
    scrape_ready: bool
    collected_at: Optional[str]
    scraped_at: Optional[str]

    # Parsing után kitöltődik
    ticker: Optional[str]        # "SPY"
    tickers_raw: Optional[str]   # "SPY,QQQ,IWM" (ha nem parsable)
    direction: Optional[str]     # "CALL", "PUT", "BUY", "SELL"
    strike: Optional[float]      # 605.0
    entry_price: Optional[float] # 1.77
    target_price: Optional[float]# 2.50
    stop_loss: Optional[float]   # 1.20
    expiry: Optional[str]        # "2024-12-09"
    confidence: Optional[float]  # 0.0-1.0
    position_size: Optional[float]# 0.02 (2%)

@dataclass
class Message:
    content: str
    timestamp: str
    ai: Optional[Dict]           # Katy AI metadata
```

**MongoDB dokumentum (AI feldolgozás után):**
```javascript
{
  "_id": ObjectId("..."),
  "thread_id": "1234567890",
  "forum_id": "9876543210",
  "forum_name": "⏰live-0dte-signals",
  "thread_name": "SPY 2024-12-09",
  "created_at": "2024-12-09T09:30:00",
  "message_count": 3,
  "messages": [
    {"content": "Signal text...", "timestamp": "...", "ai": null}
  ],
  "scraped": true,
  "scrape_ready": true,

  // Trading Logic által hozzáadva
  "ai_processed": true,
  "ai_processed_at": "2024-12-09T09:36:00",
  "trace_id": "litellm-request-id",          // Langfuse trace
  "ai_result": {
    "act": "execute",                         // "execute", "skip", "delay"
    "reasoning": "R:R 2.5:1, good timing",
    "decision": {...},
    "trade_result": {...},
    "model_used": "deepseek/deepseek-reasoner",
    "timestamp": "2024-12-09T09:36:00"
  },

  // Ha scheduled reanalysis
  "scheduled_reanalysis": {
    "reanalyze_at": "2024-12-09T10:00:00",
    "delay_minutes": 30,
    "question": "Is entry still valid after market open?"
  }
}
```

---

### Trade

**Fájl:** `domain/models/trade.py`
**MongoDB collection:** `qs.trades`

```python
class TradeAction(Enum):
    SKIP = "skip"
    EXECUTE = "execute"
    MODIFY = "modify"
    DELAY = "delay"
    ERROR = "error"

@dataclass
class TradeDecision:
    action: TradeAction
    reasoning: str
    confidence: float = 0.0
    modified_entry: Optional[float] = None
    modified_target: Optional[float] = None
    modified_stop_loss: Optional[float] = None
    modified_size: Optional[float] = None
    skip_reason: Optional[str] = None

@dataclass
class TradeResult:
    success: bool
    order_id: Optional[str] = None
    error: Optional[str] = None
    fill_price: Optional[float] = None
    filled_quantity: Optional[int] = None
    simulated: bool = False            # True if dry run
    trade_id: Optional[str] = None     # MongoDB _id
    timestamp: str

@dataclass
class AIResponse:
    decision: TradeDecision
    trade_result: Optional[TradeResult]
    raw_response: str
    model_used: str
    trace_id: Optional[str]            # Langfuse link
    delay_info: Optional[Dict]         # Scheduled reanalysis info
    timestamp: str
```

**MongoDB trades document:**
```javascript
{
  "_id": ObjectId("..."),
  "thread_id": "discord_thread_id",
  "ticker": "SPY 241209C00605000",     // OCC symbol
  "direction": "BUY",
  "entry_price": 1.77,
  "quantity": 1,
  "take_profit": 2.50,
  "stop_loss": 1.20,
  "order_id": "123456",                // IBKR order ID
  "conid": "654321",                   // IBKR contract ID
  "status": "open",                    // open, closed_tp, closed_sl, closed_other
  "entry_time": "2024-12-09T09:36:00",
  "exit_time": null,
  "exit_price": null,
  "pnl": null,
  "exit_reason": null,
  "model_used": "deepseek/deepseek-reasoner",
  "confidence": 0.85,
  "reasoning": "Strong R:R with good timing",
  "product": {
    "ticker": "SPY",
    "expiry": "2024-12-09",
    "strike": 605.0,
    "direction": "CALL"
  },
  "simulated": false,
  "created_at": "2024-12-09T09:36:00",
  "updated_at": "2024-12-09T09:36:00"
}
```

---

### Position

**Fájl:** `domain/models/position.py`
**Forrás:** IBKR API response

```python
@dataclass
class Position:
    conid: str
    symbol: str              # "SPY 241209C00605000"
    quantity: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    currency: str = "USD"

@dataclass
class PortfolioSummary:
    account_id: str
    net_liquidation: float
    total_cash: float
    unrealized_pnl: float
    realized_pnl: float
    positions: List[Position]
```

---

## AI Tools

### Market Tools (Prefetch)

**Fájl:** `tools/market_tools.py`

Automatikusan prefetch-elődnek az LLM hívás előtt.

| Tool | Paraméterek | Visszatérés |
|------|-------------|-------------|
| `get_current_time` | - | `{timestamp, time_est, date, day_of_week, is_market_open, market_status}` |
| `get_ticker_price` | `symbol` | `{symbol, price, currency, timestamp}` |
| `get_option_chain` | `symbol`, `expiry?` | `{symbol, expiry, current_price, calls[], puts[], available_expiries[]}` |
| `get_vix` | - | `{vix, timestamp}` |

### Portfolio Tools (Prefetch)

**Fájl:** `tools/portfolio_tools.py`

| Tool | Paraméterek | Visszatérés |
|------|-------------|-------------|
| `get_account_summary` | - | `{usd_available_for_trading, usd_buying_power, usd_net_liquidation}` |
| `get_positions` | - | `{positions[], count, tickers[]}` |

### Decision Tools (AI választás)

**Fájl:** `tools/order_tools.py`, `tools/schedule_tools.py`

Az AI csak ezeket a tool-okat látja - egyiket KELL hívnia.

**skip_signal:**
```python
{
    "reason": str,      # "No actionable signal", "Market closed", "R:R < 1.5"
    "category": str     # "no_signal", "market_closed", "bad_rr",
                        # "low_confidence", "timing", "position_exists", "other"
}
```

**place_bracket_order:**
```python
{
    "ticker": str,           # "SPY"
    "expiry": str,           # "2024-12-09"
    "strike": float,         # 605.0
    "direction": str,        # "CALL" | "PUT"
    "side": str,             # "BUY" | "SELL"
    "quantity": int,         # 1
    "entry_price": float,    # 1.77
    "take_profit": float,    # 2.50
    "stop_loss": float       # 1.20
}
```

**schedule_reanalysis:**
```python
{
    "delay_minutes": int,    # 5-240
    "reason": str,           # "Waiting for PCE data release"
    "question": str,         # "Has market reacted? Is entry still valid?"
    "key_levels": {          # Optional
        "entry_price": float,
        "target_price": float,
        "stop_loss": float,
        "underlying_price": float
    }
}
```

---

## Redis Queue Struktúra

### Task Format

**Pending queue task (qs-discord-chat-exporter által):**
```json
{
  "thread_id": "1234567890",
  "thread_name": "SPY 2024-12-15"
}
```

**Scheduled reanalysis task:**
```json
{
  "thread_id": "1234567890",
  "thread_name": "SPY 2024-12-15",
  "scheduled_context": {
    "retry_count": 1,
    "delay_reason": "Waiting for market open",
    "delay_question": "Is entry still valid?",
    "key_levels": {...},
    "previous_analysis": {
      "tools_called": ["get_current_time", "get_option_chain"],
      "tool_results_summary": {...}
    },
    "signal_summary": {...}
  }
}
```

### Reliable Queue Flow

```
1. Task érkezik → RPUSH queue:threads:pending
2. Consumer → BRPOPLPUSH pending → processing (atomic)
3. Duplicate check → SISMEMBER completed
4. Handler sikeres → LREM processing + SADD completed
5. Handler hiba → LREM processing + HSET failed
6. Invalid JSON → LREM processing + LPUSH dead_letter
```

### Scheduled Reanalysis Flow

```
1. AI calls schedule_reanalysis(delay_minutes=30)
2. → ZADD queue:scheduled {thread_id: future_timestamp}
3. → SET scheduled:data:{thread_id} {context_json}
4. Consumer loop (30s interval):
   → ZRANGEBYSCORE queue:scheduled 0 NOW
   → Process due items
   → ZREM queue:scheduled
   → DELETE scheduled:data:{thread_id}
```

---

## MongoDB Collection Struktúrák

### discord_threads (qs DB)

**Index-ek:**
- `thread_id` (unique)
- `forum_id`
- `ai_processed`
- `created_at`

**Scraper által írott mezők:**
```javascript
{
  "thread_id": "string",
  "forum_id": "string",
  "forum_name": "string",
  "thread_name": "string",
  "created_at": "ISO date",
  "message_count": "number",
  "messages": [
    {
      "content": "string",
      "timestamp": "ISO date",
      "ai": {"prediction": "...", ...}  // Katy AI metadata
    }
  ],
  "scraped": true,
  "scrape_ready": true,
  "collected_at": "ISO date",
  "scraped_at": "ISO date"
}
```

**Trading Logic által hozzáadott mezők:**
```javascript
{
  "ai_processed": true,
  "ai_processed_at": "ISO date",
  "trace_id": "string",
  "ai_result": {
    "act": "execute|skip|delay",
    "reasoning": "string",
    "decision": {...},
    "trade_result": {...},
    "model_used": "string",
    "timestamp": "ISO date"
  },
  "scheduled_reanalysis": {
    "reanalyze_at": "ISO date",
    "delay_minutes": "number",
    "question": "string"
  }
}
```

### trades (qs DB)

**Index-ek:**
- `thread_id`
- `status`
- `entry_time`

Lásd: [Trade datamodel](#trade)

### prompts (app_settings DB)

**Dashboard által kezelve.**

```javascript
{
  "_id": ObjectId,
  "type": "system_prompt" | "user_template",
  "name": "Production v3",
  "content": "You are a QS Trade Execution Agent...",
  "is_active": true,
  "created_at": "ISO date",
  "updated_at": "ISO date",
  "version": 3
}
```

---

## Prompt Rendszer

**Fájl:** `infrastructure/prompts/prompt_service.py`

### Betöltési sorrend

1. **MongoDB** (`app_settings.prompts`)
   - `type: "system_prompt"`, `is_active: true`
   - `type: "user_template"`, `is_active: true`
2. **Fallback**: Beágyazott default-ok (`_DEFAULT_SYSTEM_PROMPT`, `_DEFAULT_USER_TEMPLATE`)

### System Prompt tartalma

```
Role: QS Trade Execution Agent
- NOT market analysis, only execution validation
- Trust QS signal analysis

Workflow:
1. Check time → If closed → skip_signal
2. Check signal → If no entry/target/stop → skip_signal
3. Get option chain → Calculate R:R
4. If R:R < 1.5 → skip_signal
5. If R:R OK → place_bracket_order

Tools: skip_signal, place_bracket_order, schedule_reanalysis

Skip Categories:
- no_signal, market_closed, bad_rr, low_confidence, timing, position_exists, other

Efficiency:
- Max 4-5 tool calls
- NEVER call same tool twice
- Pre-fetched data already in prompt
```

### User Template (Jinja2)

```jinja
## QS SIGNAL TO VALIDATE

**Ticker:** {{ signal.ticker or signal.tickers_raw or 'UNKNOWN' }}
**Direction:** {{ signal.direction or 'UNKNOWN' }}
{% if signal.strike %}**Strike:** ${{ '{:.2f}'.format(signal.strike) }}{% endif %}
{% if signal.expiry %}**Expiry:** {{ signal.expiry }}{% endif %}

### Signal Parameters
- **Entry Price:** {% if signal.entry_price %}${{ ... }}{% else %}MARKET{% endif %}
- **Target:** {% if signal.target_price %}${{ ... }}{% else %}NOT SPECIFIED{% endif %}
- **Stop Loss:** {% if signal.stop_loss %}${{ ... }}{% else %}NOT SPECIFIED{% endif %}

---

## RAW SIGNAL CONTENT

{{ signal.full_content or 'No content available' }}

---

## PRE-FETCHED DATA
(automatikusan hozzáadódik: time, option_chain, account, positions)
```

---

## Preconditions

**Fájl:** `domain/preconditions/`

Discord cog-szerű moduláris validáció - minden forum-ra közös, AI előtt fut.

| Precondition | Fájl | Live Only | Leírás |
|--------------|------|-----------|--------|
| EmergencyStop | `emergency_stop.py` | No | Kill switch check |
| TickerRequired | `ticker_required.py` | No | Kell ticker VAGY content |
| SignalConfidence | `signal_confidence.py` | No | Min confidence check |
| VixLevel | `vix_level.py` | **Yes** | Max VIX (live only) |
| MaxPositions | `max_positions.py` | **Yes** | Max pozíciók (live only) |
| DuplicatePosition | `duplicate_position.py` | **Yes** | Duplikált entry (live only) |

**Execution flow:**
```python
PreconditionManager.check_all(signal, context):
    for precondition in preconditions:
        if precondition.live_mode_only and not is_live:
            continue  # Skip in dry run
        result = precondition.check(signal, context)
        if result is not None:
            return result  # First error stops
    return None  # All passed
```

**Új precondition hozzáadása:**
1. Fájl: `domain/preconditions/my_check.py`
2. Osztály: `class MyCheckPrecondition(Precondition)`
3. Import + lista: `domain/preconditions/__init__.py`

---

## Teljes Folyamat

### 1. Startup (`main.py`)

```python
1. Config validation
2. TradingService init
3. RedisConsumer init
4. OrderMonitor init (if live mode)
5. BRPOP loop start
```

### 2. Task Processing

```
┌─────────────────────────────────────────────────────────────────┐
│ RedisConsumer.pop_task()                                        │
│   BRPOPLPUSH pending → processing                              │
│   Duplicate check (completed set)                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ TradingService.process_signal(task)                            │
│   1. Load signal from MongoDB                                   │
│   2. Run global preconditions                                   │
│      - EmergencyStop                                            │
│      - TickerRequired                                           │
│      - SignalConfidence                                         │
│      - VixLevel (live only)                                     │
│      - MaxPositions (live only)                                 │
│      - DuplicatePosition (live only)                            │
│   3. Strategy routing (StrategyManager)                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ LlmStrategy.execute()                                           │
│   1. Strategy pre-check (forum-specific whitelist/blacklist)    │
│   2. Prefetch (parallel):                                       │
│      - get_current_time                                         │
│      - get_option_chain                                         │
│      - get_account_summary                                      │
│      - get_positions                                            │
│   3. Build prompt (system + user template + prefetched data)    │
│   4. Single LLM call (with decision tools)                      │
│   5. Execute AI's tool call                                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ AI Decision Tool Execution                                      │
│                                                                  │
│ skip_signal:                                                    │
│   → Return SKIP result                                          │
│                                                                  │
│ place_bracket_order:                                            │
│   → If dry_run: Simulate, return success                        │
│   → If live: IBKR order placement                               │
│     1. Build OCC symbol                                         │
│     2. Lookup conid (underlying → option)                       │
│     3. Place bracket (parent + TP child + SL child)             │
│     4. Save to trades collection                                │
│                                                                  │
│ schedule_reanalysis:                                            │
│   → ZADD queue:scheduled                                        │
│   → SET scheduled:data:{thread_id}                              │
│   → Return DELAY result                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Result Saving                                                   │
│   1. Update discord_threads (ai_processed, ai_result)           │
│   2. Save trade (if execute)                                    │
│   3. Redis: complete_task or fail_task                          │
└─────────────────────────────────────────────────────────────────┘
```

### 3. Order Monitor (Live Mode Only)

```
Background thread (30s poll interval):
  1. Get live orders from IBKR
  2. Check for fills
  3. Match with trades collection
  4. Update status + P&L
```

### 4. Scheduled Reanalysis

```
Consumer loop (30s check interval):
  1. ZRANGEBYSCORE queue:scheduled 0 NOW
  2. For each due item:
     - Load scheduled:data:{thread_id}
     - Build task with scheduled_context
     - Process through TradingService
     - ZREM + DELETE scheduled data
```

---

## Kapcsolódó Projektek

| Projekt | Leírás |
|---------|--------|
| `qs-discord-chat-exporter` | Discord scraper → MongoDB + Redis queue |
| `dashboard` | Django monitoring UI (prompt editor, config) |

---

*Dokumentáció generálva: 2024-12-15*

# MongoDB Dokumentáció - QS Trading Logic

## Adatbázis

- **Database**: `qs` (env: `MONGO_DB_NAME`)
- **Connection**: `MONGO_URL` env variable

## Collections

### 1. `discord_threads`

Discord szignál thread-ek tárolása. A scraper írja, a trading logic olvassa és frissíti.

#### Séma

```javascript
{
  "_id": ObjectId,
  "thread_id": "1234567890",           // Discord thread ID (unique)
  "forum_id": "9876543210",            // Discord forum ID
  "forum_name": "0DTE-signals",        // Forum neve
  "thread_name": "SPY 605C 0DTE",      // Thread címe
  "created_at": "2024-12-14T10:00:00",
  "message_count": 5,
  "messages": [                        // Thread üzenetei
    {
      "content": "Entry at $2.50, TP $3.50, SL $1.80",
      "timestamp": "2024-12-14T10:01:00",
      "ai": null                       // Régi AI mezők (nem használt)
    }
  ],

  // Scraper státusz
  "scraped": true,
  "scrape_ready": true,
  "collected_at": "2024-12-14T10:00:30",
  "scraped_at": "2024-12-14T10:01:00",

  // Trading Logic által írt mezők
  "ai_processed": true,
  "ai_processed_at": "2024-12-14T10:02:00",
  "trace_id": "langfuse-abc123",       // Langfuse trace (opcionális)
  "ai_result": {                       // AI döntés részletei
    "act": "execute",                  // "execute" | "skip" | "schedule"
    "reasoning": "Good R:R ratio...",
    "model_used": "gpt-4",
    "timestamp": "2024-12-14T10:02:00",
    "decision": {
      "action": "execute",
      "reasoning": "...",
      "confidence": 0.85,
      "modified_entry": 2.50,
      "modified_target": 3.50,
      "modified_stop_loss": 1.80,
      "modified_size": 5,
      "skip_reason": null
    },
    "trade_result": {                  // Ha execute volt
      "success": true,
      "order_id": "12345",
      "trade_id": "T-abc123",
      "error": null,
      "fill_price": 2.52,
      "filled_quantity": 5,
      "simulated": false,
      "timestamp": "2024-12-14T10:02:01"
    }
  },
  "scheduled_reanalysis": {            // Ha schedule volt
    "delay_minutes": 30,
    "reason": "Waiting for PCE data",
    "question": "Has market reacted?"
  }
}
```

#### Műveletek (Trading Service)

| Művelet | Metódus | Mikor |
|---------|---------|-------|
| **READ** | `_load_signal()` | Signal betöltése feldolgozáshoz |
| **UPDATE** | `_save_result()` | AI execute/skip eredmény mentése |
| **UPDATE** | `_save_skip_result()` | Precondition skip mentése |
| **UPDATE** | `_save_delay_result()` | Schedule reanalysis mentése |

#### Indexek (ajánlott)

```javascript
db.discord_threads.createIndex({ "thread_id": 1 }, { unique: true })
db.discord_threads.createIndex({ "ai_processed": 1, "scraped": 1 })
db.discord_threads.createIndex({ "created_at": -1 })
```

---

### 2. `trades`

Végrehajtott trade-ek és P&L tracking.

#### Séma

```javascript
{
  "_id": ObjectId,
  "thread_id": "1234567890",           // Forrás signal thread
  "ticker": "SPY",
  "symbol": "SPY 241214C00605000",     // OCC symbol
  "direction": "CALL",
  "side": "BUY",
  "quantity": 5,
  "entry_price": 2.50,
  "take_profit": 3.50,
  "stop_loss": 1.80,
  "conid": "123456789",                // IBKR contract ID
  "order_id": "ORD-12345",             // IBKR order ID
  "model_used": "gpt-4",
  "confidence": 0.85,

  // Státusz
  "status": "open",                    // "open" | "closed_tp" | "closed_sl" | "closed_manual" | "closed_expired"
  "entry_time": "2024-12-14T10:02:01",
  "created_at": "2024-12-14T10:02:01",

  // Exit (ha lezárva)
  "exit_price": 3.45,
  "exit_time": "2024-12-14T14:30:00",
  "exit_reason": "Take profit hit",
  "pnl": 475.00,                       // Realized P&L
  "updated_at": "2024-12-14T14:30:00"
}
```

#### Műveletek (TradesRepository)

| Művelet | Metódus | Leírás |
|---------|---------|--------|
| **INSERT** | `save_trade()` | Új trade mentése execute után |
| **UPDATE** | `update_trade()` | Trade frissítése |
| **UPDATE** | `close_trade()` | Trade lezárása exit adatokkal |
| **READ** | `find_trade_by_order_id()` | Trade keresés IBKR order ID alapján |
| **READ** | `find_trade_by_thread_id()` | Nyitott trade keresés thread alapján |
| **READ** | `get_open_trades()` | Összes nyitott trade |
| **READ** | `get_recent_trades()` | Legutóbbi trade-ek |
| **AGGREGATE** | `get_stats()` | P&L statisztikák |

#### Indexek (ajánlott)

```javascript
db.trades.createIndex({ "thread_id": 1 })
db.trades.createIndex({ "order_id": 1 })
db.trades.createIndex({ "status": 1 })
db.trades.createIndex({ "created_at": -1 })
db.trades.createIndex({ "ticker": 1, "created_at": -1 })
```

---

## MongoHandler API

Context manager pattern a kapcsolatkezeléshez.

```python
from infrastructure.storage.mongo import MongoHandler

# Használat
with MongoHandler() as mongo:
    # READ
    doc = mongo.find_one("discord_threads", query={"thread_id": "123"})
    docs = mongo.find_many("discord_threads", query={"scraped": True}, limit=10)

    # WRITE
    mongo.update_one(
        "discord_threads",
        query={"thread_id": "123"},
        update_data={"ai_processed": True}
    )

    # INSERT
    mongo.insert_one("trades", {"ticker": "SPY", ...})
```

### Metódusok

| Metódus | Paraméterek | Return |
|---------|-------------|--------|
| `find_one(collection, query, projection=None)` | collection név, query dict | `Dict` vagy `None` |
| `find_many(collection, query, projection=None, sort=None, limit=0)` | collection név, query dict | `List[Dict]` |
| `update_one(collection, query, update_data)` | collection név, query dict, update dict | `int` (modified count) |
| `insert_one(collection, document)` | collection név, document dict | `str` (inserted id) |

---

## Adatfolyam

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Discord        │     │  discord_threads │     │  trades         │
│  Scraper        │────▶│  collection      │────▶│  collection     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
      │                        │                        │
      │ INSERT                 │ READ                   │ INSERT
      │ (new threads)          │ UPDATE                 │ UPDATE
      │                        │ (ai_result)            │ (P&L)
      ▼                        ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Trading Logic Service                       │
│                                                                  │
│  1. _load_signal()        - READ discord_threads                │
│  2. _save_result()        - UPDATE discord_threads.ai_result    │
│  3. trades_repo.save()    - INSERT trades                       │
│  4. trades_repo.close()   - UPDATE trades (exit)                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Példa Dokumentumok

### Feldolgozott SKIP signal

```javascript
{
  "thread_id": "1234567890",
  "thread_name": "Market Analysis Today",
  "ai_processed": true,
  "ai_processed_at": "2024-12-14T10:02:00",
  "ai_result": {
    "act": "skip",
    "reasoning": "No actionable trade signal - analysis only",
    "decision": {
      "action": "skip",
      "skip_reason": "No actionable trade signal - analysis only"
    }
  }
}
```

### Feldolgozott EXECUTE signal

```javascript
{
  "thread_id": "1234567891",
  "thread_name": "SPY 605C Entry",
  "ai_processed": true,
  "ai_processed_at": "2024-12-14T10:02:00",
  "trace_id": "langfuse-xyz789",
  "ai_result": {
    "act": "execute",
    "reasoning": "Strong momentum, good R:R at 2:1",
    "model_used": "gpt-4",
    "decision": {
      "action": "execute",
      "confidence": 0.85,
      "modified_entry": 2.50,
      "modified_target": 3.50,
      "modified_stop_loss": 1.80,
      "modified_size": 5
    },
    "trade_result": {
      "success": true,
      "order_id": "ORD-12345",
      "trade_id": "T-abc123",
      "simulated": false
    }
  }
}
```

### Scheduled DELAY signal

```javascript
{
  "thread_id": "1234567892",
  "thread_name": "SPY Pre-PCE Setup",
  "ai_processed": true,
  "ai_processed_at": "2024-12-14T08:00:00",
  "ai_result": {
    "act": "schedule",
    "reasoning": "Waiting for PCE data release at 8:30 AM"
  },
  "scheduled_reanalysis": {
    "delay_minutes": 45,
    "reason": "Waiting for PCE data release",
    "question": "Has the market reacted to PCE? Is the setup still valid?"
  }
}
```

---

*Utolsó frissítés: 2024-12-14*

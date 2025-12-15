# Prefetch Variables - Jinja2 Template Reference

Ez a dokumentum tartalmazza az összes elérhető prefetch változót, amit a Jinja2 promptokban használhatsz.

## Használat

A dashboard prompt szerkesztőjében ezeket a változókat `{{ }}` szintaxissal érheted el:

```jinja2
{% if time.is_market_open %}
Market is OPEN until {{ time.closes_at }}
{% else %}
Market is CLOSED ({{ time.status_reason }})
{% endif %}
```

---

## `time` - Időpont és Market Status

| Változó | Típus | Példa | Leírás |
|---------|-------|-------|--------|
| `time.time_est` | string | `"10:30:45"` | Aktuális idő EST-ben |
| `time.date` | string | `"2025-12-15"` | Aktuális dátum |
| `time.day_of_week` | string | `"Monday"` | Hét napja |
| `time.timestamp` | string | `"2025-12-15T10:30:45-05:00"` | ISO timestamp |
| `time.timezone` | string | `"US/Eastern (ET)"` | Időzóna |
| `time.is_market_open` | bool | `true` / `false` | NYSE nyitva van-e |
| `time.market_status` | string | `"open"` / `"closed"` | Market státusz |
| `time.status_reason` | string | `"market_open"` | Státusz oka |
| `time.closes_at` | string | `"16:00 ET"` | Mikor zár (ha nyitva) |
| `time.opens_at` | string | `"09:30 ET"` | Mikor nyit (ha zárva) |

**status_reason értékek:**
- `market_open` - Nyitva
- `pre_market` - Pre-market (< 09:30)
- `after_hours` - After-hours (> 16:00)
- `weekend` - Hétvége
- `holiday` - Ünnepnap

**Példa:**
```jinja2
Current time: {{ time.time_est }} ET ({{ time.day_of_week }})

{% if time.is_market_open %}
✅ Market is OPEN - closes at {{ time.closes_at }}
{% elif time.status_reason == "pre_market" %}
⏳ Pre-market - opens at {{ time.opens_at }}
{% elif time.status_reason == "weekend" %}
📅 Weekend - market closed
{% else %}
🔒 Market closed ({{ time.status_reason }})
{% endif %}
```

---

## `account` - Számla Információk

| Változó | Típus | Példa | Leírás |
|---------|-------|-------|--------|
| `account.available` | float | `10000.00` | Elérhető készpénz |
| `account.buying_power` | float | `20000.00` | Vásárlóerő |
| `account.net_liquidation` | float | `50000.00` | Nettó likvidációs érték |
| `account.currency` | string | `"USD"` | Pénznem |
| `account.is_simulated` | bool | `true` | Dry run módban van-e |

**Példa:**
```jinja2
💰 Account Summary:
- Available: ${{ "%.2f"|format(account.available) }}
- Buying Power: ${{ "%.2f"|format(account.buying_power) }}

{% if account.is_simulated %}
⚠️ DRY RUN MODE - Orders are simulated
{% endif %}

{% if account.available < 1000 %}
🚨 LOW BALANCE WARNING
{% endif %}
```

---

## `option_chain` - Opciós Lánc

| Változó | Típus | Példa | Leírás |
|---------|-------|-------|--------|
| `option_chain.symbol` | string | `"SPY"` | Ticker |
| `option_chain.current_price` | float | `680.50` | Underlying ár |
| `option_chain.expiry` | string | `"2025-12-15"` | Lejárat |
| `option_chain.available_expiries` | list | `["2025-12-15", ...]` | Elérhető lejáratok |
| `option_chain.calls` | list | `[{...}, ...]` | Call opciók |
| `option_chain.puts` | list | `[{...}, ...]` | Put opciók |
| `option_chain.calls_count` | int | `50` | Call opciók száma |
| `option_chain.puts_count` | int | `50` | Put opciók száma |

**Call/Put objektum mezői:**
| Mező | Típus | Leírás |
|------|-------|--------|
| `strike` | float | Strike ár |
| `bid` | float | Bid ár |
| `ask` | float | Ask ár |
| `last` | float | Utolsó ár |
| `mid` | float | Mid ár (bid+ask)/2 |
| `volume` | int | Volumen |
| `open_interest` | int | Open interest |
| `implied_volatility` | float | IV |
| `in_the_money` | bool | ITM-e |

**Példa:**
```jinja2
📊 {{ option_chain.symbol }} @ ${{ "%.2f"|format(option_chain.current_price) }}
Expiry: {{ option_chain.expiry }}

🟢 CALLS:
{% for call in option_chain.calls[:5] %}
  ${{ call.strike }}: ${{ "%.2f"|format(call.bid) }}/${{ "%.2f"|format(call.ask) }} {% if call.in_the_money %}(ITM){% else %}(OTM){% endif %}
{% endfor %}

🔴 PUTS:
{% for put in option_chain.puts[:5] %}
  ${{ put.strike }}: ${{ "%.2f"|format(put.bid) }}/${{ "%.2f"|format(put.ask) }} {% if put.in_the_money %}(ITM){% else %}(OTM){% endif %}
{% endfor %}

{% set target_strike = 680 %}
{% for call in option_chain.calls if call.strike == target_strike %}
Target ${{ target_strike }} Call: ${{ "%.2f"|format(call.mid) }} mid
{% endfor %}
```

---

## `positions` - Nyitott Pozíciók

| Változó | Típus | Példa | Leírás |
|---------|-------|-------|--------|
| `positions.count` | int | `3` | Pozíciók száma |
| `positions.tickers` | list | `["SPY", "QQQ"]` | Tickerek listája |
| `positions.has_positions` | bool | `true` | Van-e pozíció |
| `positions.items` | list | `[{...}, ...]` | Pozíció objektumok |
| `positions.total_unrealized_pnl` | float | `150.00` | Össz. unrealized P&L |
| `positions.total_market_value` | float | `5000.00` | Össz. piaci érték |
| `positions.is_simulated` | bool | `false` | Szimulált-e |

**Position objektum mezői:**
| Mező | Típus | Leírás |
|------|-------|--------|
| `symbol` | string | Teljes szimbólum |
| `ticker` | string | Ticker (SPY, QQQ) |
| `conid` | string | IBKR contract ID |
| `quantity` | float | Mennyiség |
| `avg_cost` | float | Átlagár |
| `market_value` | float | Piaci érték |
| `unrealized_pnl` | float | Unrealized P&L |
| `realized_pnl` | float | Realized P&L |

**Példa:**
```jinja2
📈 Open Positions: {{ positions.count }}

{% if positions.has_positions %}
{% for pos in positions.items %}
- {{ pos.symbol }}: {{ pos.quantity }} @ ${{ "%.2f"|format(pos.avg_cost) }} (P&L: ${{ "%.2f"|format(pos.unrealized_pnl) }})
{% endfor %}

Total Unrealized P&L: ${{ "%.2f"|format(positions.total_unrealized_pnl) }}
{% else %}
No open positions
{% endif %}

{% if signal.ticker in positions.tickers %}
⚠️ Already have position in {{ signal.ticker }}!
{% endif %}
```

---

## `vix` - Volatilitási Index

| Változó | Típus | Példa | Leírás |
|---------|-------|-------|--------|
| `vix.value` | float | `18.50` | VIX érték |
| `vix.level` | string | `"normal"` | Szint kategória |
| `vix.timestamp` | string | `"2025-12-15T10:30:00"` | Időbélyeg |
| `vix.is_low` | bool | VIX < 15 | Alacsony |
| `vix.is_normal` | bool | 15-20 | Normál |
| `vix.is_elevated` | bool | 20-25 | Emelkedett |
| `vix.is_high` | bool | 25-30 | Magas |
| `vix.is_extreme` | bool | VIX >= 30 | Extrém |

**level értékek:**
- `low` - VIX < 15
- `normal` - 15 <= VIX < 20
- `elevated` - 20 <= VIX < 25
- `high` - 25 <= VIX < 30
- `extreme` - VIX >= 30

**Példa:**
```jinja2
📊 VIX: {{ vix.value }} ({{ vix.level }})

{% if vix.is_extreme %}
🚨 EXTREME VOLATILITY - Consider halting trading
{% elif vix.is_high %}
⚠️ High volatility - Reduce position size
{% elif vix.is_elevated %}
📈 Elevated volatility - Use caution
{% else %}
✅ Normal volatility environment
{% endif %}
```

---

## `signal` - Szignál Adatok

Ezek a szignálból jönnek, nem prefetch-ből:

| Változó | Típus | Leírás |
|---------|-------|--------|
| `signal.ticker` | string | Ticker (SPY) |
| `signal.direction` | string | CALL/PUT/BUY/SELL |
| `signal.strike` | float | Strike ár |
| `signal.expiry` | string | Lejárat |
| `signal.entry_price` | float | Entry ár |
| `signal.target_price` | float | Target ár |
| `signal.stop_loss` | float | Stop loss |
| `signal.confidence` | float | Confidence (0-1) |

---

## Komplex Példa

```jinja2
# {{ signal.ticker }} Analysis - {{ time.date }}

## Market Status
{% if time.is_market_open %}
✅ Market OPEN ({{ time.time_est }} ET) - closes {{ time.closes_at }}
{% else %}
🔒 Market CLOSED - {{ time.status_reason }}
{% endif %}

## Volatility
VIX: {{ vix.value }} ({{ vix.level }})
{% if vix.value > 25 %}⚠️ High VIX - reduce size{% endif %}

## Signal
- Direction: {{ signal.direction }}
- Strike: ${{ signal.strike }}
- Entry: ${{ signal.entry_price }}
- Target: ${{ signal.target_price }}
- Stop: ${{ signal.stop_loss }}

## Current Prices
{{ option_chain.symbol }} underlying: ${{ "%.2f"|format(option_chain.current_price) }}

{% set target_calls = option_chain.calls | selectattr('strike', 'equalto', signal.strike) | list %}
{% if target_calls %}
Target option: ${{ "%.2f"|format(target_calls[0].mid) }} mid
{% endif %}

## Account
Available: ${{ "%.2f"|format(account.available) }}
{% if signal.ticker in positions.tickers %}
⚠️ Already holding {{ signal.ticker }}
{% endif %}

## Decision
{% if not time.is_market_open %}
SKIP: Market closed
{% elif vix.value > 30 %}
SKIP: VIX too high ({{ vix.value }})
{% elif signal.ticker in positions.tickers %}
SKIP: Position exists
{% else %}
ANALYZE for potential entry
{% endif %}
```

---

## Új Prefetch Hozzáadása

1. Fájl létrehozása: `domain/prefetches/my_prefetch.py`
2. Osztály:
```python
from domain.prefetches.base import Prefetch, PrefetchResult

class MyPrefetch(Prefetch):
    name = "my_data"
    key = "my"  # {{ my.field }} in templates
    description = "My custom data"

    def fetch(self, signal, context):
        return PrefetchResult.from_data({
            "field1": "value1",
            "field2": 123,
        })
```
3. Regisztrálás: `domain/prefetches/__init__.py` → `ALL_PREFETCHES` lista

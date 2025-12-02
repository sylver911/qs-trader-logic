- Az elkészült scraper trading logikáját kell most elkészíteni. 
  - A kód legyen szépen tagolt, pep8-at követve és domain driven design, az üzleti és architekturális réteg legyen leválasztva
  - A kódnak mindig futnia kell, a bejövő feladatokat Redis szerverről fogja majd kapni.
  - Minden konfig, IP stb. környezeti változóból fog jönni és fontos, hogy egy külön konfigfájl kezelje majd ezt.
  - Loggingra szükség van, legyen beleírva INFO és DEBUG is.
    - Az INFO üzeneteket a LOG_WEBHOOK_URL (ha meg van adva) discord webhook címre kell elküldeni
    - Az INFO tartalmazzon nagyobb léptékű dolgokat, pl.: beesik a feladat, kiértékelve, LLM gondolata, ACT

- Amint beesik Redis szerverről egy feladat, úgy a litellm szerver felé kell majd fordulni
- A litellm python sdk-t (https://docs.litellm.ai/docs/set_keys)  kell használnod
- Litellm proxyba fog majd bemenni a kérés, ami a LITELLM_URL környezeti változóból jön. Az API kulcsokat a proxyban fogom beállítani, neked azzal dolgod nincs. Csak egy master key lesz majd.

- Egy signal így fog kinézni:
```json
{
  "_id": "692dc7ab8b19c22400c25705",
  "forum_id": "1373531558274666496",
  "forum_name": "⏰live-0dte-signals",
  "thread_id": "144477652490S4534197",
  "thread_name": "SPY 2025-11-30",
  "created_at": "2025-11-30T19:46:06.187000+00:00",
  "message_count": 1,
  "messages": [
    {
      "content": "SPY QuantSignals V3 0DTE 2025-11-30\n**SPY 0DTE Signal | 2025-11-30**\n• Direction: BUY CALLS | Confidence: 65%\n• Expiry: 2025-12-01 (same-day)\n• Strike Focus: $683.00\n• Entry Range: $1.77\n• Target 1: $2.10\n• Stop Loss: $1.40\n• Gamma Risk: Low\n• Flow Intel: Neutral | PCR 0.83\n• Price vs VWAP: +0.16%\n• ⚠️ MODERATE RISK WARNING: Consider reducing position size due to moderate confidence level.\n⚖️ **Compliance**: Educational 0DTE commentary for QS Premium. Not financial advice.\n\n### 🎯 TRADE RECOMMENDATION\n**Direction**: BUY CALLS  \n**Confidence**: 65%  \n**Conviction Level**: MEDIUM  \n\n### 🧠 ANALYSIS SUMMARY\n**Katy AI Signal**: The AI prediction shows a neutral trend with 50% confidence, but the detailed time series reveals a predominantly sideways movement with occasional minor fluctuations. Prices oscillate between $681.18 and $683.54 throughout the session, indicating no strong directional bias.\n\n**Technical Analysis**: SPY trading at $683.54 (+0.27% session change) above VWAP of $682.46 (+0.16%), suggesting mild bullish momentum. Current price near session high ($683.96) with support at $673.72. Volume at 0.0x average indicates low participation, potentially reducing signal reliability.\n\n**News Sentiment**: OPEC reaffirming crude oil production levels through 2026 provides market stability. Political uncertainty from Trump's executive order comments creates minor background noise but no immediate market-moving impact. Overall neutral to slightly positive sentiment.\n\n**Options Flow**: Put/Call Ratio at 0.83 indicates neutral flow bias. Max pain at $669.00 (-2.1% from spot) creates slight upward pressure. Gamma risk level low, suggesting reduced volatility compression effects.\n\n**Risk Level**: MEDIUM - Low volume conditions and neutral Katy AI signal require cautious position sizing. 0DTE time decay accelerates significantly in afternoon session.\n\n### 💰 TRADE SETUP\n**Expiry Date**: 2025-12-01 (1 days)  \n**Recommended Strike**: $683.00  \n**Entry Price**: $1.75 - $1.78",
      "timestamp": "2025-11-30T20:46:06.187+01:00",
      "ai": null
    },
    {
      "content": "**Target 1**: $2.10 (20% gain from entry)  \n**Target 2**: $2.50 (40% gain from entry)  \n**Stop Loss**: $1.40 (20% loss from entry)  \n**Position Size**: 2% of portfolio  \n\n### ⚡ COMPETITIVE EDGE\n**Why This Trade**: This play leverages the mild bullish technical setup (price above VWAP) despite neutral Katy AI predictions, focusing on gamma ramp effects during power hour session.\n\n**Timing Advantage**: Entry during midday (11:00-13:30 ET) allows for VWAP reversion opportunities before afternoon gamma effects intensify.\n\n**Risk Mitigation**: Conservative strike selection with 0.55 delta provides intrinsic value protection against rapid time decay. Tight stop loss limits downside in low-volume conditions.\n\n### 🚨 IMPORTANT NOTES\n- ⚠️ Katy AI shows neutral trend with only 50% confidence - trade relies more on technical setup than AI prediction\n- ⚠️ Extremely low volume (0.0x average) reduces signal reliability - smaller position size recommended\n- ⚠️ 0DTE time decay accelerates significantly after 2:00 PM ET - consider exiting positions by 3:00 PM ET\n- ⚠️ Monitor VIX levels (currently 16.35) for any volatility spikes that could impact option pricing\n\n**CRITICAL OVERRIDE JUSTIFICATION**: While Katy AI shows neutral trend, the composite directional guidance (+1.8 STRONG bias) and technical setup (price above VWAP, session gain) provide sufficient evidence for a mild bullish bias. The conservative strike selection and tight risk parameters appropriately account for the neutral AI signal.\n\n📊 TRADE DETAILS 📊\n🎯 Instrument: SPY\n🔀 Direction: CALL (LONG)\n🎯 Strike: 683.00\n💵 Entry Price: 1.77\n🎯 Profit Target: 2.10\n🛑 Stop Loss: 1.40\n📅 Expiry: 2025-12-01\n📏 Size: 2.0\n📈 Confidence: 65%\n⏰ Entry Timing: N/A\n🕒 Signal Time: 2025-11-30 14:45:59 EST\n\n⚠️ MODERATE RISK WARNING: Consider reducing position size due to moderate confidence level.",
      "timestamp": "2025-11-30T20:46:07.042+01:00",
      "ai": null
    }
  ],
  "scraped": true,
  "scrape_ready": true,
  "collected_at": "2025-12-01T17:51:55.473789",
  "scraped_at": "2025-12-01T17:52:00.578218"
}
```
- A cél, hogy az AI elemezze ezt a signalt és utasításokat adjon és kereskedjen.
- Itt majd az `ai` kulcsot kell kitölteni. Fontos, hogy ott legyen az AI véleménye és legyen egy `act` kulcs, ami tartalmazza, hogy az ai mit csinált. pl.: skip vagy tett tradet
  - Az AI véleménye dinamikus, az AI-ból kitöltendő
  - Az `act` viszont kódilag lesz érdekes, ez az AI által használt toolokból derül ki algoritmikusan, hogy mit csinált.
- Az egész egy `jinja2` templatebe kell hogy beessen és ez fog elmenni a litellm részére. Ez azért lesz lényeges, mert ha később ezt szeretném módosítani VAGY beletenni a lentebb használt mezőkből, azt könnyedén meg tudjam tenni.

- Az AI használhat bizonyos toolokat, ezek a következők (itt is külön kell definiálni az architekturális rétegben, hogy aztán az üzletiben már csak simán hívni kelljen):
  - Le tudja kérdezni az aktuális kereskedési időt. (EST)
  - Le tudja kérdezni az aktuális aktuális ticker árfolyamát. (kezdetben yfinance segítségével, később IBindből élőben, most még nincs market data az Ibindben. ezt valahogy kezeld le)
  - Le tudja kérdezni a volume-t és a volatilitást
  - Le tudja kérdezni az opciós láncot
  - Az aktuális pozíciókat
  - Daily P&L
  - Aktuális VIX level
  - Aktuális napi trading history
- ACTION TOOLOK:
  - Order placement (execution)
  - Place bracket order (entry + profit target + stop loss)
  - Cancel order
  - Modify order
  - Close position
  - Adjust stop loss


- Az alábbi beállításokat kell validálnia a kódnak: ezekhez készíts gettert (nyilván fogsz, mert az archiktektúra le van választva az üzleti logikáról). Ezek Redisben fognak tárolódni, viszont ezek még nincs ott. Ezekre figyelned kell, hogy oda kerüljenek. És értelemszerűen hardcodeold ezeket a változókat ott, ahol kell
  - max_loss_per_trade_percent  - "Maximum portfolio risk per single trade" DEFAULT: 0.1
  - max_daily_trades - "Maximum number of trades per day" DEFAULT: 10
  - max_concurrent_positions - "Maximum open positions at once" DEFAULT: 5
  - max_loss_per_day_percent - "Stop trading if daily loss exceeds this" DEFAULT: 0.1
  - default_stop_loss_percent - "Default stop loss if not specified in signal" DEFAULT: 0.3
  - default_take_profit_percent - "Default take profit if not specified" DEFAULT: 0.5
  - trailing_stop_enabled - "Use trailing stop after profit threshold" DEFAULT: FALSE
  - trailing_stop_activation_percent - "Profit % to activate trailing stop" DEFAULT: 0.2
  - trailing_stop_distance_percent - "Distance from peak to trail" DEFAULT: 0.1
  - min_ai_confidence_score - "Minimum AI confidence to execute" DEFAULT: 0.5
  - blacklist_tickers - "Never trade these symbols" DEFAULT: ['GME', 'BYND']
  - whitelist_tickers - "Only trade these symbols (if not empty)" DEFAULT: ['SPY', 'QQQ']
  - max_position_size_percent - "Maximum % of portfolio in single position" DEFAULT: 0.2
  - emergency_stop - "Kill switch - stop all trading immediately" DEFAULT: false
  - max_vix_level - "Skip trading if VIX is over this value" DEFAULT: 25
  - current_llm_model - "Use this LLM model to validate signal" DEFAULT: deepseek/deepseek-reasoner

- A trading logikához az IBind klienst fogjuk használni Voyztól. Implementációs segédletként megkapod az API referenciát
- Az ibind kliens inicializálásának így kell majd kinéznie: (a környezeti változó adott csak a kontextus miatt adtam meg)
```dotenv
IBEAM_URL=http://ibeam-deploy.railway.internal:5000
IB_ACCOUNT_ID=DU8875169
```
```python
import os
from ibind import IbkrClient
IBEAM_URL = os.getenv('IBEAM_URL')
ACCOUNT_ID = os.getenv('IB_ACCOUNT_ID')
client = IbkrClient(url=f"{IBEAM_URL}/v1/api/", account_id=ACCOUNT_ID, cacert=False,  timeout=10 )  
accounts = client.portfolio_accounts() 
print(f"✅ Accounts: {accounts.data}")
```

Kérlek a fenti implementációt kódold le, csomagold be .zipbe és add ide.
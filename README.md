# Quant Clash Bot — RSI + MACD + News Sentiment

An algorithmic trading bot I built to compete in the **HFT Siege Trading Competition** — a simulated real-time market where multiple bots compete across 20 tickers, each starting with $100,000 in capital, in a 30-minute sprint.

**Result: 2nd place out of 4 competing strategies.**

This was a learning project. The goal was to understand how automated trading systems actually work — not just write code, but think through decision-making under uncertainty, risk management, and system reliability under pressure.

---

## What the Bot Does

The strategy combines three layers:

### 1. RSI (Relative Strength Index)
Detects when a stock is oversold or overbought.
- RSI < 30 → stock is beaten down, likely to bounce → **BUY signal**
- RSI > 70 → stock is overheated, likely to drop → **SELL signal**

### 2. MACD (Moving Average Convergence Divergence)
Confirms the RSI signal with trend momentum.
- MACD line crosses **above** signal line → trend turning bullish → reinforces BUY
- MACD line crosses **below** signal line → trend turning bearish → reinforces SELL

The bot only trades when **both RSI and MACD agree** — this filters out a lot of false signals.

### 3. News Sentiment
Reacts to incoming news events in real time.
- Sentiment score > 0.4 → buy the affected ticker(s)
- Sentiment score < -0.4 → sell out of current position
- Macro news (no specific ticker) → applies to all tracked stocks

---

## Project Structure

```
Quant-Clash-Bot-by-AY/
├── Quant_bot.py          # Main bot — strategy + SDK callbacks
├── hft_siege_client.py   # WebSocket client SDK (provided by competition)
├── requirements.txt      # Just websockets
└── README.md
```

---

## Setup & Running

### 1. Clone the repo

```bash
git clone https://github.com/AryanYadav215/Quant-Clash-Bot-by-AY.git
cd Quant-Clash-Bot-by-AY
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:
- **Windows:** `.venv\Scripts\activate`
- **Mac/Linux:** `source .venv/bin/activate`

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set your credentials and run

Never hardcode credentials. Use environment variables:

**Windows (PowerShell):**
```powershell
$env:WS_URL="ws://SERVER_IP:8081/ws"
$env:USERNAME="your_team_name"
$env:PASSWORD="your_password"
python Quant_bot.py
```

**Mac/Linux:**
```bash
WS_URL="ws://SERVER_IP:8081/ws" USERNAME="your_team_name" PASSWORD="your_password" python Quant_bot.py
```

---

## Key Parameters (Tunable)

| Parameter | Default | What it controls |
|---|---|---|
| `ORDER_SIZE` | 5 shares | How many shares per trade |
| `MAX_POSITION` | 50 shares | Max exposure per ticker |
| `RSI_PERIOD` | 14 | Lookback window for RSI |
| `RSI_OVERSOLD` | 30 | RSI threshold to trigger BUY |
| `RSI_OVERBOUGHT` | 70 | RSI threshold to trigger SELL |
| `MACD_FAST` | 12 | Fast EMA period |
| `MACD_SLOW` | 26 | Slow EMA period |
| `MACD_SIGNAL` | 9 | Signal line smoothing period |
| `NEWS_BUY_THRESHOLD` | 0.4 | Min sentiment score to buy on news |
| `NEWS_SELL_THRESHOLD` | -0.4 | Max sentiment score to sell on news |

---

## What I Learned

The obvious lesson was "build good signals." The less obvious lesson was that **risk management and system design matter more than signal quality** in a constrained environment.

Some things that would've made the bot stronger:

- **Wider market coverage** — only tracked 5 of 20 available tickers, which meant missing 75% of opportunities
- **Stop-loss logic** — the bot relies on indicator reversals to exit, which can mean holding through drawdowns
- **Dynamic position sizing** — fixed ORDER_SIZE of 5 doesn't account for price differences between stocks
- **Faster warmup** — needs 35 price ticks before trading, which delays entry by a few minutes at round start
- **Advanced risk controls** — no portfolio-level circuit breaker; adding one (e.g., halt trading if net worth drops >10%) would protect against bad streaks

---

## Competition Context

- **Event:** HFT Siege Trading Competition
- **Format:** 30-minute simulated market, 20 tickers, $100K starting capital per bot
- **Participants:** 4 bots with different strategies (momentum, OFI, grid trading, RSI+MACD)
- **Evaluation:** Ranked by final net worth at round end

---

## Disclaimer

This is a student learning project built for a simulated competition. It is **not** financial advice and should not be used for real trading.

---

*Built with Python + websockets. Feedback and forks welcome.*
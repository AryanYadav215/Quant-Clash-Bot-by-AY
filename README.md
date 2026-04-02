# HFT Siege Bot — RSI + MACD
This is an automated trading bot for the HFT Siege competition.

## Strategy
- **RSI:** Buys when oversold (<30), Sells when overbought (>70).
- **MACD:** Uses signal line crossovers for trend confirmation.
- **News:** Integrated sentiment analysis for rapid news-based execution.

## Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Run the bot: `python Quant_bot.py`

## How to run
1. ## 🚀 Quick Start
To run the bot securely without hardcoding your credentials:

```powershell
$env:WS_URL="ws://SERVER_IP:8081/ws"
$env:USERNAME="your_team_name"
$env:PASSWORD="your_password"
.\.venv\Scripts\python.exe Quant_bot.py
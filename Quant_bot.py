"""
HFT Siege Bot — RSI + MACD + News Strategy
Built on top of the official hft_siege_client SDK.

Install:
    pip install websockets
    cd sdk/python && pip install -e .

Run:
    python quant_bot.py

Or with env variables:
    WS_URL=ws://SERVER_IP:8081/ws USERNAME=yourteam PASSWORD=yourpass python quant_bot.py
"""

import asyncio
import collections
import logging
import os
import websockets

from hft_siege_client import (
    ClientConfig,
    HFTSiegeClient,
    LeaderboardEntry,
    NewsEvent,
    OrderResponse,
    PriceTick,
    RoundStatus,
    Trade,
    WalletUpdate,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("quant_bot")

# ============================================================
#  CHANGE THESE — or set as environment variables at venue
# ============================================================
WS_URL   = os.getenv("WS_URL",    "ws://10.220.147.182:8081/ws")
USERNAME = os.getenv("USERNAME",  "aryan")
PASSWORD = os.getenv("PASSWORD",  "arya_1234asdf")
# ============================================================

# ---- TUNING KNOBS (tweak between rounds) -------------------
ORDER_SIZE          = int(os.getenv("ORDER_SIZE", "5"))
MAX_POSITION        = 50      # max shares to hold per stock

# RSI
RSI_PERIOD          = 14      # number of prices to calculate RSI
RSI_OVERSOLD        = 30      # below this → BUY signal
RSI_OVERBOUGHT      = 70      # above this → SELL signal

# MACD
MACD_FAST           = 12
MACD_SLOW           = 26
MACD_SIGNAL         = 9

# News
NEWS_BUY_THRESHOLD  = 0.4     # sentiment above this → buy
NEWS_SELL_THRESHOLD = -0.4    # sentiment below this → sell

# Minimum prices needed before trading
MIN_PRICES_NEEDED   = MACD_SLOW + MACD_SIGNAL   # = 35
# ------------------------------------------------------------

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]


# ============================================================
#  INDICATOR FUNCTIONS
# ============================================================

def calculate_rsi(prices: list, period: int = 14):
    """
    RSI 0-100.
    < RSI_OVERSOLD  → stock beaten down → likely to bounce → BUY
    > RSI_OVERBOUGHT → stock overheated → likely to drop  → SELL
    """
    if len(prices) < period + 1:
        return None

    gains, losses = [], []
    for i in range(1, period + 1):
        change = prices[-period - 1 + i] - prices[-period - 2 + i]
        if change > 0:
            gains.append(change); losses.append(0)
        else:
            gains.append(0); losses.append(abs(change))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100

    rs  = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_ema(prices: list, period: int):
    """Exponential Moving Average — weights recent prices more."""
    if len(prices) < period:
        return None

    ema = sum(prices[:period]) / period
    multiplier = 2 / (period + 1)
    for price in prices[period:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))
    return ema


def calculate_macd(prices: list):
    """
    Returns (macd_line, signal_line) or (None, None).
    BUY  when macd_line crosses ABOVE signal_line
    SELL when macd_line crosses BELOW signal_line
    """
    if len(prices) < MACD_SLOW + MACD_SIGNAL:
        return None, None

    # Build MACD values over last MACD_SIGNAL+1 points
    macd_values = []
    for i in range(MACD_SIGNAL + 1):
        subset = prices[:len(prices) - MACD_SIGNAL + i] if i < MACD_SIGNAL else prices
        fast = calculate_ema(subset, MACD_FAST)
        slow = calculate_ema(subset, MACD_SLOW)
        if fast is None or slow is None:
            return None, None
        macd_values.append(fast - slow)

    macd_line   = macd_values[-1]
    signal_line = calculate_ema(macd_values, MACD_SIGNAL)
    return macd_line, signal_line


# ============================================================
#  PER-STOCK STATE
# ============================================================

class StockState:
    def __init__(self, ticker: str):
        self.ticker        = ticker
        self.prices        = collections.deque(maxlen=100)
        self.prev_macd     = None
        self.prev_signal   = None

    def add_price(self, p: int):
        self.prices.append(p)

    def latest(self):
        return self.prices[-1] if self.prices else None

    def ready(self):
        return len(self.prices) >= MIN_PRICES_NEEDED

    def price_list(self):
        return list(self.prices)


# ============================================================
#  BOT STATE
# ============================================================

stocks       = {t: StockState(t) for t in TICKERS}
positions    = collections.defaultdict(int)   # shares owned per ticker
cash         = 0                              # cents — updated by server
round_active = False

# ============================================================
#  CLIENT SETUP
# ============================================================

cfg = ClientConfig(
    url      = WS_URL,
    username = USERNAME,
    password = PASSWORD,
    reconnect= True,    # zombie loop built into SDK
)
client = HFTSiegeClient(cfg)


# ============================================================
#  HELPERS
# ============================================================

async def do_buy(ticker: str, price: int, qty: int, reason: str):
    """Safety-checked buy with optimistic cash updates."""
    global cash  # 🚨 Added to allow local deduction

    if price <= 0:
        return

    # Never spend more than 30% of cash at once
    max_by_cash = int(cash * 0.30 / price) if price > 0 else 0
    qty = min(qty, max_by_cash)

    # Respect MAX_POSITION
    qty = min(qty, MAX_POSITION - positions[ticker])

    if qty <= 0:
        return

    # 🚨 Optimistic update: deduct locally instantly
    cash -= (price * qty)
    positions[ticker] += qty

    logger.info("BUY  %s x%d @ $%.2f  [%s]", ticker, qty, price / 100, reason)
    await client.submit_limit_order(ticker, "BUY", price, qty)


async def do_sell(ticker: str, price: int, qty: int, reason: str):
    """Safety-checked sell with optimistic cash updates."""
    global cash  # 🚨 Added to allow local addition

    if price <= 0:
        return

    qty = min(qty, positions[ticker])  # can't sell what we don't own
    if qty <= 0:
        return

    # 🚨 Optimistic update: add locally instantly
    cash += (price * qty)
    positions[ticker] -= qty

    logger.info("SELL %s x%d @ $%.2f  [%s]", ticker, qty, price / 100, reason)
    await client.submit_limit_order(ticker, "SELL", price, qty)

# ============================================================
#  CORE STRATEGY: RSI + MACD
# ============================================================

async def evaluate_rsi_macd(ticker: str, price: int):
    state  = stocks[ticker]
    prices = state.price_list()

    # --- RSI ---
    rsi = calculate_rsi(prices, RSI_PERIOD)
    if rsi is None:
        return

    # --- MACD ---
    macd_line, signal_line = calculate_macd(prices)
    if macd_line is None or signal_line is None:
        return

    # --- Crossover detection ---
    macd_crossed_up   = (state.prev_macd is not None and
                         state.prev_macd   < state.prev_signal and
                         macd_line         > signal_line)

    macd_crossed_down = (state.prev_macd is not None and
                         state.prev_macd   > state.prev_signal and
                         macd_line         < signal_line)

    state.prev_macd   = macd_line
    state.prev_signal = signal_line

    logger.debug("%s RSI=%.1f MACD=%.2f Signal=%.2f", ticker, rsi, macd_line, signal_line)

    # --- BUY: both RSI oversold + MACD crossed up ---
    if rsi < RSI_OVERSOLD and macd_crossed_up:
        logger.info("[STRONG BUY] %s RSI=%.1f + MACD crossed UP", ticker, rsi)
        await do_buy(ticker, price, ORDER_SIZE,
                     reason=f"RSI={rsi:.1f}<{RSI_OVERSOLD} + MACD cross UP")

    # --- SELL: both RSI overbought + MACD crossed down ---
    elif rsi > RSI_OVERBOUGHT and macd_crossed_down:
        logger.info("[STRONG SELL] %s RSI=%.1f + MACD crossed DOWN", ticker, rsi)
        await do_sell(ticker, price, ORDER_SIZE,
                      reason=f"RSI={rsi:.1f}>{RSI_OVERBOUGHT} + MACD cross DOWN")


# ============================================================
#  SDK CALLBACKS
# ============================================================

@client.on_connected
async def handle_connected():
    logger.info("Connected to HFT Siege as %s", USERNAME)


@client.on_disconnected
async def handle_disconnected():
    logger.warning("Disconnected — SDK will auto-reconnect...")


@client.on_round_status
async def handle_round_status(status: RoundStatus):
    global round_active
    was_active  = round_active
    round_active = status.state == "Active"

    if round_active and not was_active:
        logger.info("ROUND ACTIVE — trading enabled! (%ds remaining)", status.remaining_seconds)
    elif not round_active and was_active:
        logger.info("Round paused/ended (state=%s)", status.state)


@client.on_wallet_update
async def handle_wallet(update: WalletUpdate):
    global cash
    cash = update.cash
    for ticker, qty in update.positions.items():
        positions[ticker] = qty
    logger.info("WALLET  cash=$%.2f  net_worth=$%.2f",
                cash / 100, update.net_worth / 100)


@client.on_price_update
async def handle_price(tick: PriceTick):
    if not round_active:
        return

    ticker = tick.ticker
    price  = tick.price

    if ticker not in stocks:
        return

    state = stocks[ticker]
    state.add_price(price)

    if not state.ready():
        remaining = MIN_PRICES_NEEDED - len(state.prices)
        logger.debug("%s warming up — %d more prices needed", ticker, remaining)
        return

    await evaluate_rsi_macd(ticker, price)


@client.on_news
async def handle_news(event: NewsEvent):
    if not round_active:
        return

    score    = event.sentiment_score
    headline = getattr(event, "headline", "")
    ticker   = event.ticker   # None = macro news (affects all stocks)

    logger.info("NEWS [%s] score=%.2f  %s",
                ticker or "MACRO", score, headline)

    targets = [ticker] if ticker else TICKERS

    for t in targets:
        if t not in stocks:
            continue
        price = stocks[t].latest()
        if not price:
            continue

        if score >= NEWS_BUY_THRESHOLD:
            await do_buy(t, price, ORDER_SIZE,
                         reason=f"news sentiment={score:.2f}")

        elif score <= NEWS_SELL_THRESHOLD and positions[t] > 0:
            await do_sell(t, price, positions[t],
                          reason=f"news sentiment={score:.2f}")


@client.on_order_response
async def handle_order_response(resp: OrderResponse):
    if resp.success:
        logger.info("Order %d accepted", resp.order_id)
    else:
        logger.warning("Order REJECTED: %s", resp.message)


@client.on_trade
async def handle_trade(trade: Trade):
    logger.info("TRADE FILLED  %s x%d @ $%.2f",
                trade.ticker, trade.quantity, trade.price / 100)


@client.on_leaderboard
async def handle_leaderboard(entries: list):
    me = next((e for e in entries if e.participant_id == USERNAME), None)
    if me:
        logger.info("LEADERBOARD  rank=#%d  net_worth=$%.2f",
                    me.rank, me.net_worth_dollars)
    # Print top 5
    for e in entries[:5]:
        logger.info("  #%d  %s  $%.2f", e.rank, e.participant_id, e.net_worth_dollars)


@client.on_round_end
async def handle_round_end(payload: dict):
    logger.info("ROUND ENDED!")
    for entry in payload.get("leaderboard", [])[:5]:
        logger.info("  %s: $%.2f",
                    entry.get("participant_id", "?"),
                    entry.get("net_worth", 0) / 100)


@client.on_fraud_alert
async def handle_fraud_alert(payload: dict):
    logger.warning("FRAUD ALERT — frozen 60s. %s", payload)


@client.on_error
async def handle_error(message: str):
    logger.error("Server error: %s", message)


# ============================================================
#  MAIN
# ============================================================

# ============================================================
#  MAIN
# ============================================================

async def safe_run():
    while True:
        try:
            await client.connect()
        except websockets.exceptions.InvalidStatus as e:
            if "HTTP 429" in str(e):
                logger.error("HTTP 429 Rate Limit Hit. Sleeping for 60 seconds before retrying...")
                await asyncio.sleep(60)
            else:
                logger.error("WebSocket rejected connection: %s. Retrying in 10s...", e)
                await asyncio.sleep(10)
        except Exception as e:
            logger.error("Client crashed: %s. Retrying in 10s...", e)
            await asyncio.sleep(10)


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("HFT SIEGE BOT — RSI + MACD + NEWS")
    logger.info("URL=%s  USER=%s", WS_URL, USERNAME)
    logger.info("RSI period=%d  oversold<%d  overbought>%d", RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT)
    logger.info("MACD fast=%d slow=%d signal=%d", MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    logger.info("=" * 50)

    try:
        asyncio.run(safe_run())
    except KeyboardInterrupt:
        logger.info("\n[STOPPED] Bot shut down manually.")
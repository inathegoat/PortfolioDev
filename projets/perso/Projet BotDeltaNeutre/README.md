# Delta-Neutral Funding Arbitrage Bot

**Automated delta-neutral arbitrage bot capturing funding rates on Hyperliquid DEX.**

Monitors funding rates across 90+ perpetual swap pairs and automatically opens delta-neutral positions when rates exceed configurable thresholds, collecting funding payments while hedging price risk with a spot position.

> Free to test, improve, or adapt.

---

## Features

- **Automated funding monitoring** — scans 20+ active pairs every ~20 seconds
- **Delta-neutral strategy** — perp + spot hedge to neutralise directional risk
- **Intelligent signal detection** — anomaly detection via Z-score and configurable thresholds
- **Risk management** — max drawdown, circuit breaker, concentration limits
- **Telegram dashboard** — real-time alerts + `/status`, `/start`, `/stop` commands
- **Internal wallet tracking** — PnL tracking and funding history
- **French localisation** — full French language support

---

## Architecture

```
├── main.py                    # Entry point
├── config.example.json        # Configuration template
├── modules/
│   ├── hyperliquid_api.py     # Hyperliquid SDK wrapper (perps + spot)
│   ├── execution_engine.py    # Order execution (perp + hedge spot)
│   ├── funding_analyzer.py    # Funding rate analysis + signals
│   ├── position_manager.py    # Position state management
│   ├── risk_manager.py        # Risk controls + circuit breaker
│   └── telegram_bot.py        # Telegram bot interface
├── strategies/
│   └── delta_neutral.py       # Core strategy logic
├── wallet/
│   └── wallet_manager.py      # Capital and PnL tracking
├── core/
│   ├── config.py              # Config loading
│   └── logger.py              # CSV trade/funding logging
└── localization/
    └── translator.py          # i18n support
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/inathegoat/delta-neutral-bot.git
cd delta-neutral-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.example.json config.json
```

Edit `config.json` with your credentials:

| Field | Description |
|-------|-------------|
| `hyperliquid.private_key` | Your EVM private key (`0x...`) |
| `hyperliquid.account` | Your EVM address (`0x...`) |
| `telegram.token` | Telegram bot token from @BotFather |
| `telegram.admin_chat_ids` | Your Telegram user ID |

### 3. Fund the account

1. Deposit USDC on [app.hyperliquid.xyz](https://app.hyperliquid.xyz)
2. Make sure funds are in the **Perps** trading account (not Spot or HyperEVM)

### 4. Run the bot

```bash
python main.py
```

---

## How It Works

### Delta-Neutral Strategy

1. **Monitor** funding rates on all enabled pairs
2. **Detect** anomalies when `|funding_rate| > threshold` (default: `0.003%/h`)
3. **Open** a delta-neutral position:
   - **Positive funding** → SHORT perp + BUY spot (shorts receive funding)
   - **Negative funding** → LONG perp + SELL spot (longs receive funding)
4. **Collect** funding payments every hour
5. **Close** the position when funding drops below the profitability threshold

### Capital Allocation

Capital is split 50/50 between perp margin and spot hedge to maintain delta neutrality.

### Example

```
Signal: HYPE funding = -0.0048%/h (42% annualised)
→ LONG 0.51 HYPE perp @ $26.95
→ BUY 0.51 HYPE spot @ $26.95 (hedge)
→ Collecting ~$0.006/h in funding
→ Price-neutral: gains/losses offset between perp and spot
```

---

## Configuration

### Strategy Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `funding_threshold` | `3e-05` | Minimum funding rate to trigger (0.003%/h) |
| `funding_ma_period` | `3` | Moving average period for signal |
| `funding_zscore_k` | `1.0` | Z-score multiplier for anomaly detection |
| `capital_per_pair_pct` | `1.0` | % of capital allocated per trade |
| `min_trade_size_usdt` | `5.0` | Minimum order size |
| `slippage_pct` | `0.001` | Maximum slippage tolerance |

### Risk Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_drawdown_pct` | `0.10` | Maximum portfolio drawdown (10%) |
| `max_daily_loss_pct` | `0.03` | Maximum daily loss (3%) |
| `circuit_breaker_enabled` | `true` | Auto-stop on significant losses |

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the strategy |
| `/stop` | Stop the strategy |
| `/status` | View current positions and PnL |
| `/dashboard` | Open interactive dashboard |

---

## Disclaimer

This bot is provided for educational purposes. Perpetual contract trading carries significant risk. Use at your own risk. Never invest funds you cannot afford to lose.

---

## License

InaCorporation — By InaTheGoat

# 🤖 Delta Neutral Funding Bot

Automated delta-neutral funding rate arbitrage bot for **Hyperliquid DEX**.

Monitors perpetual futures funding rates across 90+ pairs and automatically opens delta-neutral positions when funding rates are anomalously high — collecting funding payments while hedging price risk with spot positions.

## ✨ Features

- **Automated Funding Rate Monitoring** — Scans 20+ enabled pairs every ~20s
- **Delta-Neutral Strategy** — Perp + spot hedge to eliminate directional risk
- **Smart Signal Detection** — Z-score based anomaly detection with configurable thresholds
- **Risk Management** — Max drawdown, circuit breaker, concentration limits
- **Telegram Dashboard** — Real-time alerts, /status, /start, /stop commands
- **Internal Wallet Tracking** — PnL tracking, funding collection history
- **French Localization** — Full French language support

## 🏗️ Architecture

```
├── main.py                    # Entry point
├── config.example.json        # Configuration template
├── modules/
│   ├── hyperliquid_api.py     # Hyperliquid SDK wrapper (perps + spot)
│   ├── execution_engine.py    # Order execution (perp + spot hedge)
│   ├── funding_analyzer.py    # Funding rate analysis & signals
│   ├── position_manager.py    # Position state management
│   ├── risk_manager.py        # Risk checks & circuit breakers
│   └── telegram_bot.py        # Telegram bot interface
├── strategies/
│   └── delta_neutral.py       # Main strategy logic
├── wallet/
│   └── wallet_manager.py      # Capital & PnL tracking
├── core/
│   ├── config.py              # Config loader
│   └── logger.py              # CSV trade/funding logging
└── localization/
    └── translator.py          # i18n support
```

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/delta-neutral-bot.git
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
|---|---|
| `hyperliquid.private_key` | Your EVM private key (`0x...`) |
| `hyperliquid.account` | Your EVM address (`0x...`) |
| `telegram.token` | Telegram bot token from @BotFather |
| `telegram.admin_chat_ids` | Your Telegram user ID |

### 3. Fund Your Account

1. Deposit USDC on [app.hyperliquid.xyz](https://app.hyperliquid.xyz)
2. Make sure funds are in the **Perps** trading account (not Spot or HyperEVM)

### 4. Run

```bash
python main.py
```

## 📊 How It Works

### Delta-Neutral Strategy

1. **Monitor** funding rates across all enabled pairs
2. **Detect** anomalies when `|funding_rate| > threshold` (default: 0.003%/h)
3. **Open** a delta-neutral position:
   - **Positive funding** → SHORT perp + BUY spot (shorts receive funding)
   - **Negative funding** → LONG perp + SELL spot (longs receive funding)
4. **Collect** funding payments every hour
5. **Close** when funding rate drops below profitability threshold

### Capital Split

Capital is split 50/50 between perp margin and spot hedge to maintain delta neutrality.

### Example

```
Signal: HYPE funding = -0.0048%/h (42% annualized)
→ LONG 0.51 HYPE perp @ $26.95
→ BUY 0.51 HYPE spot @ $26.95 (hedge)
→ Collect ~$0.006/h in funding
→ Price-neutral: gains/losses cancel between perp and spot
```

## ⚙️ Configuration

### Strategy Parameters

| Parameter | Default | Description |
|---|---|---|
| `funding_threshold` | `3e-05` | Min funding rate to trigger (0.003%/h) |
| `funding_ma_period` | `3` | Moving average period for signal |
| `funding_zscore_k` | `1.0` | Z-score multiplier for anomaly detection |
| `capital_per_pair_pct` | `1.0` | % of capital per trade |
| `min_trade_size_usdt` | `5.0` | Minimum order size |
| `slippage_pct` | `0.001` | Max slippage tolerance |

### Risk Parameters

| Parameter | Default | Description |
|---|---|---|
| `max_drawdown_pct` | `0.10` | Max portfolio drawdown (10%) |
| `max_daily_loss_pct` | `0.03` | Max daily loss (3%) |
| `circuit_breaker_enabled` | `true` | Auto-stop on large losses |

## 📱 Telegram Commands

| Command | Description |
|---|---|
| `/start` | Start the strategy |
| `/stop` | Stop the strategy |
| `/status` | Show current positions & PnL |
| `/dashboard` | Interactive dashboard with buttons |

## ⚠️ Disclaimer

This bot is for educational purposes. Trading perpetual futures involves significant risk. Use at your own risk. Never trade with funds you can't afford to lose.

## 📄 License

MIT

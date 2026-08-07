# Delta-Neutral Funding Bot

Educational Python prototype for analysing perpetual-futures funding rates and modelling a delta-neutral trading workflow on Hyperliquid.

> This repository is an experimental software project, not financial advice. The checked-in configuration is disabled and testnet-only. Never commit credentials or run an unfamiliar trading system with real funds.

## What the project demonstrates

- asynchronous market-data and exchange interfaces;
- funding-rate monitoring and signal analysis;
- position and wallet state management;
- risk limits, drawdown checks and circuit breakers;
- Telegram status and alert interfaces;
- historical backtesting scaffolding;
- modular Python project structure.

## Architecture

```text
Projet BotDeltaNeutre/
├── main.py
├── config.example.json
├── modules/
│   ├── hyperliquid_api.py
│   ├── execution_engine.py
│   ├── funding_analyzer.py
│   ├── position_manager.py
│   ├── risk_manager.py
│   └── telegram_bot.py
├── strategies/delta_neutral.py
├── backtesting/backtest.py
├── wallet/wallet_manager.py
├── core/
└── localization/
```

## Strategy model

The intended market-neutral structure pairs a perpetual position with a spot hedge. The sign of the funding rate determines which side of the perpetual contract is considered for the strategy. A production-quality implementation must also account for:

- the two legs independently;
- funding received or paid;
- trading fees and slippage;
- hedge drift and rebalancing;
- margin and liquidation risk;
- partial fills and exchange/API failures;
- negative funding and unavailable spot markets.

The current backtesting code is a prototype and should not be interpreted as proof of profitability or neutrality until those assumptions are explicitly modelled and tested.

## Safe local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
```

The checked-in example has:

- `testnet: true`;
- `strategy.active: false`;
- empty credentials.

Keep all local credentials in the ignored `config.json`. Review the code before enabling any live functionality. Do not place private keys in commits, issues, screenshots or notebooks.

## Risk controls

The prototype includes configuration and code for:

- maximum drawdown;
- maximum daily loss;
- leverage limits;
- concentration limits;
- liquidation-margin buffer;
- circuit-breaker state;
- logging and position tracking.

These controls are not a guarantee of safety. They need dedicated tests and failure-mode simulations before any operational use.

## Development priorities

- add unit tests for signal direction, fees, sizing and hedge ratios;
- model both perpetual and spot legs in the backtester;
- add negative-funding scenarios;
- add partial-fill and API-failure simulations;
- use walk-forward and out-of-sample evaluation;
- report costs, drawdown and uncertainty rather than only returns;
- replace any remaining credential-in-config workflow with environment-based secret loading.

## Licence

This code is shared for educational and research purposes. Review the repository licence and applicable exchange terms before reuse.

from __future__ import annotations
"""
backtesting/backtest.py - Historical funding simulation.
Loads CSV or fetches historical funding data and simulates the strategy.
"""

import csv
import json
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    timestamp: datetime
    pair: str
    action: str        # OPEN / CLOSE
    price: float
    size: float
    funding_at_entry: float
    pnl: float = 0.0
    fees: float = 0.0
    funding_collected: float = 0.0
    days_held: float = 0.0


@dataclass
class BacktestResult:
    pair: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_pnl: float
    total_funding: float
    total_fees: float
    num_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    annualized_return: float
    trades: list = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "pair": self.pair,
            "period": f"{self.start_date} → {self.end_date}",
            "initial_capital": f"${self.initial_capital:,.2f}",
            "final_capital": f"${self.final_capital:,.2f}",
            "total_pnl": f"${self.total_pnl:,.4f}",
            "total_funding": f"${self.total_funding:,.4f}",
            "total_fees": f"${self.total_fees:,.4f}",
            "net_pnl": f"${self.total_pnl - self.total_fees:,.4f}",
            "num_trades": self.num_trades,
            "win_rate": f"{self.win_rate*100:.1f}%",
            "max_drawdown": f"{self.max_drawdown*100:.2f}%",
            "sharpe_ratio": f"{self.sharpe_ratio:.3f}",
            "annualized_return": f"{self.annualized_return*100:.2f}%",
        }


class Backtester:
    """
    Simulates delta-neutral funding strategy on historical data.

    Expected CSV format:
    timestamp,pair,funding_rate,price,volume,open_interest
    """

    def __init__(self, config: dict):
        self._cfg = config
        self._output_dir = Path(config.get("output_dir", "data/backtest"))
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def load_csv(self, path: str) -> list[dict]:
        rows = []
        with open(path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["timestamp"] = datetime.fromisoformat(row["timestamp"])
                row["funding_rate"] = float(row["funding_rate"])
                row["price"] = float(row["price"])
                rows.append(row)
        return sorted(rows, key=lambda r: r["timestamp"])

    def run(self, data: list[dict], pair: str,
            initial_capital: float = 10000.0,
            leverage: float = 2.0,
            funding_threshold: float = 0.0003,
            ma_period: int = 24,
            zscore_k: float = 1.5,
            taker_fee: float = 0.0006,
            slippage: float = 0.001) -> BacktestResult:

        capital = initial_capital
        peak = capital
        max_dd = 0.0
        trades = []
        in_position = False
        entry_price = 0.0
        entry_funding = 0.0
        entry_time: Optional[datetime] = None
        position_size = 0.0
        funding_history: list[float] = []
        equity_curve: list[float] = [capital]
        funding_collected = 0.0
        total_fees = 0.0
        wins = 0

        for row in data:
            rate = row["funding_rate"]
            price = row["price"]
            ts = row["timestamp"]
            funding_history.append(rate)

            if len(funding_history) < ma_period:
                continue

            window = funding_history[-ma_period:]
            ma = statistics.mean(window)
            std = statistics.stdev(window) if len(window) > 1 else 0.0

            if not in_position:
                # Entry signal
                threshold = ma + zscore_k * std
                if rate > threshold and rate > funding_threshold:
                    spot_cap = capital / 2
                    position_size = spot_cap / price
                    fee = position_size * price * (taker_fee + slippage) * 2
                    capital -= fee
                    total_fees += fee
                    in_position = True
                    entry_price = price
                    entry_funding = rate
                    entry_time = ts
                    trades.append(BacktestTrade(ts, pair, "OPEN",
                                                price, position_size, rate, fees=fee))

            else:
                # Collect funding every 8h interval
                funding_usd = position_size * price * rate
                funding_collected += funding_usd
                capital += funding_usd

                # Exit signal: funding falls below MA
                if rate < ma or rate < funding_threshold / 2:
                    # Close position
                    close_pnl = position_size * (price - entry_price)
                    fee = position_size * price * (taker_fee + slippage) * 2
                    capital += close_pnl - fee
                    total_fees += fee
                    days_held = (ts - entry_time).total_seconds() / 86400
                    net = close_pnl - fee
                    if net > 0:
                        wins += 1
                    trades.append(BacktestTrade(
                        ts, pair, "CLOSE", price, position_size, rate,
                        pnl=close_pnl, fees=fee,
                        funding_collected=funding_collected,
                        days_held=days_held
                    ))
                    in_position = False
                    funding_collected = 0.0

            equity_curve.append(capital)
            if capital > peak:
                peak = capital
            dd = (peak - capital) / peak
            if dd > max_dd:
                max_dd = dd

        # Close any open position at end
        if in_position and data:
            last_price = data[-1]["price"]
            close_pnl = position_size * (last_price - entry_price)
            fee = position_size * last_price * (taker_fee + slippage) * 2
            capital += close_pnl - fee + funding_collected
            total_fees += fee

        total_pnl = capital - initial_capital
        num_trades = len([t for t in trades if t.action == "CLOSE"])
        win_rate = wins / max(num_trades, 1)

        # Sharpe ratio (using daily equity returns)
        daily_returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] > 0:
                daily_returns.append(
                    (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                )

        if len(daily_returns) > 1 and statistics.stdev(daily_returns) > 0:
            sharpe = (statistics.mean(daily_returns) /
                      statistics.stdev(daily_returns)) * (365 ** 0.5)
        else:
            sharpe = 0.0

        days_total = max((data[-1]["timestamp"] - data[0]["timestamp"]).days, 1)
        ann_return = ((capital / initial_capital) ** (365 / days_total)) - 1

        start_str = data[0]["timestamp"].strftime("%Y-%m-%d") if data else ""
        end_str = data[-1]["timestamp"].strftime("%Y-%m-%d") if data else ""

        return BacktestResult(
            pair=pair,
            start_date=start_str,
            end_date=end_str,
            initial_capital=initial_capital,
            final_capital=capital,
            total_pnl=total_pnl,
            total_funding=sum(t.funding_collected for t in trades),
            total_fees=total_fees,
            num_trades=num_trades,
            win_rate=win_rate,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            annualized_return=ann_return,
            trades=trades,
        )

    def export_results(self, result: BacktestResult):
        """Export trades and summary to CSV + JSON."""
        prefix = f"{result.pair}_{result.start_date}_{result.end_date}"

        # Summary JSON
        with open(self._output_dir / f"{prefix}_summary.json", "w") as f:
            json.dump(result.summary(), f, indent=2)

        # Trades CSV
        with open(self._output_dir / f"{prefix}_trades.csv", "w", newline="") as f:
            fields = ["timestamp", "pair", "action", "price", "size",
                      "funding_at_entry", "pnl", "fees",
                      "funding_collected", "days_held"]
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for t in result.trades:
                writer.writerow({
                    "timestamp": t.timestamp.isoformat(),
                    "pair": t.pair,
                    "action": t.action,
                    "price": round(t.price, 4),
                    "size": round(t.size, 6),
                    "funding_at_entry": round(t.funding_at_entry, 8),
                    "pnl": round(t.pnl, 4),
                    "fees": round(t.fees, 6),
                    "funding_collected": round(t.funding_collected, 4),
                    "days_held": round(t.days_held, 2),
                })

        logger.info(f"Backtest results exported to {self._output_dir}/{prefix}_*")

    def print_report(self, result: BacktestResult):
        s = result.summary()
        print("\n" + "="*50)
        print(f"  BACKTEST REPORT — {s['pair']}")
        print("="*50)
        for k, v in s.items():
            print(f"  {k:<25} {v}")
        print("="*50 + "\n")

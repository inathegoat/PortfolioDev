from pathlib import Path

import pandas as pd


# File locations
PROJECT_ROOT = Path(__file__).resolve().parents[1] # Path to the root of the project
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "btc_data.csv"
PROCESSED_FILE = PROJECT_ROOT / "data" / "processed" / "btc_features.csv"


# The first row is the column header; rows 2 and 3 contain ticker metadata.
btc = pd.read_csv(RAW_FILE, skiprows=[1, 2])
btc = btc.rename(columns={"Price": "Date"})

# Convert the date and market columns to the appropriate types.
btc["Date"] = pd.to_datetime(btc["Date"])
for column in ["Open", "High", "Low", "Close", "Volume"]:
    btc[column] = pd.to_numeric(btc[column], errors="raise")

btc = btc.sort_values("Date").reset_index(drop=True)

# Daily returns are expressed as percentages in this dataset.
daily_return = btc["Close"].pct_change() * 100
five_day_return = btc["Close"].pct_change(5) * 100
twenty_day_return = btc["Close"].pct_change(20) * 100

# Volatility is calculated from daily returns, not raw prices.
five_day_volatility = daily_return.rolling(window=5).std()
twenty_day_volatility = daily_return.rolling(window=20).std()
sixty_day_volatility = daily_return.rolling(window=60).std()

# Downside deviation: negative returns contribute their squared magnitude;
# positive returns contribute zero.
negative_returns = daily_return.clip(upper=0)
downside_volatility = negative_returns.pow(2).rolling(window=20).mean().pow(0.5)

# Moving averages and market-condition variables.
sixty_day_moving_average = btc["Close"].rolling(window=60).mean()
twenty_day_moving_average = btc["Close"].rolling(window=20).mean()
distance_from_moving_average = (
    btc["Close"] / twenty_day_moving_average - 1
) * 100

# Drawdown relative to the historical maximum available at each date.
drawdown = (btc["Close"] / btc["Close"].cummax() - 1) * 100

# Drawdown relative to the highest close in the recent 20-day window.
recent_drawdown = (
    btc["Close"] / btc["Close"].rolling(window=20).max() - 1
) * 100

# Relative range between the highest high and lowest low in the recent 20-day window.
recent_high_low_range = (
    btc["High"].rolling(window=20).max()
    / btc["Low"].rolling(window=20).min()
    - 1
) * 100

volume_change = btc["Volume"].pct_change() * 100


# Combine raw data and engineered features in one processed table.
btc_features = btc.assign(
    **{
        "One-day return": daily_return,
        "Five-day return": five_day_return,
        "Twenty-day return": twenty_day_return,
        "Five-day volatility": five_day_volatility,
        "Twenty-day volatility": twenty_day_volatility,
        "Sixty-day volatility": sixty_day_volatility,
        "Downside volatility": downside_volatility,
        "Sixty-day moving average": sixty_day_moving_average,
        "Moving average": twenty_day_moving_average,
        "Distance from moving average": distance_from_moving_average,
        "Drawdown": drawdown,
        "Recent drawdown": recent_drawdown,
        "Recent high-low range": recent_high_low_range,
        "Volume change": volume_change,
    }
)

PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
btc_features.to_csv(PROCESSED_FILE, index=False)

print(f"Saved {len(btc_features):,} rows to {PROCESSED_FILE}")
print("Columns:", ", ".join(btc_features.columns))
print("Missing values:")
print(btc_features.isna().sum().to_string())

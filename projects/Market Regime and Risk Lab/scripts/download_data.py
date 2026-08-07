from pathlib import Path

from yfinance import download


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "btc_data.csv"

RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
data = download("BTC-USD", start="2018-01-01", end="2025-12-31")
data.to_csv(RAW_FILE)

print(f"Saved raw data to {RAW_FILE}")

# Market Regime and Risk Lab

A reproducible financial machine-learning study of five-day future volatility for BTC-USD.

## Research question

Can information available at the end of date `t` improve the prediction of BTC-USD realised volatility over the next five daily observations, compared with a simple historical-volatility baseline?

## Scope

- Asset: BTC-USD.
- Frequency: daily, including weekends.
- Source: Yahoo Finance through `yfinance`.
- Sample: 2018-01-01 to 2025-12-30, 2,921 observations.
- Target: standard deviation of returns from `t+1` to `t+5`.
- Features: returns, rolling volatility, downside volatility, moving-average distance, drawdowns, recent range and volume change.
- Evaluation: boundary-safe expanding-window walk-forward evaluation.
- Models: historical-volatility baseline, Ridge regression and Random Forest.
- Trading simulation: not included in this version.

The project is a forecasting and evaluation study, not a claim of universal predictive accuracy or trading profitability.

## Repository structure

```text
Market Regime and Risk Lab/
├── data/
│   ├── raw/       Unchanged BTC-USD CSV
│   └── processed/ Engineered feature table
├── docs/          Detailed guide and documentation
├── reports/       Results, LaTeX reports, bibliography and figures
├── scripts/       Reproducible Python workflow and sensitivity experiments
└── requirements.txt
```

## Main files

- `data/raw/btc_data.csv` — unchanged raw BTC-USD export;
- `data/processed/btc_features.csv` — cleaned data and engineered features;
- `scripts/create_features.py` — creates the processed feature table;
- `scripts/final_evaluation.py` — authoritative boundary-safe evaluation;
- `scripts/generate_report_figures.py` — regenerates the three report figures;
- `scripts/descriptive_charts.py` — exploratory descriptive charts;
- `reports/final_walk_forward_results.csv` — final model comparison;
- `reports/final_walk_forward_predictions.csv` — dated predictions;
- `reports/ridge_without_2020_results.csv` — corrected no-2020 sensitivity;
- `reports/report_english.pdf` — English report;
- `reports/report_french.pdf` — French report;
- `docs/Market Regime and Risk Lab - Complete Guide.md` — detailed project guide.

The other scripts in `scripts/` are retained sensitivity experiments documented in the guide. They are not required for the authoritative final result.

## Reproduce from a clean Python environment

The project pins its Python dependencies in `requirements.txt`. From this project directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

The raw CSV is already included, so the reproducibility path does not need network access:

```bash
.venv/bin/python scripts/create_features.py
.venv/bin/python scripts/final_evaluation.py
.venv/bin/python scripts/generate_report_figures.py
```

To download the source data again instead, run this command first:

```bash
.venv/bin/python scripts/download_data.py
```

This refreshes the raw CSV from Yahoo Finance. Provider data can change, so a refreshed download may not reproduce the committed results byte-for-byte. The original raw CSV should be preserved before refreshing it.

## Evaluation design

The final evaluation uses these expanding windows:

- train through 2021, evaluate 2022;
- train through 2022, evaluate 2023;
- train through 2023, evaluate 2024;
- train through 2024, evaluate 2025.

A row is used only when its complete five-day target remains inside the corresponding training or evaluation period. This prevents target windows from crossing the train/test boundary.

## Main conclusion

Ridge regression has lower RMSE than the historical-volatility baseline in all four corrected yearly walk-forward periods. Random Forest improves on the baseline only in 2022. All Ridge $R^2$ values remain negative, so the result is a limited and period-dependent improvement rather than a highly accurate forecasting system.

## Data and security notes

- The raw file contains public BTC-USD market data and no user credentials.
- No API keys, private keys, passwords or exchange account information are required by this project.
- The downloader uses Yahoo Finance public data and does not require a secret.
- Local virtual environments, `.env` files, credentials and runtime output are excluded by the repository `.gitignore`.

See `docs/Market Regime and Risk Lab - Complete Guide.md` for the full methodology, source list, limitations and interpretation notes.

## Resources Used

- [yfinance GitHub repository](https://github.com/ranaroussi/yfinance)
- [NumPy documentation](https://numpy.org/doc/stable/)
- [Matplotlib documentation](https://matplotlib.org/stable/)
- [PCT_Changes](https://stackoverflow.com/questions/20000726/calculate-daily-returns-with-pandas-dataframe)
- [Pandas Manage CSV](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_csv.html)
- [Read CSV](https://www.datacamp.com/tutorial/pandas-read-csv?utm_cid=23340058065&utm_aid=192632748929&utm_campaign=230119_1-ps-dscia~dsa-tofu~python_2-b2c_3-emea_4-prc_5-na_6-na_7-le_8-pdsh-go_9-nb-e_10-na_11-na&utm_loc=9242458-&utm_mtd=-c&utm_kw=&utm_source=google&utm_medium=paid_search&utm_content=ps-dscia~emea-en~dsa~tofu~tutorial~python&gad_source=1&gad_campaignid=23340058065&gbraid=0AAAAADQ9WsEVeS-08oyvbDWwem3cDo3wH&gclid=CjwKCAjw4dDTBhAqEiwAkHYmSh0hc2yPxGO1Q_iEYqxbBS1ULROsyBc_1fseN81KawDFoGxDInsERRoCJKwQAvD_BwE)
- [Linear Regression](https://www.youtube.com/watch?v=O2Cw82YR5Bo)
- [Random Forest](https://www.youtube.com/watch?v=_QuGM_FW9eo&pp=ygUlcmFuZG9tIGZvcmVzdCBtYWNoaW5lIGxlYXJuaW5nIHB5dGhvbg%3D%3D)
-  [scikit-learn Pipelines](https://scikit-learn.org/stable/modules/compose.html)
- [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
- [statsmodels time-series analysis](https://www.statsmodels.org/stable/tsa.html)

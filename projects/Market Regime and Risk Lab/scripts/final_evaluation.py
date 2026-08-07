from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from scipy.stats import pearsonr, spearmanr
import pandas as pd
import numpy as np
from pathlib import Path

# File locations
PROJECT_ROOT = Path(__file__).resolve().parents[1] # Path to the root of the project
PROCESSED_FILE = PROJECT_ROOT / "data" / "processed" / "btc_features.csv"
REPORTS_DIRECTORY = PROJECT_ROOT / "reports"
REPORTS_DIRECTORY.mkdir(exist_ok=True)

# Read the CSV file containing the data.
df = pd.read_csv(PROCESSED_FILE)
df["Date"] = pd.to_datetime(df["Date"])
df = df.sort_values("Date").reset_index(drop=True)

# Create the future-volatility target.
future_five_day_volatility = df["Five-day volatility"].shift(-5)
df["future_five_day_volatility"] = future_five_day_volatility
# Explain the operation above.
df["target_end_date"] = df["Date"].shift(-5)

# Explain the operation above.
feature_columns = [
    "One-day return",
    "Five-day return",
    "Twenty-day return",
    "Five-day volatility",
    "Twenty-day volatility",
    "Sixty-day volatility",
    "Downside volatility",
    "Distance from moving average",
    "Drawdown",
    "Recent drawdown",
    "Recent high-low range",
    "Volume change",
]
target_column = "future_five_day_volatility"
model_columns = feature_columns + [target_column, "target_end_date"]
df = df.dropna(subset=model_columns).copy()

# Metrics used by all methods.

def calculate_metrics(y_true, predictions, volatility_threshold):
    y_true = pd.Series(y_true).reset_index(drop=True)
    predictions = pd.Series(predictions).reset_index(drop=True)
    errors = (y_true - predictions).abs()
    high_volatility = y_true >= volatility_threshold
    low_volatility = y_true < volatility_threshold

    if len(y_true) > 1:
        pearson_correlation = pearsonr(y_true, predictions)[0]
        spearman_correlation = spearmanr(y_true, predictions)[0]
    else:
        pearson_correlation = np.nan
        spearman_correlation = np.nan

    return {
        "MAE": mean_absolute_error(y_true, predictions),
        "RMSE": np.sqrt(mean_squared_error(y_true, predictions)),
        "R2": r2_score(y_true, predictions),
        "Pearson correlation": pearson_correlation,
        "Spearman rank correlation": spearman_correlation,
        "MAE high volatility": errors[high_volatility].mean(),
        "MAE low volatility": errors[low_volatility].mean(),
    }

# Years used for walk-forward evaluation.
walk_forward_periods = [
    (2022, 2021),
    (2023, 2022),
    (2024, 2023),
    (2025, 2024),
]

all_results = []
all_predictions = []
without_2020_results = []

for test_year, training_end_year in walk_forward_periods:
    test_start = pd.Timestamp(f"{test_year}-01-01")
    test_end = pd.Timestamp(f"{test_year}-12-31")
    training_end = pd.Timestamp(f"{training_end_year}-12-31")

    # The training target must remain entirely inside the training period.
    training_data = df[
        (df["Date"] <= training_end) &
        (df["target_end_date"] <= training_end)
    ].copy()

    # The test target must remain entirely inside the evaluation year.
    test_data = df[
        (df["Date"] >= test_start) &
        (df["Date"] <= test_end) &
        (df["target_end_date"] <= test_end)
    ].copy()

    X_train = training_data[feature_columns]
    y_train = training_data[target_column]
    X_test = test_data[feature_columns]
    y_test = test_data[target_column]

    # Calculate the threshold using training targets only.
    volatility_threshold = y_train.median()

    # Explain the operation above.
    baseline_predictions = test_data["Five-day volatility"]
    baseline_metrics = calculate_metrics(y_test, baseline_predictions, volatility_threshold)
    all_results.append({
        "Model": "Historical-volatility baseline",
        "Period": test_year,
        "Training period": f"up to {training_end_year}",
        "Features": "Five-day volatility",
        "Better than baseline": "Reference",
        **baseline_metrics,
    })

    # Ridge regression
    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train, y_train)
    ridge_predictions = ridge.predict(X_test)
    ridge_metrics = calculate_metrics(y_test, ridge_predictions, volatility_threshold)
    all_results.append({
        "Model": "Ridge regression",
        "Period": test_year,
        "Training period": f"up to {training_end_year}",
        "Features": "Full feature set",
        "Better than baseline": "Yes" if ridge_metrics["RMSE"] < baseline_metrics["RMSE"] else "No",
        **ridge_metrics,
    })

    # Random Forest
    random_forest = RandomForestRegressor(
        n_estimators=200,
        random_state=42,
        n_jobs=-1,
    )
    random_forest.fit(X_train, y_train)
    random_forest_predictions = random_forest.predict(X_test)
    random_forest_metrics = calculate_metrics(y_test, random_forest_predictions, volatility_threshold)
    all_results.append({
        "Model": "Random Forest",
        "Period": test_year,
        "Training period": f"up to {training_end_year}",
        "Features": "Full feature set",
        "Better than baseline": "Yes" if random_forest_metrics["RMSE"] < baseline_metrics["RMSE"] else "No",
        **random_forest_metrics,
    })

    # Sensitivity analysis: exclude 2020 from training observations.
    training_data_without_2020 = training_data[training_data["Date"].dt.year != 2020].copy()
    X_train_without_2020 = training_data_without_2020[feature_columns]
    y_train_without_2020 = training_data_without_2020[target_column]

    ridge_without_2020 = Ridge(alpha=1.0)
    ridge_without_2020.fit(X_train_without_2020, y_train_without_2020)
    ridge_without_2020_predictions = ridge_without_2020.predict(X_test)
    ridge_without_2020_metrics = calculate_metrics(
        y_test,
        ridge_without_2020_predictions,
        y_train_without_2020.median(),
    )
    without_2020_results.append({
        "Model": "Ridge regression without 2020",
        "Period": test_year,
        "Training period": f"up to {training_end_year}, excluding 2020",
        "Features": "Full feature set",
        **ridge_without_2020_metrics,
    })

    for date, actual, baseline, ridge_prediction, random_forest_prediction in zip(
        test_data["Date"],
        y_test,
        baseline_predictions,
        ridge_predictions,
        random_forest_predictions,
    ):
        all_predictions.append({
            "Date": date,
            "Period": test_year,
            "Actual future five-day volatility": actual,
            "Historical-volatility baseline": baseline,
            "Ridge regression": ridge_prediction,
            "Random Forest": random_forest_prediction,
        })

results = pd.DataFrame(all_results)
predictions = pd.DataFrame(all_predictions)
without_2020_results = pd.DataFrame(without_2020_results)

# Save the results to avoid copying values manually.
results.to_csv(REPORTS_DIRECTORY / "final_walk_forward_results.csv", index=False)
predictions.to_csv(REPORTS_DIRECTORY / "final_walk_forward_predictions.csv", index=False)
without_2020_results.to_csv(REPORTS_DIRECTORY / "ridge_without_2020_results.csv", index=False)

# Display the result.
pd.set_option("display.max_columns", None)
print("Walk-forward evaluation")
print(results.to_string(index=False))
print("\nRidge sensitivity without 2020")
print(without_2020_results.to_string(index=False))
print("\nSaved files:")
print(REPORTS_DIRECTORY / "final_walk_forward_results.csv")
print(REPORTS_DIRECTORY / "final_walk_forward_predictions.csv")
print(REPORTS_DIRECTORY / "ridge_without_2020_results.csv")

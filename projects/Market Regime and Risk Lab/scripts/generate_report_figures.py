from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_FILE = PROJECT_ROOT / "data" / "processed" / "btc_features.csv"
RESULTS_FILE = PROJECT_ROOT / "reports" / "final_walk_forward_results.csv"
PREDICTIONS_FILE = PROJECT_ROOT / "reports" / "final_walk_forward_predictions.csv"
FIGURES_DIRECTORY = PROJECT_ROOT / "reports" / "figures"


def main():
    processed = pd.read_csv(PROCESSED_FILE, parse_dates=["Date"])
    results = pd.read_csv(RESULTS_FILE)
    predictions = pd.read_csv(PREDICTIONS_FILE, parse_dates=["Date"])
    FIGURES_DIRECTORY.mkdir(parents=True, exist_ok=True)

    plt.style.use("seaborn-v0_8-whitegrid")

    figure, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    axes[0].plot(processed["Date"], processed["Close"], color="#1f4e79", linewidth=0.8)
    axes[0].set_title("BTC-USD closing price")
    axes[0].set_ylabel("Price (USD)")
    axes[1].plot(
        processed["Date"],
        processed["Five-day volatility"],
        label="5-day volatility",
        linewidth=0.8,
    )
    axes[1].plot(
        processed["Date"],
        processed["Sixty-day volatility"],
        label="60-day volatility",
        linewidth=0.8,
    )
    axes[1].set_title("Historical volatility features")
    axes[1].set_ylabel("Volatility (%)")
    axes[1].set_xlabel("Date")
    axes[1].legend()
    figure.tight_layout()
    figure.savefig(
        FIGURES_DIRECTORY / "btc_price_and_volatility.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.close(figure)

    pivot = results[results["Model"] != "Historical-volatility baseline"].pivot(
        index="Period", columns="Model", values="RMSE"
    )
    baseline = results[results["Model"] == "Historical-volatility baseline"].set_index(
        "Period"
    )["RMSE"]
    comparison = pd.concat(
        [baseline.rename("Historical-volatility baseline"), pivot], axis=1
    )
    axes = comparison.plot(
        kind="bar",
        figsize=(10, 6),
        color=["#7f8c8d", "#1f77b4", "#d95f02"],
    )
    axes.set_title("Walk-forward RMSE by evaluation year")
    axes.set_xlabel("Evaluation year")
    axes.set_ylabel("RMSE")
    axes.legend(title="Model")
    axes.set_xticklabels([str(int(value)) for value in comparison.index], rotation=0)
    figure = axes.get_figure()
    figure.tight_layout()
    figure.savefig(
        FIGURES_DIRECTORY / "walk_forward_rmse.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.close(figure)

    figure, axes = plt.subplots(2, 2, figsize=(12, 8), sharey=True)
    for axis, year in zip(axes.ravel(), sorted(predictions["Period"].unique())):
        subset = predictions[predictions["Period"] == year].sort_values("Date")
        axis.plot(
            subset["Date"],
            subset["Actual future five-day volatility"],
            label="Actual target",
            color="black",
            linewidth=0.9,
        )
        axis.plot(subset["Date"], subset["Ridge regression"], label="Ridge", linewidth=0.8)
        axis.plot(
            subset["Date"],
            subset["Historical-volatility baseline"],
            label="Baseline",
            linewidth=0.8,
            alpha=0.8,
        )
        axis.plot(
            subset["Date"],
            subset["Random Forest"],
            label="Random Forest",
            linewidth=0.8,
            alpha=0.8,
        )
        axis.set_title(str(year))
        axis.set_xlabel("Date")
        axis.set_ylabel("Future volatility")
        axis.tick_params(axis="x", rotation=35)

    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.02))
    figure.suptitle("Actual and predicted five-day future volatility", y=1.07)
    figure.tight_layout()
    figure.savefig(
        FIGURES_DIRECTORY / "predictions_by_year.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.close(figure)

    print(f"Saved figures to {FIGURES_DIRECTORY}")


if __name__ == "__main__":
    main()

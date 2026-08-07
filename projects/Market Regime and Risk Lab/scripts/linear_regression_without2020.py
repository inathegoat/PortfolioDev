from sklearn.linear_model import LinearRegression
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import pandas as pd
import pylab as pl
import scipy.stats as stats

# File locations
PROJECT_ROOT = Path(__file__).resolve().parents[1] # Path to the root of the project
PROCESSED_FILE = PROJECT_ROOT / "data" / "processed" / "btc_features.csv"
df = pd.read_csv(PROCESSED_FILE) # Read the CSV file containing the data.
df["Date"] = pd.to_datetime(df["Date"])


# Create the future-volatility target.

future_five_day_volatility = df["Five-day volatility"].shift(-5) # Shift the volatility column to create the future target.
df["future_five_day_volatility"] = future_five_day_volatility # Add the required item.

# Separate the data into training, validation and test sets.

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

model_columns = feature_columns + [target_column]
df = df.dropna(subset=model_columns)

learn = df[((df["Date"] >= "2018-01-01") & (df["Date"] < "2020-01-01")) | ((df["Date"] >= "2021-01-01") & (df["Date"] <= "2022-12-31"))] # Filter the rows for the specified date range.
valid = df[(df["Date"] > "2023-01-01") & (df["Date"] <= "2024-12-31")] # Filter the rows for the specified date range.
test = df[df["Date"] > "2025-01-01"] # Filter the rows for the specified date range.

X_learn = learn[feature_columns]
y_learn = learn[target_column]

X_valid = valid[feature_columns]
y_valid = valid[target_column]

X_test = test[feature_columns]
y_test = test[target_column]

# Create the regression model.


lm = Ridge(alpha=1.0) # Create the regression model.
lm.fit(X_learn, y_learn)

cdf = pd.DataFrame(lm.coef_, X_learn.columns, columns=['Coefficient']) # Create a DataFrame containing the model coefficients.
print(cdf)


predictions = lm.predict(X_valid) # Generate predictions for the selected data.

sns.scatterplot(x=predictions, y=y_valid) # Create the diagnostic chart.
plt.xlabel("Predictions") # Set the axis label.
plt.ylabel("True Values") # Set the axis label.
plt.title("Linear Regression Predictions vs True Values") # Set the chart title.
plt.show() # Display the result.

# Calculate the evaluation metrics.
mse = mean_squared_error(y_valid, predictions) # Calculate the mean squared error.
rmse = np.sqrt(mse) # Calculate the root mean squared error.
mae = mean_absolute_error(y_valid, predictions) # Calculate the mean absolute error.
r2 = r2_score(y_valid, predictions) # Calculate the R-squared score.

# Display the result.
print(f"Mean Squared Error (MSE): {mse:.4f}") #
print(f"Root Mean Squared Error (RMSE): {rmse:.4f}")
print(f"Mean Absolute Error (MAE): {mae:.4f}")
print(f"R-squared (R²): {r2:.4f}")

residuals = y_valid - predictions # Calculate the model residuals.
sns.displot(residuals, bins=30, kde=True) # Create a residual histogram.
plt.xlabel("Residuals") # Set the axis label.
plt.ylabel("Frequency") # Set the axis label.
plt.title("Residuals Distribution") # Set the chart title.
plt.show() # Display the result.

stats.probplot(residuals, dist="norm", plot=pl) # Create the diagnostic chart.
plt.show() # Display the result.

# Evaluate the model on the 2025 test data.

test_predictions = lm.predict(X_test) # Generate predictions for the selected data.
mse_test = mean_squared_error(y_test, test_predictions) # Calculate the mean squared error.
rmse_test = np.sqrt(mse_test) # Calculate the root mean squared error.
mae_test = mean_absolute_error(y_test, test_predictions) # Calculate the mean absolute error.
r2_test = r2_score(y_test, test_predictions) # Calculate the R-squared score.

print(f"Test Mean Squared Error (MSE): {mse_test:.4f}") # Display the result.
print(f"Test Root Mean Squared Error (RMSE): {rmse_test:.4f}") # Display the result.
print(f"Test Mean Absolute Error (MAE): {mae_test:.4f}") # Display the result.
print(f"Test R-squared (R²): {r2_test:.4f}") # Display the result.

residuals_test = y_test - test_predictions # Calculate the model residuals.
sns.displot(residuals_test, bins=30, kde=True) # Create a residual histogram.
plt.xlabel("Residuals") # Set the axis label.
plt.ylabel("Frequency") # Set the axis label.
plt.title("Residuals Distribution (Test Set)") # Set the chart title.
plt.show() # Display the result.

#--------Walk-forward evaluation---------
#Train 2018–2021 → test 2022
#Train 2018–2022 → test 2023
#Train 2018–2023 → test 2024
#Train 2018–2024 → test 2025

learn_2018_2021 = df[(df["Date"] >= "2018-01-01") & (df["Date"] <= "2021-12-31")]
test_2022 = df[(df["Date"] >= "2022-01-01") & (df["Date"] <= "2022-12-31")]

X_learn_2018_2021 = learn_2018_2021[feature_columns]
y_learn_2018_2021 = learn_2018_2021[target_column]

X_test_2022 = test_2022[feature_columns]
y_test_2022 = test_2022[target_column]

lm = Ridge(alpha=1.0) # Create the regression model.
lm.fit(X_learn_2018_2021, y_learn_2018_2021)

predictions_2022 = lm.predict(X_test_2022)

print("--------------------------------------")
print("Mean Squared Error (MSE) on test set 2022:", mean_squared_error(y_test_2022, predictions_2022)) # Calculate the mean squared error.
print("R-squared (R2) on test set 2022:", r2_score(y_test_2022, predictions_2022)) # Calculate the R-squared score.
print("Mean Absolute Error (MAE) on test set 2022:", mean_absolute_error(y_test_2022, predictions_2022)) # Calculate the mean absolute error.
print("--------------------------------------")

#Train 2018–2022 → test 2023
learn_2018_2022 = df[(df["Date"] >= "2018-01-01") & (df["Date"] <= "2022-12-31")]
test_2023 = df[(df["Date"] >= "2023-01-01") & (df["Date"] <= "2023-12-31")]

X_learn_2018_2022 = learn_2018_2022[feature_columns]
y_learn_2018_2022 = learn_2018_2022[target_column]
X_test_2023 = test_2023[feature_columns]
y_test_2023 = test_2023[target_column]

lm = Ridge(alpha=1.0) # Create the regression model.
lm.fit(X_learn_2018_2022, y_learn_2018_2022)

predictions_2023 = lm.predict(X_test_2023)


print("Mean Squared Error (MSE) on test set 2023:", mean_squared_error(y_test_2023, predictions_2023)) # Calculate the mean squared error.
print("R-squared (R2) on test set 2023:", r2_score(y_test_2023, predictions_2023)) # Calculate the R-squared score.
print("Mean Absolute Error (MAE) on test set 2023:", mean_absolute_error(y_test_2023, predictions_2023)) # Calculate the mean absolute error.
print("--------------------------------------")

#Train 2018–2023 → test 2024

learn_2018_2023 = df[(df["Date"] >= "2018-01-01") & (df["Date"] <= "2023-12-31")]
test_2024 = df[(df["Date"] >= "2024-01-01") & (df["Date"] <= "2024-12-31")]

X_learn_2018_2023 = learn_2018_2023[feature_columns]
y_learn_2018_2023 = learn_2018_2023[target_column]
X_test_2024 = test_2024[feature_columns]
y_test_2024 = test_2024[target_column]

lm = Ridge(alpha=1.0) # Create the regression model.
lm.fit(X_learn_2018_2023, y_learn_2018_2023)
predictions_2024 = lm.predict(X_test_2024)


print("Mean Squared Error (MSE) on test set 2024:", mean_squared_error(y_test_2024, predictions_2024)) # Calculate the mean squared error.
print("R-squared (R2) on test set 2024:", r2_score(y_test_2024, predictions_2024)) # Calculate the R-squared score.
print("Mean Absolute Error (MAE) on test set 2024:", mean_absolute_error(y_test_2024, predictions_2024)) # Calculate the mean absolute error.
print("--------------------------------------")

#Train 2018–2024 → test 2025
learn_2018_2024 = df[(df["Date"] >= "2018-01-01") & (df["Date"] <= "2024-12-31")]
test_2025 = df[(df["Date"] >= "2025-01-01") & (df["Date"] <= "2025-12-31")]

X_learn_2018_2024 = learn_2018_2024[feature_columns]
y_learn_2018_2024 = learn_2018_2024[target_column]
X_test_2025 = test_2025[feature_columns]
y_test_2025 = test_2025[target_column]

lm = Ridge(alpha=1.0) # Create the regression model.
lm.fit(X_learn_2018_2024, y_learn_2018_2024)
predictions_2025 = lm.predict(X_test_2025)


print("Mean Squared Error (MSE) on test set 2025:", mean_squared_error(y_test_2025, predictions_2025)) # Calculate the mean squared error.
print("R-squared (R2) on test set 2025:", r2_score(y_test_2025, predictions_2025)) # Calculate the R-squared score.
print("Mean Absolute Error (MAE) on test set 2025:", mean_absolute_error(y_test_2025, predictions_2025)) # Calculate the mean absolute error.

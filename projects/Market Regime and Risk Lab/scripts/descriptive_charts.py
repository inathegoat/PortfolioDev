from pathlib import Path

import matplotlib.pyplot as plt # Create charts with matplotlib
import pandas as pd
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from scipy.stats import skew

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "btc_data.csv"
btc_data = pd.read_csv(RAW_FILE) # Read the CSV file containing the data
btc = btc_data.drop(index = [0, 1],axis=0) # Remove metadata rows from the DataFrame.
date, close, high, low, open, volume = btc.columns # Assign the column names to variables.

# Display the result.
# Display the result.

#---------------Price Through Time----------------

fig, axis = plt.subplots(figsize=(12, 6))
axis.plot(btc[date], btc[close], label="Closed Price of Bitcoin (BTC-USD)", color="blue")
axis.set_title("Closed Price of Bitcoin (BTC-USD) from 2018 to 2025") # Set the chart title.
axis.set_xlabel("Date") # Set the axis label.
axis.set_ylabel("Closed Price (USD)") # Set the axis label.
axis.legend() # Add the required item.
plt.xticks(rotation=45) # Rotate the x-axis labels.
plt.show() # Display the result.

#-----------------Daily returns through time----------------

daily_returns = []
for i in range(3, len(btc[close])):
    daily_returns.append((float(btc[close][i]) - float(btc[close][i-1])) * 100 / float(btc[close][i-1])) # Calculate daily returns with a loop.

fig1, axis1 = plt.subplots(figsize=(12, 6))
axis1.plot(btc[date][3:], daily_returns, label="Daily Returns of Bitcoin (BTC-USD)", color="orange") # Plot the daily returns.
axis1.set_title("Daily Returns of Bitcoin (BTC-USD) from 2018 to 2025")
axis1.set_xlabel("Date")
axis1.set_ylabel("Daily Returns")
axis1.legend()
plt.xticks(rotation=45)
plt.show()

#-----------------Distribution of Daily Returns----------------

fig2, axis2 = plt.subplots(figsize=(12, 6))
axis2.hist(daily_returns, bins=50, label="Distribution of Daily Returns", color="green", alpha=0.4) # Plot the calculated values.
axis2.set_title("Distribution of Daily Returns of Bitcoin (BTC-USD) from 2018 to 2025")
axis2.set_xlabel("Daily Returns")
axis2.set_ylabel("Frequency")
axis2.legend()
plt.show()

#------------------Rolling Volatility----------------

rolling_volatility = []
for i in range(23, len(btc[close])):
    rolling_volatility.append(sum([((float(btc[close][j]) - float(btc[close][j-1])) * 100 / float(btc[close][j-1]))**2 for j in range(i-20, i)])**0.5) # Calculate rolling volatility.

fig3, axis3 = plt.subplots(figsize=(12, 6))
axis3.plot(btc[date][23:], rolling_volatility, label="Rolling Volatility of Bitcoin (BTC-USD)", color="red")
axis3.set_title("Rolling Volatility of Bitcoin (BTC-USD) from 2018 to 2025")
axis3.set_xlabel("Date")
axis3.set_ylabel("Rolling Volatility")
axis3.legend()
plt.xticks(rotation=45)
plt.show()

skewness_scipy = skew(daily_returns) # Calculate return skewness.
print("Skewness using SciPy:", skewness_scipy)

kurtosis_scipy = pd.Series(daily_returns).kurtosis() # Calculate return kurtosis.
print("Kurtosis using pandas:", kurtosis_scipy)

#-----------------Drawdown from the previous historical maximum----------------

drawdown = []
for i in range(3, len(btc[close])):
    drawdown.append((float(btc[close][i]) - max([float(btc[close][j]) for j in range(2, i)])) * 100 / max([float(btc[close][j]) for j in range(2, i)])) # Calculate drawdown relative to the previous historical maximum.

fig4, axis4 = plt.subplots(figsize=(12, 6))
axis4.plot(btc[date][3:], drawdown, label="Drawdown of Bitcoin (BTC-USD)", color="purple")
axis4.set_title("Drawdown of Bitcoin (BTC-USD) from 2018 to 2025")
axis4.set_xlabel("Date")
axis4.set_ylabel("Drawdown (%)")
axis4.legend()
plt.xticks(rotation=45)
plt.show()

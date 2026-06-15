import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score

start = "2021-01-01"
AAPL = yf.download("AAPL", start = start)

dfAAPL = pd.DataFrame(AAPL)
dfAAPL.columns = dfAAPL.columns.get_level_values(0)

# print(dfAAPL.tail(5))
# print(dfAAPL.info())
# print(dfAAPL.describe())

# Find average closing price this week

# print(dfAAPL.iloc[-5:]["Close"].mean())

# Plot close price per day over last five days

# dfAAPL.iloc[-5:].plot.line(y= "Close", figsize = (10,6), title = "Close Price per Day this Week")
# plt.show()

# First Features
dfAAPL["pct_change"] = dfAAPL["Close"].pct_change()
dfAAPL["ma_5"] = dfAAPL["Close"].rolling(5).mean()
dfAAPL["ma_20"] = dfAAPL["Close"].rolling(20).mean()
dfAAPL["volatility"] = dfAAPL["pct_change"].rolling(10).std()

# More Features + Target
dfAAPL["volume_change"] = dfAAPL["Volume"].pct_change()
dfAAPL["high_low_change"] = (dfAAPL["High"] - dfAAPL["Low"]) / (dfAAPL["Close"])
dfAAPL["gap"] = dfAAPL["Open"] - dfAAPL["Close"].shift(1)
dfAAPL["target"] = (dfAAPL["Close"].shift(-1) > dfAAPL["Close"]).astype(int)
dfAAPL = dfAAPL.iloc[:-1]

# print(dfAAPL.head(25))

cleaned_dfAAPL = dfAAPL.dropna()

# Make sure NaN values are gone
print(cleaned_dfAAPL.shape)
print(cleaned_dfAAPL.tail(25))

# Make sure most recent day is gone
print(cleaned_dfAAPL["target"].tail(1))


# Seperate features from target
X = cleaned_dfAAPL[["pct_change", "ma_5", "ma_20", "volatility", "volume_change", "high_low_change", "gap"]]
y = cleaned_dfAAPL["target"]

# Split by Time
split = int(len(cleaned_dfAAPL) * 0.8)

X_train = X[:split]
X_test = X[split:]

y_train = y[:split]
y_test = y[split:]
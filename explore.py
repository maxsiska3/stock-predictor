import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

start = "2021-01-01"
AAPL = yf.download("AAPL", start = start)

dfAAPL = pd.DataFrame(AAPL)
dfAAPL.columns = dfAAPL.columns.get_level_values(0)

print(dfAAPL.tail(5))
print(dfAAPL.info())
print(dfAAPL.describe())

# Find average closing price this week

# print(dfAAPL.iloc[-5:]["Close"].mean())

# Plot close price per day over last five days

# dfAAPL.iloc[-5:].plot.line(y= "Close", figsize = (10,6), title = "Close Price per Day this Week")
# plt.show()

dfAAPL["pct_change"] = dfAAPL["Close"].pct_change()
dfAAPL["ma_5"] = dfAAPL["Close"].rolling(5).mean()
dfAAPL["ma_20"] = dfAAPL["Close"].rolling(20).mean()
dfAAPL["volatility"] = dfAAPL["pct_change"].rolling(10).std()

print(dfAAPL.head(25))
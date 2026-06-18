import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split, TimeSeriesSplit, cross_val_score, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier,GradientBoostingClassifier 
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score

# Create start date and download data
start = "2021-01-01"
AAPL = yf.download("AAPL", start = start)

# Create dataframe
dfAAPL = pd.DataFrame(AAPL)
dfAAPL.columns = dfAAPL.columns.get_level_values(0)

# Check data
# print(dfAAPL.tail(5))
# print(dfAAPL.info())
# print(dfAAPL.describe())

# Test data by finding average closing price this week

# print(dfAAPL.iloc[-5:]["Close"].mean())

# Test data by plotting close price per day over last five days

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

# RSI Feature (Relative Strength Index)
daily_aapl_change = dfAAPL["Close"].diff()
aapl_gains = daily_aapl_change.clip(lower=0)
aapl_losses = (-daily_aapl_change).clip(lower=0)
aapl_rolling_gains = aapl_gains.rolling(14).mean()
aapl_rolling_losses = aapl_losses.rolling(14).mean()
aapl_rs = aapl_rolling_gains / aapl_rolling_losses
dfAAPL["rsi"] = 100 - (100/(1 + aapl_rs))

# MACD Feature (Moving Average Conversion Difference)
aapl_ema_12 = dfAAPL["Close"].ewm(span=12).mean()
aapl_ema_26 = dfAAPL["Close"].ewm(span=26).mean()
dfAAPL["macd"] = aapl_ema_12 - aapl_ema_26

# Bollinger Bands (Upper and Lower Bounds)
aapl_bb_std = dfAAPL["Close"].rolling(20).std()
aapl_bb_upper = dfAAPL["ma_20"] + (2 * aapl_bb_std)
aapl_bb_lower = dfAAPL["ma_20"] - (2 * aapl_bb_std)
dfAAPL["bollinger_bands_position"] = (dfAAPL["Close"] - aapl_bb_lower) / (aapl_bb_upper - aapl_bb_lower)

# Clean data by sclicing off last row and dropping nulls
dfAAPL = dfAAPL.iloc[:-1]
cleaned_dfAAPL = dfAAPL.dropna()

# print(dfAAPL.head(25))

# Make sure NaN values are gone
print("\n=== Data Shape ===")
print(cleaned_dfAAPL.shape)
print("\n=== Last 25 Rows ===")
print(cleaned_dfAAPL.tail(25))

# Make sure most recent day is gone
print("\n=== Most Recent Target ===")
print(cleaned_dfAAPL["target"].tail(1))

# Seperate features from target
X = cleaned_dfAAPL[["pct_change", "volatility", "volume_change", "high_low_change", "gap", "rsi", "macd", "bollinger_bands_position"]]
y = cleaned_dfAAPL["target"]

# Time Series Split
aapl_time_series_split = TimeSeriesSplit(n_splits=5)

# Pipeline
aapl_pipe = Pipeline([
    ("scaler", StandardScaler()),
    ("model", RandomForestClassifier(n_estimators=200, random_state=42))
    
])

# Cross Value Reference 
aapl_cross_value_score = cross_val_score(aapl_pipe, X, y, cv=aapl_time_series_split)
print("\n=== Cross Value Score ===")
print("Each fold:", aapl_cross_value_score)
print("Average:", aapl_cross_value_score.mean())

# # Grid Search CV
# aapl_param_grid = {
#     "model__n_estimators": [100, 200, 500],
#     "model__max_depth": [5, 10, 20, None],
#     "model__min_samples_split": [2, 5, 10]
# }

# aapl_grid_search_cv = GridSearchCV(aapl_pipe, aapl_param_grid, cv=aapl_time_series_split)
# aapl_grid_search_cv.fit(X, y)
# print("\n=== Grid Search ===")
# print("Best Parameters", aapl_grid_search_cv.best_params_)
# print("Best Score", aapl_grid_search_cv.best_score_)


# Split by Time
split = int(len(cleaned_dfAAPL) * 0.8)

X_train = X[:split]
X_test = X[split:]

y_train = y[:split]
y_test = y[split:]

# Standard Scaling

print("\n=== Before Scaling ===")
print(X_train[:5])
scaler = StandardScaler()
scaler.fit(X_train)

X_train = scaler.transform(X_train)
X_test = scaler.transform(X_test)
print("\n=== After Scaling ===")
print(X_train[:5])

# # Logistic Regression

# log_reg_model = LogisticRegression()
# log_reg_model.fit(X_train, y_train)

# print("\n=== Logistic Regression ===")
# print(f"  Train accuracy: {log_reg_model.score(X_train, y_train):.4f}")
# print(f"  Test accuracy:  {log_reg_model.score(X_test, y_test):.4f}")

# Random Forest

rand_for_model = RandomForestClassifier(
    n_estimators=200, 
    max_depth=20, 
    min_samples_split=10, 
    random_state=42
)
rand_for_model.fit(X_train, y_train)

print("\n=== Random Forest ===")
print(f"  Train accuracy: {rand_for_model.score(X_train, y_train):.4f}")
print(f"  Test accuracy:  {rand_for_model.score(X_test, y_test):.4f}")

# Measuring Random Forest Importance

feature_names = ["pct_change", "volatility", "volume_change", "high_low_change", "gap", "rsi", "macd", "boiler_bands_position"]
print("\n  Feature Importances:")
for name, score in zip(feature_names, rand_for_model.feature_importances_):
    print(f"    {name:<20} {score:.4f}")

# # Gradient Boosting

# grad_boost_model = GradientBoostingClassifier(random_state=42)
# grad_boost_model.fit(X_train, y_train)

# print("\n=== Gradient Boosting ===")
# print(f"  Train accuracy: {grad_boost_model.score(X_train, y_train):.4f}")
# print(f"  Test accuracy:  {grad_boost_model.score(X_test, y_test):.4f}")
# print()


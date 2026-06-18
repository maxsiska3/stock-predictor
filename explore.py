import numpy as np
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import joblib as jl

from sklearn.model_selection import train_test_split, TimeSeriesSplit, cross_val_score, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score

FEATURE_COLS = [
    "pct_change", "volatility", "volume_change", "high_low_change",
    "gap", "rsi", "macd", "bollinger_bands_position"
]


def compute_features(df):
    """Compute all model features for an OHLCV DataFrame. Safe to call on any ticker.

    For live predictions in Flask: pass at least 100 rows of history so EWM-based
    features (MACD) are fully warmed up, then use only the last row for prediction.
    gap requires today's Open price, so predictions must run after market open.
    """
    df = df.copy()

    df["pct_change"] = df["Close"].pct_change()
    df["ma_20"] = df["Close"].rolling(20).mean()
    df["volatility"] = df["pct_change"].rolling(10).std()
    df["volume_change"] = df["Volume"].pct_change()
    df["high_low_change"] = (df["High"] - df["Low"]) / df["Close"]
    df["gap"] = df["Open"] - df["Close"].shift(1)

    # RSI — uses simple rolling mean (not Wilder's EMA). Flask must replicate this exact formula.
    daily_change = df["Close"].diff()
    gains = daily_change.clip(lower=0)
    losses = (-daily_change).clip(lower=0)
    df["rsi"] = 100 - (100 / (1 + gains.rolling(14).mean() / losses.rolling(14).mean()))

    # MACD (Moving Average Convergence Divergence)
    ema_12 = df["Close"].ewm(span=12).mean()
    ema_26 = df["Close"].ewm(span=26).mean()
    df["macd"] = ema_12 - ema_26

    # Bollinger Bands
    bb_std = df["Close"].rolling(20).std()
    bb_upper = df["ma_20"] + (2 * bb_std)
    bb_lower = df["ma_20"] - (2 * bb_std)
    df["bollinger_bands_position"] = (df["Close"] - bb_lower) / (bb_upper - bb_lower)
    df["bollinger_bands_position"] = df["bollinger_bands_position"].replace([np.inf, -np.inf], np.nan)

    return df


# Create start date and download data
start = "2021-01-01"
AAPL = yf.download("AAPL", start=start)

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

# Compute features and target
dfAAPL = compute_features(dfAAPL)
dfAAPL["target"] = (dfAAPL["Close"].shift(-1) > dfAAPL["Close"]).astype(int)

# Clean data by slicing off last row and dropping nulls
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
X = cleaned_dfAAPL[FEATURE_COLS]
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

print("\n  Feature Importances:")
for name, score in zip(FEATURE_COLS, rand_for_model.feature_importances_):
    print(f"    {name:<20} {score:.4f}")

# # Gradient Boosting

# grad_boost_model = GradientBoostingClassifier(random_state=42)
# grad_boost_model.fit(X_train, y_train)

# print("\n=== Gradient Boosting ===")
# print(f"  Train accuracy: {grad_boost_model.score(X_train, y_train):.4f}")
# print(f"  Test accuracy:  {grad_boost_model.score(X_test, y_test):.4f}")
# print()

jl.dump(rand_for_model, "model/trained_model.pkl")
jl.dump(scaler, "model/scaler.pkl")

# =============================================================================
# SUMMARY
# =============================================================================
#
# This file trains a binary classifier to predict whether AAPL's closing price
# will be higher or lower the following trading day (1 = up, 0 = down).
#
# DATA
# Downloads 5 years of AAPL OHLCV data via yfinance starting from 2021-01-01.
# The target is created by shifting the Close price back one day and comparing
# it to the current Close. The last row is dropped since it has no next-day
# target, and early rows are dropped where rolling windows haven't warmed up.
#
# FEATURES (defined in FEATURE_COLS, engineered in compute_features())
#   pct_change            - daily percent change in Close price
#   volatility            - 10-day rolling std of pct_change
#   volume_change         - daily percent change in Volume
#   high_low_change       - (High - Low) / Close, measures intraday range
#   gap                   - today's Open minus yesterday's Close
#   rsi                   - Relative Strength Index over 14 days (simple rolling mean)
#   macd                  - difference between 12-day and 26-day EMA of Close
#   bollinger_bands_position - where Close sits within the 20-day Bollinger Band range
#
# TRAINING
# Data is split 80/20 by time (no shuffling) to prevent future leakage.
# Features are scaled with StandardScaler fit on the training set only.
# A RandomForestClassifier is trained with n_estimators=200, max_depth=20,
# and min_samples_split=10. Cross-validation uses TimeSeriesSplit with 5 folds.
# Cross-validated accuracy is around 52%, single-split test accuracy around 57%.
#
# OUTPUTS
# The trained model and scaler are saved to model/ via joblib so the Flask app
# can load them for live predictions without retraining.
#
# FLASK NOTES
# Import compute_features() and FEATURE_COLS from this file to guarantee the
# live feature engineering matches exactly what the model was trained on.
# Pass at least 100 rows of history to compute_features() so the EWM-based
# MACD values are fully warmed up, then use only the last row for prediction.
# The gap feature requires today's Open price, so predictions must run after
# market open.
# =============================================================================

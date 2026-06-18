import numpy as np

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

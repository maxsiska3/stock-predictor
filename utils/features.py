import numpy as np

FEATURE_COLS = [
    "pct_change", "volatility", "volume_change", "high_low_change",
    "gap", "rsi", "macd", "bollinger_bands_position",
    "spy_pct_change", "excess_return",
    "pct_change_lag1", "rsi_lag1", "return_5d",
    "volume_sma_ratio", "atr_pct", "momentum_20d",
]


def compute_features(df, spy_df=None):
    """Compute all model features for an OHLCV DataFrame.

    Pass spy_df (OHLCV for SPY) to add market-context columns. Same spy_df
    must be used in training and inference for parity.

    For live predictions: pass at least 100 rows so EWM features warm up.
    gap requires today's Open — run after market open for meaningful values.
    """
    df = df.copy()

    df["pct_change"] = df["Close"].pct_change()
    df["ma_20"] = df["Close"].rolling(20).mean()
    df["volatility"] = df["pct_change"].rolling(10).std()
    df["volume_change"] = df["Volume"].pct_change().replace([np.inf, -np.inf], np.nan)
    df["high_low_change"] = (df["High"] - df["Low"]) / df["Close"]
    df["gap"] = df["Open"] - df["Close"].shift(1)

    daily_change = df["Close"].diff()
    gains = daily_change.clip(lower=0)
    losses = (-daily_change).clip(lower=0)
    df["rsi"] = 100 - (100 / (1 + gains.rolling(14).mean() / losses.rolling(14).mean()))

    ema_12 = df["Close"].ewm(span=12).mean()
    ema_26 = df["Close"].ewm(span=26).mean()
    df["macd"] = ema_12 - ema_26

    bb_std = df["Close"].rolling(20).std()
    bb_upper = df["ma_20"] + (2 * bb_std)
    bb_lower = df["ma_20"] - (2 * bb_std)
    df["bollinger_bands_position"] = (df["Close"] - bb_lower) / (bb_upper - bb_lower)
    df["bollinger_bands_position"] = df["bollinger_bands_position"].replace([np.inf, -np.inf], np.nan)

    if spy_df is not None:
        spy_close = spy_df["Close"].reindex(df.index)
        df["spy_pct_change"] = spy_close.pct_change()
        df["excess_return"] = df["pct_change"] - df["spy_pct_change"]
    else:
        df["spy_pct_change"] = np.nan
        df["excess_return"] = np.nan

    df["pct_change_lag1"] = df["pct_change"].shift(1)
    df["rsi_lag1"] = df["rsi"].shift(1)
    df["return_5d"] = df["Close"].pct_change(5)
    df["volume_sma_ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()
    df["atr_pct"] = ((df["High"] - df["Low"]) / df["Close"]).rolling(10).mean()
    df["momentum_20d"] = df["Close"] / df["Close"].shift(20) - 1

    return df

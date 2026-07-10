import joblib as jl
import numpy as np
import yfinance as yf
import pandas as pd
from pathlib import Path

from utils.features import compute_features, FEATURE_COLS
from utils.yfinance_setup import configure_yfinance, get_yf_session

_ROOT = Path(__file__).resolve().parent.parent
MIN_HISTORY_ROWS = 100

configure_yfinance()

# Load Model (paths anchored to repo root, not CWD)
scaler = jl.load(_ROOT / "model" / "scaler.pkl")
trained_model = jl.load(_ROOT / "model" / "trained_model.pkl")
_SESSION = get_yf_session()


def _flatten_download(df):
    raw_df = pd.DataFrame(df)
    if isinstance(raw_df.columns, pd.MultiIndex):
        raw_df.columns = raw_df.columns.get_level_values(0)
    return raw_df


def _row_is_finite(row) -> bool:
    return bool(np.isfinite(row[FEATURE_COLS].iloc[0]).all())


def predict_stock(ticker, history_df=None) -> tuple:
    """Predict next-day direction. Pass history_df to skip a redundant download."""
    if history_df is not None and len(history_df) >= MIN_HISTORY_ROWS:
        raw_df = history_df.copy()
    else:
        start = pd.Timestamp.now() - pd.DateOffset(months=6)
        raw_df = _flatten_download(yf.download(ticker, start=start, progress=False, session=_SESSION, threads=False))

    if raw_df is None or len(raw_df) < MIN_HISTORY_ROWS:
        raise ValueError(
            f"insufficient history for {ticker}: need {MIN_HISTORY_ROWS} rows, got {0 if raw_df is None else len(raw_df)}"
        )

    df_features = compute_features(raw_df)

    # Grab Last Row
    last_row = df_features[FEATURE_COLS].iloc[[-1]]
    if not _row_is_finite(last_row):
        raise ValueError(f"non-finite features for {ticker}")

    # Scale Data
    scaled_features = scaler.transform(last_row)

    # Predict Up or Down and Confidence
    prediction = trained_model.predict(scaled_features)
    confidence = trained_model.predict_proba(scaled_features)

    return prediction, confidence

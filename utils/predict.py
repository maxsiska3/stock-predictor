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

scaler = jl.load(_ROOT / "model" / "scaler.pkl")
trained_model = jl.load(_ROOT / "model" / "trained_model.pkl")
_SESSION = get_yf_session()


def _flatten_download(df):
    raw_df = pd.DataFrame(df)
    if isinstance(raw_df.columns, pd.MultiIndex):
        raw_df.columns = raw_df.columns.get_level_values(0)
    return raw_df


def _download_spy_for_index(index, session=None, _retry=True):
    """Fetch SPY OHLCV covering the same dates as the stock history."""
    session = session or _SESSION
    start = pd.Timestamp(index.min()).normalize() - pd.Timedelta(days=7)
    try:
        spy = _flatten_download(
            yf.download("SPY", start=start, progress=False, session=session, threads=False)
        )
        if spy is None or spy.empty:
            raise ValueError("empty SPY download")
        return spy
    except Exception:
        if _retry:
            from utils.yfinance_setup import reset_yf_session
            reset_yf_session()
            return _download_spy_for_index(index, session=get_yf_session(), _retry=False)
        raise


def _row_is_finite(row) -> bool:
    return bool(np.isfinite(row[FEATURE_COLS].iloc[0]).all())


def predict_stock(ticker, history_df=None) -> tuple:
    """Predict next-day direction. Pass history_df to skip a redundant download."""
    session = _SESSION
    if history_df is not None and len(history_df) >= MIN_HISTORY_ROWS:
        raw_df = history_df.copy()
    else:
        start = pd.Timestamp.now() - pd.DateOffset(months=6)
        raw_df = _flatten_download(
            yf.download(ticker, start=start, progress=False, session=session, threads=False)
        )

    if raw_df is None or len(raw_df) < MIN_HISTORY_ROWS:
        raise ValueError(
            f"insufficient history for {ticker}: need {MIN_HISTORY_ROWS} rows, got {0 if raw_df is None else len(raw_df)}"
        )

    spy_df = _download_spy_for_index(raw_df.index, session=session)
    df_features = compute_features(raw_df, spy_df=spy_df)

    last_row = df_features[FEATURE_COLS].iloc[[-1]]
    if not _row_is_finite(last_row):
        raise ValueError(f"non-finite features for {ticker}")

    scaled_features = scaler.transform(last_row)
    prediction = trained_model.predict(scaled_features)
    confidence = trained_model.predict_proba(scaled_features)

    return prediction, confidence

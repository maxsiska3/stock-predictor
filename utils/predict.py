import joblib as jl
import yfinance as yf
import pandas as pd
from utils.features import compute_features, FEATURE_COLS
from utils.yfinance_setup import get_yf_session

# Load Model
scaler = jl.load("model/scaler.pkl")
trained_model = jl.load("model/trained_model.pkl")
_SESSION = get_yf_session()


def _flatten_download(df):
    raw_df = pd.DataFrame(df)
    if isinstance(raw_df.columns, pd.MultiIndex):
        raw_df.columns = raw_df.columns.get_level_values(0)
    return raw_df


def predict_stock(ticker, history_df=None) -> tuple:
    """Predict next-day direction. Pass history_df to skip a redundant download."""
    if history_df is not None and len(history_df) >= 30:
        raw_df = history_df.copy()
    else:
        start = pd.Timestamp.now() - pd.DateOffset(months=6)
        raw_df = _flatten_download(yf.download(ticker, start=start, progress=False, session=_SESSION, threads=False))

    df_features = compute_features(raw_df)

    # Grab Last Row
    last_row = df_features[FEATURE_COLS].iloc[[-1]]

    # Scale Data
    scaled_features = scaler.transform(last_row)

    # Predict Up or Down and Confidence
    prediction = trained_model.predict(scaled_features)
    confidence = trained_model.predict_proba(scaled_features)

    return prediction, confidence

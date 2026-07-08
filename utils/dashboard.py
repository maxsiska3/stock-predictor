import yfinance as yf
import pandas as pd

from utils.predict import predict_stock
from utils.yfinance_setup import configure_yfinance, get_yf_session

configure_yfinance()


def _flatten_download(df):
    raw_df = pd.DataFrame(df)
    if isinstance(raw_df.columns, pd.MultiIndex):
        raw_df.columns = raw_df.columns.get_level_values(0)
    return raw_df


def download_ohlcv(ticker):
    """Download ~6 months OHLCV once. Returns cleaned DataFrame or None."""
    try:
        session = get_yf_session()
        start = pd.Timestamp.now() - pd.DateOffset(months=6)
        raw_df = _flatten_download(
            yf.download(ticker, start=start, progress=False, session=session, threads=False)
        )
        if raw_df.empty:
            return None
        return raw_df.dropna(subset=["Open", "High", "Low", "Close"])
    except Exception:
        return None


def _history_from_df(df, days=60):
    tail = df.tail(days)
    if tail.empty:
        return None

    dates = [ts.date().isoformat() for ts in tail.index]
    prices = [round(float(v), 2) for v in tail["Close"]]
    ohlc = [
        {
            "o": round(float(row["Open"]), 2),
            "h": round(float(row["High"]), 2),
            "l": round(float(row["Low"]), 2),
            "c": round(float(row["Close"]), 2),
        }
        for _, row in tail.iterrows()
    ]
    return {"dates": dates, "prices": prices, "ohlc": ohlc}


def fetch_sector(ticker: str) -> str:
    try:
        session = get_yf_session()
        stock = yf.Ticker(ticker, session=session) if session else yf.Ticker(ticker)
        info = stock.info or {}

        sector = info.get("sector")
        if isinstance(sector, str) and sector.strip():
            return sector.strip()

        industry = info.get("industry")
        if isinstance(industry, str) and industry.strip():
            return industry.strip()

        return "Unknown"
    except Exception:
        return "Unknown"


def fetch_history(ticker, raw_df=None, days=60):
    """Build chart JSON from pre-fetched OHLCV or download if needed."""
    try:
        df = raw_df if raw_df is not None else download_ohlcv(ticker)
        if df is None or df.empty:
            return None
        return _history_from_df(df, days)
    except Exception:
        return None


def fetch_prediction(ticker, history_df=None):
    """Run model on OHLCV. Returns (direction, confidence) or (None, None)."""
    try:
        prediction, proba = predict_stock(ticker, history_df=history_df)
        direction = "up" if prediction[0] == 1 else "down"
        confidence = round(float(proba[0].max()) * 100, 1)
        return direction, confidence
    except Exception:
        return None, None

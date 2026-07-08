import yfinance as yf
import pandas as pd

from utils.yfinance_setup import configure_yfinance, get_yf_session

configure_yfinance()


def _flatten_download(df):
    raw_df = pd.DataFrame(df)
    if isinstance(raw_df.columns, pd.MultiIndex):
        raw_df.columns = raw_df.columns.get_level_values(0)
    return raw_df


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


def fetch_history(ticker, days=60):
    try:
        session = get_yf_session()
        start = pd.Timestamp.now() - pd.DateOffset(months=6)
        raw_df = _flatten_download(
            yf.download(ticker, start=start, progress=False, session=session, threads=False)
        )
        if raw_df.empty:
            return None

        df = raw_df.dropna(subset=["Open", "High", "Low", "Close"]).tail(days)
        if df.empty:
            return None

        dates = [ts.date().isoformat() for ts in df.index]
        prices = [round(float(v), 2) for v in df["Close"]]
        ohlc = [
            {
                "o": round(float(row["Open"]), 2),
                "h": round(float(row["High"]), 2),
                "l": round(float(row["Low"]), 2),
                "c": round(float(row["Close"]), 2),
            }
            for _, row in df.iterrows()
        ]

        return {"dates": dates, "prices": prices, "ohlc": ohlc}
    except Exception:
        return None

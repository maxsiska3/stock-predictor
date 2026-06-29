# utils/market.py — market data fetching and caching layer
#
# Batch-downloads yfinance data, computes indicators, runs ML predictions.
# Cached for 60 seconds and keyed by ticker set (see watchlist_store + clear_cache).

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

from utils.features import compute_features
from utils.predict import predict_stock

# Module-level cache — lives for the server process lifetime (same pattern as ticker_search).
_cache = {"data": None, "updated_at": None, "tickers_key": None}

_CACHE_TTL = timedelta(seconds=60)


def clear_cache():
    """Clear cached market data (call after watchlist add/remove)."""
    _cache["data"] = None
    _cache["updated_at"] = None
    _cache["tickers_key"] = None


def _tickers_key(tickers):
    """Stable cache key so order doesn't matter but different sets don't collide."""
    return tuple(sorted(tickers))


def _slice_ticker(df, ticker):
    """Extract one ticker's OHLCV from a single- or multi-ticker yfinance DataFrame."""
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        return df[ticker].copy()
    return df.copy()


def _safe_float(val, digits=2):
    """Return a rounded float, or None if missing/NaN."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return None


# Shown in equity columns (EPS, Beta) when the metric doesn't apply to ETFs.
_ETF_NA = "N/A"


def _etf_display_fields(info, eps, beta, sector):
    """
    Fallbacks for ETF rows where stock-style fundamentals are missing.

    We don't substitute other metrics (e.g. expense ratio in the EPS column) —
    that reads like real data but means something else. N/A is honest.

    Sector uses yfinance 'category' when available (e.g. "Large Blend") since
    that's the ETF equivalent and is usually populated.
    """
    quote_type = (info.get("quoteType") or "").upper()
    if quote_type != "ETF":
        return None, None, sector or None

    category = info.get("category")

    eps_note = _ETF_NA if eps is None else None
    beta_note = _ETF_NA if beta is None else None
    sector_display = sector or category or None
    return eps_note, beta_note, sector_display


def _ticker_info(ticker):
    """Fetch yfinance .info dict with safe defaults."""
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


def fetch_market_data(tickers):
    """
    Fetch live price, change, volume, and ML prediction for each ticker.
    Returns a list of dicts, one per ticker.
    Results are cached for 60 seconds to avoid hammering the yfinance rate limit.
    Cache is keyed by ticker set — changing the watchlist requires a fresh fetch.
    """
    if not tickers:
        return []

    key = _tickers_key(tickers)

    if (
        _cache["data"] is not None
        and _cache["updated_at"] is not None
        and _cache["tickers_key"] == key
    ):
        age = datetime.now() - _cache["updated_at"]
        if age < _CACHE_TTL:
            return _cache["data"]

    daily_df    = yf.download(tickers, period="2d",  interval="1d", group_by="ticker", auto_adjust=True)
    intraday_df = yf.download(tickers, period="1d",  interval="1m", group_by="ticker", auto_adjust=True)
    year_df     = yf.download(tickers, period="1y",  interval="1d", group_by="ticker", auto_adjust=True)

    list_data = []

    for ticker in tickers:
        try:
            ticker_daily    = _slice_ticker(daily_df, ticker)
            ticker_intraday = _slice_ticker(intraday_df, ticker)
            ticker_year     = _slice_ticker(year_df, ticker)

            prev_close = ticker_daily["Close"].iloc[-2]

            if ticker_intraday is None or ticker_intraday.empty:
                current_price = ticker_daily["Close"].iloc[-1]
                volume = 0
            else:
                current_price = ticker_intraday["Close"].iloc[-1]
                volume = int(ticker_intraday["Volume"].sum())

            change     = current_price - prev_close
            pct_change = round((change / prev_close) * 100, 2)

            # 52-week range from 1y daily history
            week_52_high = None
            week_52_low  = None
            if ticker_year is not None and not ticker_year.empty:
                week_52_high = _safe_float(ticker_year["High"].max())
                week_52_low  = _safe_float(ticker_year["Low"].min())

            # Technical indicators — same formulas as the ML model (features.py)
            rsi = bollinger_pos = volatility = macd = None
            if ticker_year is not None and len(ticker_year) >= 30:
                features = compute_features(ticker_year)
                last = features.iloc[-1]
                rsi           = _safe_float(last["rsi"], 1)
                bollinger_pos = _safe_float(last["bollinger_bands_position"], 2)
                volatility    = _safe_float(last["volatility"], 4)
                macd          = _safe_float(last["macd"], 2)

            # Fundamentals from yfinance .info
            info   = _ticker_info(ticker)
            sector = info.get("sector")
            p_e    = _safe_float(info.get("trailingPE"), 1)
            eps    = _safe_float(info.get("trailingEps"), 2)
            beta   = _safe_float(info.get("beta"), 2)

            eps_note, beta_note, sector_display = _etf_display_fields(info, eps, beta, sector)
            if sector_display:
                sector = sector_display

            prediction, confidence = predict_stock(ticker)

            list_data.append({
                "ticker":        ticker,
                "price":         current_price,
                "change":        change,
                "pct_change":    pct_change,
                "volume":        volume,
                "week_52_high":  week_52_high,
                "week_52_low":   week_52_low,
                "p_e":           p_e,
                "eps":           eps,
                "eps_note":      eps_note,
                "rsi":           rsi,
                "bollinger_pos": bollinger_pos,
                "volatility":    volatility,
                "macd":          macd,
                "beta":          beta,
                "beta_note":     beta_note,
                "sector":        sector,
                "direction":     int(prediction[0]),
                "confidence":    round(float(confidence[0].max()) * 100, 2),
                "updated_at":    datetime.now().strftime("%-I:%M %p"),
            })

        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            continue

    _cache["data"]        = list_data
    _cache["updated_at"]  = datetime.now()
    _cache["tickers_key"] = key
    return list_data

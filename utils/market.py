# utils/market.py — market data fetching and caching layer
#
# Batch-downloads yfinance data, computes indicators, runs ML predictions.
# Per-ticker cache (60s TTL) so different users can share cached rows.

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

from utils.features import compute_features
from utils.predict import predict_stock

_cache = {"rows": {}, "updated_at": {}}
_CACHE_TTL = timedelta(seconds=60)


def clear_cache(tickers=None):
    """
    Drop cached rows. If tickers is None, clear everything.
    Otherwise invalidate only the given symbols (after watchlist edits).
    """
    if tickers is None:
        _cache["rows"].clear()
        _cache["updated_at"].clear()
        return

    for ticker in tickers:
        _cache["rows"].pop(ticker, None)
        _cache["updated_at"].pop(ticker, None)


def _slice_ticker(df, ticker):
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        return df[ticker].copy()
    return df.copy()


def _safe_float(val, digits=2):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return None


_ETF_NA = "N/A"


def _etf_display_fields(info, eps, beta, sector):
    quote_type = (info.get("quoteType") or "").upper()
    if quote_type != "ETF":
        return None, None, sector or None

    category = info.get("category")
    eps_note = _ETF_NA if eps is None else None
    beta_note = _ETF_NA if beta is None else None
    sector_display = sector or category or None
    return eps_note, beta_note, sector_display


def _ticker_info(ticker):
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


def _build_row(ticker, ticker_daily, ticker_intraday, ticker_year):
    prev_close = ticker_daily["Close"].iloc[-2]

    if ticker_intraday is None or ticker_intraday.empty:
        current_price = ticker_daily["Close"].iloc[-1]
        volume = 0
    else:
        current_price = ticker_intraday["Close"].iloc[-1]
        volume = int(ticker_intraday["Volume"].sum())

    change = current_price - prev_close
    pct_change = round((change / prev_close) * 100, 2)

    week_52_high = week_52_low = None
    if ticker_year is not None and not ticker_year.empty:
        week_52_high = _safe_float(ticker_year["High"].max())
        week_52_low = _safe_float(ticker_year["Low"].min())

    rsi = bollinger_pos = volatility = macd = None
    if ticker_year is not None and len(ticker_year) >= 30:
        features = compute_features(ticker_year)
        last = features.iloc[-1]
        rsi = _safe_float(last["rsi"], 1)
        bollinger_pos = _safe_float(last["bollinger_bands_position"], 2)
        volatility = _safe_float(last["volatility"], 4)
        macd = _safe_float(last["macd"], 2)

    info = _ticker_info(ticker)
    sector = info.get("sector")
    p_e = _safe_float(info.get("trailingPE"), 1)
    eps = _safe_float(info.get("trailingEps"), 2)
    beta = _safe_float(info.get("beta"), 2)

    eps_note, beta_note, sector_display = _etf_display_fields(info, eps, beta, sector)
    if sector_display:
        sector = sector_display

    prediction, confidence = predict_stock(ticker)

    return {
        "ticker": ticker,
        "price": current_price,
        "change": change,
        "pct_change": pct_change,
        "volume": volume,
        "week_52_high": week_52_high,
        "week_52_low": week_52_low,
        "p_e": p_e,
        "eps": eps,
        "eps_note": eps_note,
        "rsi": rsi,
        "bollinger_pos": bollinger_pos,
        "volatility": volatility,
        "macd": macd,
        "beta": beta,
        "beta_note": beta_note,
        "sector": sector,
        "direction": int(prediction[0]),
        "confidence": round(float(confidence[0].max()) * 100, 2),
        "updated_at": datetime.now().strftime("%-I:%M %p"),
    }


def _fetch_tickers_batch(tickers):
    """Download and build rows for a list of tickers (no cache read)."""
    if not tickers:
        return []

    daily_df = yf.download(tickers, period="2d", interval="1d", group_by="ticker", auto_adjust=True)
    intraday_df = yf.download(tickers, period="1d", interval="1m", group_by="ticker", auto_adjust=True)
    year_df = yf.download(tickers, period="1y", interval="1d", group_by="ticker", auto_adjust=True)

    list_data = []
    for ticker in tickers:
        try:
            row = _build_row(
                ticker,
                _slice_ticker(daily_df, ticker),
                _slice_ticker(intraday_df, ticker),
                _slice_ticker(year_df, ticker),
            )
            list_data.append(row)
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")

    return list_data


def fetch_market_data(tickers):
    """
    Return market rows for tickers, using per-ticker cache when fresh.
    Only stale or missing symbols hit yfinance.
    """
    if not tickers:
        return []

    now = datetime.now()
    need_fetch = []

    for ticker in tickers:
        updated = _cache["updated_at"].get(ticker)
        if ticker in _cache["rows"] and updated and (now - updated) < _CACHE_TTL:
            continue
        need_fetch.append(ticker)

    if need_fetch:
        for row in _fetch_tickers_batch(need_fetch):
            sym = row["ticker"]
            _cache["rows"][sym] = row
            _cache["updated_at"][sym] = now

    return [_cache["rows"][t] for t in tickers if t in _cache["rows"]]

# utils/market.py — market data fetching and caching layer
#
# Batch-downloads yfinance data, computes indicators, runs ML predictions.
# Per-ticker cache (60s TTL) so different users can share cached rows.

import logging
import os
import threading
import time
import traceback

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

from utils.yfinance_setup import configure_yfinance

configure_yfinance()

from utils.features import compute_features
from utils.predict import predict_stock

logger = logging.getLogger(__name__)

_cache = {"rows": {}, "updated_at": {}}
_CACHE_TTL = timedelta(seconds=60)

# Render shares egress IPs — Yahoo rate-limits aggressively; pace serially.
_HOSTED = bool(os.environ.get("RENDER") or os.environ.get("DATABASE_PATH", "").startswith("/data/"))
_YF_BATCH_SIZE = 1 if _HOSTED else 5
_YF_PAUSE_SEC = 2.5 if _HOSTED else 0.75
_YF_RATE_LIMIT_PAUSE = 15.0 if _HOSTED else 8.0
_SKIP_INTRADAY = _HOSTED
_info_cache = {}
_INFO_CACHE_TTL = timedelta(minutes=30)
_INFO_FAIL_TTL = timedelta(minutes=5 if _HOSTED else 2)

_fetch_lock = threading.Lock()
_rate_limited_until = 0.0


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
    """
    Pull one ticker's slice out of a yfinance download DataFrame.

    yfinance uses different MultiIndex structures depending on context:
      - batch download (group_by="ticker"): columns are (ticker, field) → ticker at level 0
      - single-ticker download in yfinance 1.4.x: columns are (field, ticker) → ticker at level 1

    We try level 0 first (covers the common batch case), then fall back to level 1.
    """
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        if ticker in df.columns.get_level_values(0):
            sliced = df.xs(ticker, axis=1, level=0)
        elif ticker in df.columns.get_level_values(1):
            sliced = df.xs(ticker, axis=1, level=1)
        else:
            return None
        return None if sliced.dropna(how="all").empty else sliced.copy()
    # Flat columns — single-ticker download that returned a plain DataFrame
    return None if df.dropna(how="all").empty else df.copy()


def _format_clock_time(when=None):
    when = when or datetime.now()
    try:
        return when.strftime("%-I:%M %p")
    except ValueError:
        return when.strftime("%I:%M %p").lstrip("0")


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


def _in_rate_limit_cooldown():
    return time.time() < _rate_limited_until


def _set_rate_limit_cooldown(seconds=None):
    global _rate_limited_until
    pause = seconds if seconds is not None else _YF_RATE_LIMIT_PAUSE * 2
    _rate_limited_until = time.time() + pause
    logger.warning("yfinance cooldown for %.0fs", pause)


def _ticker_info(ticker):
    """Fetch fundamentals with cache, pause, and retry — Yahoo rate-limits .info on Render."""
    if _in_rate_limit_cooldown():
        cached = _info_cache.get(ticker)
        return (cached or {}).get("info") or {}

    now = datetime.now()
    cached = _info_cache.get(ticker)
    if cached:
        age = now - cached["at"]
        if cached.get("info") and age < _INFO_CACHE_TTL:
            return cached["info"]
        if not cached.get("info") and age < _INFO_FAIL_TTL:
            return {}

    info = {}
    max_attempts = 2 if _HOSTED else 3
    for attempt in range(max_attempts):
        try:
            if attempt:
                time.sleep(_YF_RATE_LIMIT_PAUSE)
            else:
                _yf_pause(1.0 if _HOSTED else 0.5)
            fetched = yf.Ticker(ticker).info or {}
            if fetched:
                info = fetched
                break
        except Exception as exc:
            logger.warning("ticker info failed for %s (attempt %d): %s", ticker, attempt + 1, exc)
            if _is_rate_limited(exc):
                _set_rate_limit_cooldown()
                break

    _info_cache[ticker] = {"info": info, "at": now}
    return info


def _yf_pause(seconds=None):
    time.sleep(seconds if seconds is not None else _YF_PAUSE_SEC)


def _is_rate_limited(exc):
    msg = str(exc).lower()
    return "rate" in msg or "too many" in msg or "429" in msg


def _yf_download(tickers, **kwargs):
    """yf.download with pacing, no parallel threads, and backoff on rate limits."""
    kwargs.setdefault("threads", False)
    last_exc = None
    for attempt in range(2):
        try:
            result = yf.download(tickers, progress=False, **kwargs)
            if isinstance(tickers, str):
                empty = result is None or result.empty
            else:
                empty = result is None or result.empty
            if empty and attempt == 0:
                _set_rate_limit_cooldown()
                time.sleep(_YF_RATE_LIMIT_PAUSE)
                continue
            _yf_pause()
            return result
        except Exception as exc:
            last_exc = exc
            if _is_rate_limited(exc):
                _set_rate_limit_cooldown()
                if attempt == 0:
                    time.sleep(_YF_RATE_LIMIT_PAUSE)
                    continue
            raise
    if last_exc:
        raise last_exc
    return pd.DataFrame()


def _build_row(ticker, ticker_daily, ticker_intraday, ticker_year):
    def _scalar(val):
        """Ensure a value extracted from a DataFrame is a plain Python scalar."""
        if hasattr(val, "iloc"):
            val = val.iloc[0]
        if hasattr(val, "item"):
            return val.item()
        return float(val)

    # Use previous close from daily history; fall back to yfinance info when
    # only one trading day is available (Mondays, post-holiday, etc.)
    info = None
    if ticker_daily is not None and len(ticker_daily) >= 2:
        prev_close = _scalar(ticker_daily["Close"].iloc[-2])
    else:
        info = _ticker_info(ticker)
        prev_close_val = info.get("regularMarketPreviousClose")
        if prev_close_val is None:
            raise ValueError(f"No previous close available for {ticker}")
        prev_close = float(prev_close_val)

    if ticker_intraday is None or ticker_intraday.empty:
        if ticker_daily is None or ticker_daily.empty:
            raise ValueError(f"No price data for {ticker}")
        current_price = _scalar(ticker_daily["Close"].iloc[-1])
        volume = 0
    else:
        current_price = _scalar(ticker_intraday["Close"].iloc[-1])
        vol_sum = ticker_intraday["Volume"].sum()
        volume = int(vol_sum.iloc[0] if hasattr(vol_sum, "iloc") else vol_sum)

    change = round(current_price - prev_close, 2)
    pct_change = round((change / prev_close) * 100, 2) if prev_close else 0.0

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

    if info is None:
        info = _ticker_info(ticker)
    quote_type = (info.get("quoteType") or "EQUITY").upper()
    sector = info.get("sector") or info.get("industry")
    p_e = _safe_float(info.get("trailingPE") or info.get("forwardPE"), 1)
    eps = _safe_float(info.get("trailingEps") or info.get("epsTrailingTwelveMonths"), 2)
    beta = _safe_float(info.get("beta"), 2)

    eps_note, beta_note, sector_display = _etf_display_fields(info, eps, beta, sector)
    if sector_display:
        sector = sector_display

    prediction, confidence = predict_stock(ticker, history_df=ticker_year)

    return {
        "ticker": ticker,
        "quote_type": quote_type,
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
        "updated_at": _format_clock_time(),
    }


def _download_single(ticker):
    """
    Download timeframes for one ticker (crumb-safe fallback).
    On hosted deploys skip 1m intraday — daily close is enough and saves API calls.
    """
    daily = _slice_ticker(_yf_download(ticker, period="5d", interval="1d", auto_adjust=True), ticker)
    if daily is None or daily.empty:
        _set_rate_limit_cooldown()
        raise ValueError(f"No daily data for {ticker}")
    year = _slice_ticker(_yf_download(ticker, period="1y", interval="1d", auto_adjust=True), ticker)
    intraday = None
    if not _SKIP_INTRADAY:
        intraday = _slice_ticker(_yf_download(ticker, period="1d", interval="1m", auto_adjust=True), ticker)
    return daily, intraday, year


def _fetch_one_ticker(ticker):
    """Serial fetch for one symbol — primary path on Render."""
    if _in_rate_limit_cooldown():
        return None
    try:
        daily, intraday, year = _download_single(ticker)
        return _build_row(ticker, daily, intraday, year)
    except Exception:
        logger.error("Failed to fetch %s:\n%s", ticker, traceback.format_exc())
        return None


def _fetch_tickers_chunk(tickers):
    """Batch-download a small chunk of tickers then build rows."""
    if not tickers:
        return []

    if _HOSTED:
        rows = []
        for ticker in tickers:
            if _in_rate_limit_cooldown():
                break
            row = _fetch_one_ticker(ticker)
            if row:
                rows.append(row)
        return rows

    daily_df    = _yf_download(tickers, period="5d", interval="1d", group_by="ticker", auto_adjust=True)
    intraday_df = _yf_download(tickers, period="1d", interval="1m", group_by="ticker", auto_adjust=True)
    year_df     = _yf_download(tickers, period="1y", interval="1d", group_by="ticker", auto_adjust=True)

    list_data = []
    for ticker in tickers:
        daily    = _slice_ticker(daily_df, ticker)
        intraday = _slice_ticker(intraday_df, ticker)
        year     = _slice_ticker(year_df, ticker)

        if daily is None or daily.empty:
            logger.warning("Batch returned no data for %s — retrying individually", ticker)
            time.sleep(_YF_RATE_LIMIT_PAUSE)
            try:
                daily, intraday, year = _download_single(ticker)
            except Exception:
                logger.error("Individual retry also failed for %s:\n%s", ticker, traceback.format_exc())
                continue

        try:
            row = _build_row(ticker, daily, intraday, year)
            list_data.append(row)
        except Exception:
            logger.error("Error building row for %s:\n%s", ticker, traceback.format_exc())

    return list_data


def _fetch_tickers_batch(tickers):
    """Batch-download tickers in small chunks to avoid Yahoo rate limits."""
    if not tickers:
        return []

    list_data = []
    for i in range(0, len(tickers), _YF_BATCH_SIZE):
        chunk = tickers[i : i + _YF_BATCH_SIZE]
        list_data.extend(_fetch_tickers_chunk(chunk))
        if i + _YF_BATCH_SIZE < len(tickers):
            _yf_pause()
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
        with _fetch_lock:
            if _in_rate_limit_cooldown():
                logger.info("yfinance cooldown — serving cached data for %d stale tickers", len(need_fetch))
            else:
                still_need = []
                now_locked = datetime.now()
                for ticker in need_fetch:
                    updated = _cache["updated_at"].get(ticker)
                    if ticker in _cache["rows"] and updated and (now_locked - updated) < _CACHE_TTL:
                        continue
                    still_need.append(ticker)
                for row in _fetch_tickers_batch(still_need):
                    sym = row["ticker"]
                    _cache["rows"][sym] = row
                    _cache["updated_at"][sym] = now_locked

    return [_cache["rows"][t] for t in tickers if t in _cache["rows"]]

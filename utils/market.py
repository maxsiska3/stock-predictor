# utils/market.py — market data fetching and caching layer
#
# Batch-downloads yfinance data, computes indicators, runs ML predictions.
# Per-ticker cache (60s TTL) so different users can share cached rows.
#
# Two independent caches:
#   - price rows  (price/volume/technicals) — short TTL, refreshed every cycle
#   - fundamentals (.info: sector/P-E/EPS/beta) — long TTL, rarely change
# This matters because `.info` is the slowest, most rate-limit-prone yfinance
# call. Caching it for hours instead of seconds is what keeps the dashboard
# both fast and populated once warmed up.

import logging
import threading
import time
import traceback

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

from utils.yfinance_setup import configure_yfinance, get_yf_session

configure_yfinance()
_SESSION = get_yf_session()

from utils.features import compute_features
from utils.predict import predict_stock

logger = logging.getLogger(__name__)

_cache = {"rows": {}, "updated_at": {}}
_CACHE_TTL = timedelta(seconds=90)

_info_cache = {}
_INFO_CACHE_TTL = timedelta(hours=4)
_INFO_FAIL_TTL = timedelta(minutes=2)

_YF_PAUSE_SEC = 0.4
_RATE_LIMIT_BACKOFF_SEC = 12.0

_fetch_lock = threading.Lock()
_price_cooldown_until = 0.0
_info_cooldown_until = 0.0


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


def _is_rate_limited(exc):
    msg = str(exc).lower()
    return "rate" in msg or "too many" in msg or "429" in msg


def _in_cooldown(which):
    return time.time() < (_price_cooldown_until if which == "price" else _info_cooldown_until)


def _set_cooldown(which, seconds=_RATE_LIMIT_BACKOFF_SEC):
    global _price_cooldown_until, _info_cooldown_until
    until = time.time() + seconds
    if which == "price":
        _price_cooldown_until = until
    else:
        _info_cooldown_until = until
    logger.warning("yfinance %s cooldown for %.0fs", which, seconds)


def _ticker_info(ticker):
    """Fundamentals (.info) — cached for hours since sector/P-E/EPS/beta rarely change."""
    now = datetime.now()
    cached = _info_cache.get(ticker)
    if cached:
        age = now - cached["at"]
        if cached.get("info") and age < _INFO_CACHE_TTL:
            return cached["info"]
        if not cached.get("info") and age < _INFO_FAIL_TTL:
            return {}

    if _in_cooldown("info"):
        return (cached or {}).get("info") or {}

    info = {}
    for attempt in range(2):
        try:
            time.sleep(_YF_PAUSE_SEC if attempt == 0 else _RATE_LIMIT_BACKOFF_SEC)
            info = yf.Ticker(ticker, session=_SESSION).info or {}
            if info:
                break
        except Exception as exc:
            logger.warning("ticker info failed for %s (attempt %d): %s: %s", ticker, attempt + 1, type(exc).__name__, exc)
            if _is_rate_limited(exc):
                _set_cooldown("info")
                break

    _info_cache[ticker] = {"info": info, "at": now}
    return info


def _yf_download(tickers, **kwargs):
    """yf.download via the impersonated session, with one backoff retry on rate limits."""
    kwargs.setdefault("threads", False)
    kwargs.setdefault("session", _SESSION)
    multi = not isinstance(tickers, str) and len(tickers) > 1

    for attempt in range(2):
        try:
            result = yf.download(tickers, progress=False, **kwargs)
            if (result is None or result.empty) and not multi and attempt == 0:
                # Single ticker came back empty — could be a genuine throttle.
                time.sleep(_RATE_LIMIT_BACKOFF_SEC)
                continue
            return result
        except Exception as exc:
            if _is_rate_limited(exc):
                _set_cooldown("price")
                if attempt == 0:
                    time.sleep(_RATE_LIMIT_BACKOFF_SEC)
                    continue
            raise
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
    """Download all timeframes for one ticker individually (fallback for batch misses)."""
    daily = _slice_ticker(_yf_download(ticker, period="5d", interval="1d", auto_adjust=True), ticker)
    time.sleep(_YF_PAUSE_SEC)
    intraday = _slice_ticker(_yf_download(ticker, period="1d", interval="1m", auto_adjust=True), ticker)
    time.sleep(_YF_PAUSE_SEC)
    year = _slice_ticker(_yf_download(ticker, period="1y", interval="1d", auto_adjust=True), ticker)
    return daily, intraday, year


def _fetch_tickers_batch(tickers):
    """
    Batch-download all tickers in three calls total (daily/intraday/year), then
    build rows. Tickers missing from the batch (bad symbol, mid-download hiccup)
    are retried individually so one bad apple doesn't drop the rest of the list.
    """
    if not tickers:
        return []

    if _in_cooldown("price"):
        logger.info("price cooldown active — skipping fetch for %d tickers", len(tickers))
        return []

    daily_df    = _yf_download(tickers, period="5d", interval="1d", group_by="ticker", auto_adjust=True)
    intraday_df = _yf_download(tickers, period="1d", interval="1m", group_by="ticker", auto_adjust=True)
    year_df     = _yf_download(tickers, period="1y", interval="1d", group_by="ticker", auto_adjust=True)

    list_data = []
    for ticker in tickers:
        daily    = _slice_ticker(daily_df, ticker)
        intraday = _slice_ticker(intraday_df, ticker)
        year     = _slice_ticker(year_df, ticker)

        if daily is None or daily.empty:
            if _in_cooldown("price"):
                continue
            logger.warning("Batch returned no data for %s — retrying individually", ticker)
            time.sleep(_YF_PAUSE_SEC)
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


def _refresh_tickers(tickers):
    """Fetch + cache the given tickers. Caller must hold _fetch_lock."""
    now = datetime.now()
    for row in _fetch_tickers_batch(tickers):
        sym = row["ticker"]
        _cache["rows"][sym] = row
        _cache["updated_at"][sym] = now


def fetch_market_data(tickers, wait=True):
    """
    Return market rows for tickers, using per-ticker cache when fresh.

    wait=True (background refresh thread): blocks until fresh data is fetched.
    wait=False (web request path): never blocks the request on yfinance latency.
    Acquires the lock only if free; otherwise serves whatever is cached (even if
    a little stale) so page loads stay fast regardless of yfinance conditions.
    """
    if not tickers:
        return []

    now = datetime.now()
    need_fetch = [
        t for t in tickers
        if not (t in _cache["rows"] and _cache["updated_at"].get(t) and (now - _cache["updated_at"][t]) < _CACHE_TTL)
    ]

    if need_fetch:
        if wait:
            with _fetch_lock:
                still_need = [
                    t for t in need_fetch
                    if not (t in _cache["rows"] and _cache["updated_at"].get(t) and (datetime.now() - _cache["updated_at"][t]) < _CACHE_TTL)
                ]
                _refresh_tickers(still_need)
        else:
            # Only the tickers with NO cached row at all are worth a quick blocking
            # fetch (e.g. user just added a ticker) — anything merely stale can
            # wait for the background thread rather than slow down the request.
            brand_new = [t for t in need_fetch if t not in _cache["rows"]]
            if brand_new and _fetch_lock.acquire(blocking=False):
                try:
                    _refresh_tickers(brand_new)
                finally:
                    _fetch_lock.release()

    return [_cache["rows"][t] for t in tickers if t in _cache["rows"]]

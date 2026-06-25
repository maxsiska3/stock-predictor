# utils/market.py — market data fetching and caching layer
# All yfinance interaction lives here so app.py stays focused on routing.

import yfinance as yf
from datetime import datetime, timedelta
from utils.predict import predict_stock

# Module-level cache — persists between requests for the lifetime of the server process.
# Storing it here (not in app.py) means both the "/" route and "/api/market-data"
# share the same cached result without double-fetching.
_cache = {"data": None, "updated_at": None}


def fetch_market_data(tickers):
    """
    Fetch live price, change, volume, and ML prediction for each ticker.
    Returns a list of dicts, one per ticker.
    Results are cached for 60 seconds to avoid hammering the yfinance rate limit.
    """

    # Return cached data if it's less than 60 seconds old
    if _cache["data"] is not None and _cache["updated_at"] is not None:
        age = datetime.now() - _cache["updated_at"]
        if age < timedelta(seconds=60):
            return _cache["data"]

    # One batch call for 2 days of daily OHLCV — gives us yesterday's close for change calculation
    daily_df = yf.download(tickers, period="2d", interval="1d", group_by="ticker", auto_adjust=True)

    # One batch call for today's 1-minute bars — gives us the live current price and intraday volume
    intraday_df = yf.download(tickers, period="1d", interval="1m", group_by="ticker", auto_adjust=True)

    list_data = []

    for ticker in tickers:
        try:
            # Slice this ticker's rows out of the multi-ticker DataFrames
            ticker_daily    = daily_df[ticker]
            ticker_intraday = intraday_df[ticker]

            # Yesterday's closing price — used as the baseline for change calculation
            prev_close = ticker_daily["Close"].iloc[-2]

            # Most recent intraday price (≈1 min lag). Fall back to daily close
            # outside market hours when intraday data is unavailable.
            if ticker_intraday.empty:
                current_price = ticker_daily["Close"].iloc[-1]
            else:
                current_price = ticker_intraday["Close"].iloc[-1]

            # Dollar change vs yesterday's close, percent change, and cumulative volume today
            change     = current_price - prev_close
            pct_change = round((change / prev_close) * 100, 2)
            volume     = int(ticker_intraday["Volume"].sum())

            # Run the trained RandomForest model to get tomorrow's direction + confidence
            prediction, confidence = predict_stock(ticker)

            list_data.append({
                "ticker":     ticker,
                "price":      current_price,
                "change":     change,        # float, can be negative
                "pct_change": pct_change,    # float, can be negative
                "volume":     volume,
                "52_week_high": ticker_daily["52 Week High"],
                "52_week_low": ticker_daily["52 Week Low"],
                "p_e": ticker_daily["P/E"],
                "eps": ticker_daily["EPS"],
                "bollinger_pos": ticker_daily["Bollinger Pos"],
                "volatility": ticker_daily["Volatility"],
                "macd": ticker_daily["MACD"],
                "sector": ticker_daily["Sector"],
                "direction":  prediction,    # int: 1 = predicted up, 0 = predicted down
                "confidence": round(float(confidence[0].max()) * 100, 2),  # e.g. 72.0
                "updated_at": datetime.now().strftime("%-I:%M %p"),
            })

        except Exception as e:
            # Skip failed tickers rather than crashing the whole fetch
            print(f"Error fetching {ticker}: {e}")
            continue

    # Save to cache so the next request within 60s skips the download
    _cache["data"]       = list_data
    _cache["updated_at"] = datetime.now()
    return list_data

# =============================================================================
# SUMMARY — utils/market.py
# =============================================================================
# This module is the data layer for Siska Terminal. It owns all yfinance
# interaction and shields the rest of the app from API details.
#
# Key design decisions:
#   - Two batch downloads per refresh cycle (daily + 1m intraday) instead of
#     N per-ticker calls, to stay within yfinance's free-tier rate limits.
#   - Module-level _cache dict survives between HTTP requests (Flask reuses the
#     process), so both the page load and the /api/market-data poll share data.
#   - 60-second TTL balances freshness with rate-limit safety.
#   - try/except per ticker means one bad ticker (delisted, bad symbol, etc.)
#     doesn't wipe out the rest of the watchlist.
#
# Data flow:
#   fetch_market_data(tickers)
#     → check _cache (return early if < 60s old)
#     → yf.download() × 2  (daily, intraday)
#     → loop tickers: slice df, compute stats, run predict_stock()
#     → store in _cache, return list of dicts
# =============================================================================

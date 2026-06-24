import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from utils.predict import predict_stock

_cache = {"data": None, "updated_at": None}


def fetch_market_data(tickers):

    # 1. Check cache — return early if fresh
    if _cache["data"] is not None and _cache["updated_at"] is not None:
        age = datetime.now() - _cache["updated_at"]
        if age < timedelta(seconds=60):
            return _cache["data"]

    # 2. Batch download daily data (for yesterday's close + ML features)
    daily_df = yf.download(tickers, period="2d", interval="1d", group_by="ticker", auto_adjust=True)

    # 3. Batch download intraday data (for live current price + today's volume)
    intraday_df = yf.download(tickers, period="1d", interval="1m", group_by="ticker", auto_adjust=True)

    list_data = []

    for ticker in tickers:
        try:
            # 4. Slice this ticker's daily and intraday DataFrames
            ticker_daily = daily_df[ticker]
            ticker_intraday = intraday_df[ticker]

            # 5. Get yesterday's close from daily data (iloc[-2])
            prev_close = ticker_daily["Close"].iloc[-2]

            # 6. Get current live price from intraday data (iloc[-1])
            #    Fallback to daily close if intraday is empty
            if ticker_intraday.empty:
                current_price = ticker_daily["Close"].iloc[-1]
            else:
                current_price = ticker_intraday["Close"].iloc[-1]

            # 7. Compute dollar change, percent change, and today's total volume
            change = current_price - prev_close
            pct_change = round((change/prev_close) * 100, 2)
            volume = int(ticker_intraday["Volume"].sum())

            # 8. Run the ML prediction
            prediction, confidence = predict_stock(ticker)

            # 9. Build the ticker dict and append to list_data
            list_data.append({
                "ticker": ticker,
                "price": current_price,
                "change": change,
                "pct_change": pct_change,
                "volume": volume,
                "direction": prediction,   # 0 or 1
                "confidence": round(float(confidence[0].max()) * 100, 2),  # e.g. 0.72
            })

        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            continue

    # 10. Store result in cache and return
    _cache["data"] = list_data
    _cache["updated_at"] = datetime.now()
    return list_data

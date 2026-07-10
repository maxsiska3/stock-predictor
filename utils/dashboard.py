import time
from datetime import date, timedelta

import numpy as np
import yfinance as yf
import pandas as pd

from utils.predict import MIN_HISTORY_ROWS, predict_stock, scaler, trained_model
from utils.yfinance_setup import configure_yfinance, get_yf_session, reset_yf_session
from utils.features import compute_features, FEATURE_COLS
from utils.watchlist import DEFAULT_WATCHLIST

configure_yfinance()

# predict_proba columns follow trained_model.classes_ order; find where class 1 (up) lives
_UP_CLASS_IDX = list(trained_model.classes_).index(1)


def _flatten_download(df):
    raw_df = pd.DataFrame(df)
    if isinstance(raw_df.columns, pd.MultiIndex):
        raw_df.columns = raw_df.columns.get_level_values(0)
    return raw_df


def download_ohlcv(ticker, _retry=True):
    """Download ~6 months OHLCV once. Returns cleaned DataFrame or None.

    Retries once with a fresh session on failure — see reset_yf_session() for why.
    """
    try:
        session = get_yf_session()
        start = pd.Timestamp.now() - pd.DateOffset(months=6)
        raw_df = _flatten_download(
            yf.download(ticker, start=start, progress=False, session=session, threads=False)
        )
        if raw_df.empty:
            raise ValueError("empty download")
        cleaned = raw_df.dropna(subset=["Open", "High", "Low", "Close"])
        if len(cleaned) < MIN_HISTORY_ROWS:
            raise ValueError(f"insufficient history: need {MIN_HISTORY_ROWS} rows, got {len(cleaned)}")
        return cleaned
    except Exception:
        if _retry:
            reset_yf_session()
            return download_ohlcv(ticker, _retry=False)
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


def fetch_sector(ticker: str, _retry=True) -> str:
    try:
        session = get_yf_session()
        stock = yf.Ticker(ticker, session=session) if session else yf.Ticker(ticker)
        info = stock.info or {}
        if not info and _retry:
            reset_yf_session()
            return fetch_sector(ticker, _retry=False)

        sector = info.get("sector")
        if isinstance(sector, str) and sector.strip():
            return sector.strip()

        industry = info.get("industry")
        if isinstance(industry, str) and industry.strip():
            return industry.strip()

        return "Unknown"
    except Exception:
        if _retry:
            reset_yf_session()
            return fetch_sector(ticker, _retry=False)
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


_UI_COLS = [
    ("rsi", "rsi", lambda v: round(float(v), 1)),
    ("macd", "macd", lambda v: round(float(v), 2)),
    ("bollinger", "bollinger_bands_position", lambda v: round(float(v), 2)),
    ("volatility", "volatility", lambda v: round(float(v) * (252 ** 0.5) * 100, 1)),
    ("volume_change", "volume_change", lambda v: round(float(v) * 100, 1)),
]


def fetch_features_and_trends(raw_df):
    """Return (features, trends) dicts for the dashboard UI."""
    if raw_df is None or raw_df.empty:
        return None, None
    try:
        df = compute_features(raw_df)
        source_cols = [src for _, src, _ in _UI_COLS]
        tail = df[source_cols].tail(7)
        last = df.iloc[-1]
        if any(not np.isfinite(last[src]) for _, src, _ in _UI_COLS):
            return None, None

        features = {}
        trends = {}
        for json_key, src_col, fmt in _UI_COLS:
            features[json_key] = fmt(last[src_col])
            trends[json_key] = [fmt(v) for v in tail[src_col].tolist()]
        return features, trends
    except Exception:
        return None, None


def backtest_predictions(raw_df, days=60):
    """Walk-forward accuracy check for the frozen model, not a retrain.

    For each historical day, run the same saved scaler/model on features computed
    only from data through that day, then compare the call to the next day's real
    move. Nothing here looks ahead: row i's prediction only used rows <= i, and its
    label comes from row i+1, which is dropped so it's never used as its own input.
    """
    if raw_df is None or raw_df.empty:
        return None
    try:
        feats = compute_features(raw_df).dropna(subset=FEATURE_COLS)
        if len(feats) < 2:
            return None

        next_close_pct = (feats["Close"].shift(-1) / feats["Close"] - 1).iloc[:-1]
        actual_up = next_close_pct > 0
        feats = feats.iloc[:-1]

        feats = feats.tail(days)
        actual_up = actual_up.tail(days)
        next_close_pct = next_close_pct.tail(days)

        scaled = scaler.transform(feats[FEATURE_COLS])
        predictions = trained_model.predict(scaled)
        probs = trained_model.predict_proba(scaled)

        results = []
        for i, ts in enumerate(feats.index):
            predicted_up = bool(predictions[i])
            actual_up_i = bool(actual_up.iloc[i])
            results.append({
                "date": ts.date().isoformat(),
                "call": "up" if predicted_up else "down",
                "confidence": round(float(probs[i].max()) * 100, 1),
                "hit": predicted_up == actual_up_i,
                "move": round(abs(float(next_close_pct.iloc[i])) * 100, 2),
                "actual_up": actual_up_i,
                "proba_up": float(probs[i][_UP_CLASS_IDX]),
            })
        return results
    except Exception:
        return None


def fetch_performance(raw_df, days=60):
    """Return (last5, stock_hit_rate) from a walk-forward backtest, or (None, None).

    stock_hit_rate.history carries all `days` results (hit + move size) so the UI
    can render a real per-ticker track record strip instead of a placeholder.
    """
    results = backtest_predictions(raw_df, days=days)
    if not results:
        return None, None

    hits = sum(r["hit"] for r in results)
    stock_hit_rate = {
        "rate": round(hits / len(results) * 100, 1),
        "calls": len(results),
        "history": [{"hit": r["hit"], "move": r["move"]} for r in results],
    }
    last5 = [
        {k: r[k] for k in ("date", "call", "confidence", "hit")}
        for r in results[-5:]
    ]
    return last5, stock_hit_rate


_cache = {}


def _cached(key, ttl, compute_fn):
    """Tiny in-memory TTL cache so watchlist-wide scans don't re-hit yfinance
    on every page load. Failures aren't cached, so a bad run gets retried next request."""
    entry = _cache.get(key)
    now = time.time()
    if entry and now - entry["ts"] < ttl:
        return entry["value"]
    value = compute_fn()
    if value:
        _cache[key] = {"value": value, "ts": now}
    return value


def _fetch_index_predictions(index_defs):
    out = []
    for symbol, name in index_defs:
        raw_df = download_ohlcv(symbol)
        if raw_df is None:
            continue
        direction, confidence = fetch_prediction(symbol, history_df=raw_df)
        if direction is None:
            continue
        out.append({
            "symbol": symbol,
            "name": name,
            "direction": direction,
            "confidence": confidence,
        })
    return out


def get_index_predictions(index_defs, ttl=900):
    """Real up/down calls for the header marquee, cached for `ttl` seconds."""
    return _cached("indices", ttl, lambda: _fetch_index_predictions(index_defs))


_CONFIDENCE_BANDS = [(50, 55), (55, 60), (60, 65), (65, 1000)]


def _compute_market_stats(tickers, days=90):
    pooled = []
    sector_calls = []
    stock_rows = []
    bullish = 0
    tracked = 0

    for i, ticker in enumerate(tickers):
        if i > 0:
            time.sleep(0.2)  # pace requests so Yahoo doesn't flag the session as a scraper

        raw_df = download_ohlcv(ticker)
        if raw_df is None:
            continue

        results = backtest_predictions(raw_df, days=days) or []
        pooled.extend(results)
        if results:
            hits = sum(r["hit"] for r in results)
            stock_rows.append({
                "ticker": ticker,
                "calls": len(results),
                "rate": round(hits / len(results) * 100, 1),
            })

        direction, _confidence = fetch_prediction(ticker, history_df=raw_df)
        if direction is None:
            continue
        tracked += 1
        if direction == "up":
            bullish += 1
        sector_calls.append((fetch_sector(ticker), direction == "up"))

    if not pooled or tracked == 0:
        return None

    today_iso = date.today().isoformat()
    hit_rate_windows = {}
    for window in (30, 60, 90):
        cutoff = (date.today() - timedelta(days=window)).isoformat()
        subset = [r for r in pooled if r["date"] >= cutoff]
        hit_rate_windows[str(window)] = (
            round(sum(r["hit"] for r in subset) / len(subset) * 100, 1) if subset else None
        )

    brier_score = round(
        sum((r["proba_up"] - (1 if r["actual_up"] else 0)) ** 2 for r in pooled) / len(pooled), 3
    )

    confidence_bands = []
    for lo, hi in _CONFIDENCE_BANDS:
        bucket = [r for r in pooled if lo <= r["confidence"] < hi]
        confidence_bands.append({
            "label": f"{lo}-{hi}" if hi < 100 else f"{lo}+",
            "rate": round(sum(r["hit"] for r in bucket) / len(bucket) * 100, 1) if bucket else None,
            "count": len(bucket),
        })

    sector_totals = {}
    for sector, is_up in sector_calls:
        totals = sector_totals.setdefault(sector, {"up": 0, "total": 0})
        totals["total"] += 1
        if is_up:
            totals["up"] += 1
    sectors = sorted(
        (
            {"name": name, "pct_bullish": round(v["up"] / v["total"] * 100, 1), "count": v["total"]}
            for name, v in sector_totals.items()
        ),
        key=lambda s: s["count"],
        reverse=True,
    )

    stock_rows.sort(key=lambda s: s["calls"], reverse=True)

    return {
        "generated_at": today_iso,
        "tracked": tracked,
        "hit_rate_windows": hit_rate_windows,
        "brier_score": brier_score,
        "confidence_bands": confidence_bands,
        "sectors": sectors,
        "market_read": {
            "pct_up": round(bullish / tracked * 100, 1),
            "pct_down": round(100 - bullish / tracked * 100, 1),
            "tracked": tracked,
        },
        "stocks": stock_rows[:8],
    }


def get_market_stats(tickers=None, days=90, ttl=1800):
    """Watchlist-wide backtest aggregate (hit-rate windows, Brier score,
    confidence bands, sector breakdown, bull/bear read). Backtests every
    ticker in `tickers` (default the full watchlist), so a cold cache takes
    tens of seconds; cached for `ttl` seconds so most requests are instant."""
    tickers = tickers or DEFAULT_WATCHLIST
    return _cached("market_stats", ttl, lambda: _compute_market_stats(tickers, days=days))

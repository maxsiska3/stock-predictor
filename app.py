"""Flask backend for the Kouros prediction dashboard.

Everything is real: sector, history, direction, confidence, features, trends,
last5, hit rate, indices, and the watchlist-wide market stats
(utils/dashboard.py). No stub data paths remain.

Run: python app.py  ->  http://127.0.0.1:5001
"""
import re
import threading
from datetime import date, timedelta

from flask import Flask, jsonify, render_template
from utils.dashboard import (
    download_ohlcv,
    fetch_features_and_trends,
    fetch_history,
    fetch_performance,
    fetch_prediction,
    fetch_sector,
    get_index_predictions,
    get_market_stats,
)

app = Flask(__name__)

INDEX_DEFS = [
    ("SPY", "S&P 500"),
    ("QQQ", "NASDAQ 100"),
    ("IWM", "Russell 2000"),
    ("DIA", "Dow Jones"),
    ("^VIX", "VIX"),
    ("^RUT", "Russell 2000 Index"),
    ("^NDX", "NASDAQ 100 Index"),
]


def next_weekday(d):
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def build_prediction(ticker):
    """Prediction payload built entirely from real market data and the saved model."""
    today = date.today()

    raw_df = download_ohlcv(ticker)
    history = fetch_history(ticker, raw_df=raw_df)
    direction, confidence = fetch_prediction(ticker, history_df=raw_df)
    features, trends = fetch_features_and_trends(raw_df)
    last5, stock_hit_rate = fetch_performance(raw_df)

    return {
        "ticker": ticker,
        "sector": fetch_sector(ticker),
        "direction": direction,
        "confidence": confidence,
        "predicted_date": next_weekday(today).isoformat(),
        "features": features,
        "trends": trends,
        "history": history,
        "last5": last5,
        "stock_hit_rate": stock_hit_rate,
    }


def build_indices():
    """Real index/ETF predictions for the header marquee (cached, see get_index_predictions)."""
    predicted_date = next_weekday(date.today()).isoformat()
    out = get_index_predictions(INDEX_DEFS)
    for row in out:
        row["predicted_date"] = predicted_date
    return out


@app.route("/")
def index():
    return render_template("predict.html")


@app.route("/api/predict/<ticker>")
def predict(ticker):
    ticker = ticker.upper().strip()
    if not re.fullmatch(r"[A-Z.]{1,6}", ticker):
        return jsonify({"error": "unknown ticker"}), 404
    return jsonify(build_prediction(ticker))


@app.route("/api/indices")
def indices():
    return jsonify(build_indices())


@app.route("/api/market-stats")
def market_stats():
    """Watchlist-wide backtest aggregate for the 'Model track record' section.
    Cached in utils/dashboard.py; a cold cache backtests ~50 tickers and can
    take tens of seconds, so the frontend fetches this separately and fills
    the panels in once it resolves rather than blocking page load."""
    stats = get_market_stats()
    if stats is None:
        return jsonify({"error": "market stats unavailable"}), 503
    return jsonify(stats)


def _warm_market_stats_cache():
    """Pre-compute watchlist stats so the first browser load isn't a 30s cold wait."""
    try:
        get_market_stats()
    except Exception:
        pass


if __name__ == "__main__":
    threading.Thread(target=_warm_market_stats_cache, daemon=True).start()
    app.run(debug=True, port=5001)

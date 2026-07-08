"""Flask backend for the Kouros prediction dashboard.

Real data: sector, history, direction, confidence, features, trends (utils/dashboard.py).
Stub data: last5, hit rate, indices.

Run: python app.py  ->  http://127.0.0.1:5001
"""
import hashlib
import random
import re
from datetime import date, timedelta

from flask import Flask, jsonify, render_template
from utils.dashboard import (
    download_ohlcv,
    fetch_features_and_trends,
    fetch_history,
    fetch_prediction,
    fetch_sector,
)

app = Flask(__name__)

INDEX_DEFS = [
    ("SPY", "S&P 500"),
    ("QQQ", "NASDAQ 100"),
    ("IWM", "Russell 2000"),
    ("DIA", "Dow Jones"),
    ("VIX", "VIX"),
    ("RUT", "Russell 2000 Index"),
    ("NDX", "NASDAQ Composite"),
]


def _rng(seed: str) -> random.Random:
    return random.Random(int(hashlib.md5(seed.encode()).hexdigest(), 16))


def next_weekday(d):
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def prev_weekdays(d, n):
    out = []
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out[::-1]


def mock_prediction(ticker):
    """Prediction payload — real data except last5, hit rate."""
    rng = _rng(ticker)
    today = date.today()

    raw_df = download_ohlcv(ticker)
    history = fetch_history(ticker, raw_df=raw_df)
    direction, confidence = fetch_prediction(ticker, history_df=raw_df)
    features, trends = fetch_features_and_trends(raw_df)

    last5 = [
        {
            "date": d.isoformat(),
            "call": rng.choice(["up", "down"]),
            "confidence": round(rng.uniform(51, 68), 1),
            "hit": rng.random() < 0.58,
        }
        for d in prev_weekdays(today, 5)
    ]

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
        "stock_hit_rate": {
            "rate": round(rng.uniform(44, 66), 1),
            "calls": rng.randint(8, 40),
        },
    }


def mock_indices():
    """Deterministic fake index/ETF predictions for the header ticker."""
    predicted_date = next_weekday(date.today()).isoformat()
    out = []
    for symbol, name in INDEX_DEFS:
        rng = _rng(f"index:{symbol}")
        out.append({
            "symbol": symbol,
            "name": name,
            "direction": rng.choice(["up", "down"]),
            "confidence": round(rng.uniform(51.5, 64.5), 1),
            "predicted_date": predicted_date,
        })
    return out


@app.route("/")
def index():
    return render_template("predict.html")


@app.route("/api/predict/<ticker>")
def predict(ticker):
    ticker = ticker.upper().strip()
    if not re.fullmatch(r"[A-Z.]{1,6}", ticker):
        return jsonify({"error": "unknown ticker"}), 404
    return jsonify(mock_prediction(ticker))


@app.route("/api/indices")
def indices():
    return jsonify(mock_indices())


if __name__ == "__main__":
    app.run(debug=True, port=5001)

# Mock backend for the prediction dashboard frontend. No real ML.
# Run: python app.py  ->  http://127.0.0.1:5001
import hashlib
import random
import re
from datetime import date, timedelta

from flask import Flask, jsonify, render_template

app = Flask(__name__)

SECTORS = ["Technology", "Financials", "Energy", "Healthcare",
           "Consumer", "Industrials", "Utilities"]


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
    return out[::-1]  # oldest first


def trend7(rng, end, step):
    # 7-day walk ending at today's value, oldest first
    vals = [end]
    for _ in range(6):
        vals.append(vals[-1] + rng.gauss(0, step))
    return [round(v, 2) for v in reversed(vals)]


def mock_prediction(ticker):
    # ponytail: seeded by ticker so the same symbol always returns the same mock
    rng = random.Random(int(hashlib.md5(ticker.encode()).hexdigest(), 16))
    today = date.today()

    days = prev_weekdays(today, 60)
    price = rng.uniform(18, 480)
    prices = []
    for _ in days:
        price *= 1 + rng.gauss(0.0006, 0.018)
        prices.append(round(price, 2))

    confidence = round(rng.uniform(50.5, 69.5), 1)
    last5 = [{"date": d.isoformat(),
              "call": rng.choice(["up", "down"]),
              "confidence": round(rng.uniform(51, 68), 1),
              "hit": rng.random() < 0.58}
             for d in prev_weekdays(today, 5)]

    rsi = round(rng.uniform(22, 82), 1)
    macd = round(rng.uniform(-2.5, 2.5), 2)
    boll = round(rng.uniform(0.05, 0.95), 2)
    vol = round(rng.uniform(12, 55), 1)
    vc = round(rng.uniform(-45, 160), 1)

    return {
        "ticker": ticker,
        "sector": rng.choice(SECTORS),
        "direction": rng.choice(["up", "down"]),
        "confidence": confidence,
        "predicted_date": next_weekday(today).isoformat(),
        "features": {
            "rsi": rsi,
            "macd": macd,
            "bollinger": boll,
            "volatility": vol,
            "volume_change": vc,
        },
        "trends": {
            "rsi": trend7(rng, rsi, 4),
            "macd": trend7(rng, macd, 0.35),
            "bollinger": trend7(rng, boll, 0.09),
            "volatility": trend7(rng, vol, 2.5),
            "volume_change": trend7(rng, vc, 20),
        },
        "history": {"dates": [d.isoformat() for d in days], "prices": prices},
        "last5": last5,
        "stock_hit_rate": {"rate": round(rng.uniform(44, 66), 1),
                           "calls": rng.randint(8, 40)},
    }


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
    nd = next_weekday(date.today()).isoformat()
    return jsonify([
        {"name": "S&P 500", "direction": "up", "confidence": 61.2, "predicted_date": nd},
        {"name": "Dow", "direction": "down", "confidence": 54.8, "predicted_date": nd},
        {"name": "NASDAQ", "direction": "up", "confidence": 63.4, "predicted_date": nd},
    ])


if __name__ == "__main__":
    app.run(debug=True, port=5001)

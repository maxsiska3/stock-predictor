# app.py — local next-day direction predictor

import logging
import os

from flask import Flask, jsonify, render_template, request

from utils.predict import predict_stock
from utils.watchlist import DEFAULT_WATCHLIST
from utils.yfinance_setup import configure_yfinance

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

configure_yfinance()

app = Flask(__name__)
logger = logging.getLogger(__name__)


def _parse_tickers(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(t).strip().upper() for t in raw if str(t).strip()]
    return [t.strip().upper() for t in str(raw).split(",") if t.strip()]


def _prediction_row(ticker):
    sym = str(ticker or "").strip().upper()
    if not sym:
        return {"ticker": "", "direction": None, "confidence": None, "error": "Ticker required"}

    try:
        prediction, confidence = predict_stock(sym)
        direction = int(prediction[0])
        confidence_pct = round(float(confidence[0].max()) * 100, 2)
        return {
            "ticker": sym,
            "direction": direction,
            "confidence": confidence_pct,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Prediction failed for %s: %s", sym, exc)
        return {"ticker": sym, "direction": None, "confidence": None, "error": str(exc)}


def _summarize(results):
    up = sum(1 for r in results if r["direction"] == 1)
    down = sum(1 for r in results if r["direction"] == 0)
    failed = sum(1 for r in results if r["error"])
    return {"up": up, "down": down, "failed": failed, "total": len(results)}


@app.route("/")
def index():
    return render_template("index.html", watchlist_count=len(DEFAULT_WATCHLIST))


@app.route("/api/predict/<ticker>")
def api_predict_one(ticker):
    return jsonify(_prediction_row(ticker))


@app.route("/api/predictions", methods=["GET", "POST"])
def api_predictions():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        tickers = _parse_tickers(body.get("tickers"))
    else:
        tickers = _parse_tickers(request.args.get("tickers"))

    if not tickers:
        tickers = list(DEFAULT_WATCHLIST)

    results = [_prediction_row(t) for t in tickers]
    return jsonify({"predictions": results, "summary": _summarize(results)})


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    port = int(os.environ.get("PORT", 5001))
    print(f"Open http://127.0.0.1:{port}")
    app.run(debug=debug, port=port)

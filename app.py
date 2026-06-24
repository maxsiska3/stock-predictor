# app.py — Flask web server for MaxAlpha Terminal
# Handles routing, data assembly, and template rendering.
# Data fetching lives in utils/market.py to keep this file focused on routes.

from utils.predict import predict_stock
from utils.market import fetch_market_data
from flask import Flask, render_template, request, jsonify
from datetime import datetime

app = Flask(__name__)

# Tickers shown in the main watchlist table
WATCHLIST = [
    "ACN", "AAPL", "META", "GOOG", "AMZN",
    "TSM", "NVDA", "TSLA", "AMD", "BRK-B",
    "ORCL", "PLTR", "MU", "JPM", "AVGO"
]

# Hardcoded fund definitions — tickers list drives which holdings are shown
FUNDS = [
    {"name": "Max's Fund",     "tickers": ["ACN", "AAPL", "AMZN", "BRK-B", "NVDA", "JPM"]},
    {"name": "Excelsior Fund", "tickers": ["AMD", "ORCL", "MU", "PLTR"]},
]


def build_groups(market_data):
    """Sort market_data into mover and prediction groups for the right panel."""

    # Each group is a dict with a title, dot color, and a ranked list of tickers
    mover_groups = [
        {"title": "Gainers",     "key": "gainers", "dot": "var(--up)",
         "rows": sorted(market_data, key=lambda x: x["pct_change"], reverse=True)[:5]},
        {"title": "Losers",      "key": "losers",  "dot": "var(--down)",
         "rows": sorted(market_data, key=lambda x: x["pct_change"], reverse=False)[:5]},
        {"title": "Most Active", "key": "volume",  "dot": "var(--accent)",
         "rows": sorted(market_data, key=lambda x: x["volume"], reverse=True)[:5]},
    ]

    # Filter by ML direction first, then rank by model confidence
    pred_groups = [
        {"title": "Predicted Up Tomorrow",   "dot": "var(--up)",
         "rows": sorted([x for x in market_data if x["direction"] == 1], key=lambda x: x["confidence"], reverse=True)[:5]},
        {"title": "Predicted Down Tomorrow", "dot": "var(--down)",
         "rows": sorted([x for x in market_data if x["direction"] == 0], key=lambda x: x["confidence"], reverse=True)[:5]},
    ]

    return mover_groups, pred_groups


def build_funds(market_data):
    """Attach live market data to each fund's holdings and compute aggregate stats."""

    # Build a fast ticker → data lookup so we don't scan the list repeatedly
    lookup = {item["ticker"]: item for item in market_data}

    funds = []
    for fund in FUNDS:
        # Only include tickers that successfully fetched data
        holdings = [lookup[t] for t in fund["tickers"] if t in lookup]
        total = len(holdings)
        up_count = sum(1 for h in holdings if h["direction"] == 1)
        avg_conf = round(sum(h["confidence"] for h in holdings) / total, 1) if total > 0 else 0

        funds.append({
            "name": fund["name"],
            "tickers": fund["tickers"],
            "holdings": holdings,
            "count": total,
            "avg_conf": avg_conf,
            "direction": 1 if up_count >= total / 2 else 0,  # majority vote
        })
    return funds


# Jinja2 filter: converts raw volume int to human-readable string (e.g. 54200000 → "54.2M")
@app.template_filter("vol")
def format_volume(v):
    if v >= 1_000_000_000: return f"{v/1_000_000_000:.1f}B"
    if v >= 1_000_000:     return f"{v/1_000_000:.1f}M"
    if v >= 1_000:         return f"{v/1_000:.1f}K"
    return str(int(v))


@app.route("/")
def home():
    """Main dashboard — fetches live data and renders the full landing screen."""
    market_data = fetch_market_data(WATCHLIST)
    mover_groups, pred_groups = build_groups(market_data)
    funds = build_funds(market_data)

    return render_template(
        "landing-screen.html",
        watchlist=market_data,
        funds=funds,
        moverGroups=mover_groups,
        predGroups=pred_groups,
        watchCount=len(market_data),
        fundCount=len(funds),
        theme="light",
        now=datetime.now().strftime("%-I:%M %p"),  # e.g. "2:34 PM"
    )


@app.route("/api/market-data")
def api_market_data():
    """JSON endpoint polled by the frontend every 60s to refresh data without a page reload."""
    market_data = fetch_market_data(WATCHLIST)
    mover_groups, pred_groups = build_groups(market_data)

    return jsonify({
        "watchlist": market_data,
        "moverGroups": mover_groups,
        "predGroups": pred_groups,
    })


@app.route("/predict", methods=["POST"])
def predict():
    """Legacy single-ticker prediction endpoint used by the original index.html form."""
    ticker = request.form.get("ticker")
    prediction, confidence = predict_stock(ticker)
    direction = "Up" if prediction[0] == 1 else "Down"
    confidence_pct = round(float(confidence[0].max()) * 100, 2)
    return render_template("index.html", ticker=ticker, direction=direction, confidence=confidence_pct)


if __name__ == "__main__":
    app.run(debug=True)

# =============================================================================
# SUMMARY — app.py
# =============================================================================
# This is the Flask application entry point for MaxAlpha Terminal.
#
# Constants:
#   WATCHLIST   — 15 tickers displayed in the main table
#   FUNDS       — 2 hardcoded fund definitions
#
# Helper functions:
#   build_groups(market_data)  — sorts tickers into gainers/losers/volume and
#                                up/down prediction groups for the right panel
#   build_funds(market_data)   — joins live data onto fund holdings, computes
#                                avg confidence and majority direction per fund
#   format_volume(v)           — Jinja2 filter, formats large ints as 54.2M etc.
#
# Routes:
#   GET  /                  — renders landing-screen.html with all live data
#   GET  /api/market-data   — returns JSON; polled by JS every 60s for live updates
#   POST /predict           — legacy single-ticker form endpoint
# =============================================================================

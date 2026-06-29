# app.py — Flask web server for Kouros
# Routes, template rendering, and dashboard data assembly.
# Market fetching: utils/market.py | Watchlist persistence: utils/watchlist_store.py

from collections import Counter
from datetime import datetime

from flask import Flask, jsonify, render_template, request

from utils.market import fetch_market_data
from utils.predict import predict_stock
from utils.ticker_search import search_tickers
from utils.watchlist_store import WatchlistError, add_tickers, load_watchlist, remove_ticker

app = Flask(__name__)

# Hardcoded fund definitions — tickers list drives which holdings are shown (dynamic funds later).
FUNDS = [
    {"name": "Max's Fund",     "tickers": ["ACN", "AAPL", "AMZN", "BRK-B", "NVDA", "JPM"]},
    {"name": "Excelsior Fund", "tickers": ["AMD", "ORCL", "MU", "PLTR"]},
]


def get_fetch_tickers():
    """
    Tickers to pass to fetch_market_data.
    Union of user watchlist + fund holdings so funds still load when watchlist is empty.
    """
    watchlist = load_watchlist()
    fund_tickers = {t for f in FUNDS for t in f["tickers"]}
    return list(dict.fromkeys(watchlist + list(fund_tickers)))


def _split_watchlist_rows(market_data_all):
    """Watchlist table + sidebar use saved symbols only; funds use the full fetch set."""
    watchlist_symbols = set(load_watchlist())
    watchlist_rows = [r for r in market_data_all if r["ticker"] in watchlist_symbols]
    return watchlist_rows, watchlist_symbols


def build_groups(market_data):
    """Sort market_data into mover and prediction groups for the right panel."""

    mover_groups = [
        {"title": "Gainers",     "key": "gainers", "dot": "var(--up)",
         "rows": sorted(market_data, key=lambda x: x["pct_change"], reverse=True)[:5]},
        {"title": "Losers",      "key": "losers",  "dot": "var(--down)",
         "rows": sorted(market_data, key=lambda x: x["pct_change"], reverse=False)[:5]},
        {"title": "Most Active", "key": "volume",  "dot": "var(--accent)",
         "rows": sorted(market_data, key=lambda x: x["volume"], reverse=True)[:5]},
    ]

    pred_groups = [
        {"title": "Predicted Up Tomorrow",   "dot": "var(--up)",
         "rows": sorted([x for x in market_data if x["direction"] == 1], key=lambda x: x["confidence"], reverse=True)[:5]},
        {"title": "Predicted Down Tomorrow", "dot": "var(--down)",
         "rows": sorted([x for x in market_data if x["direction"] == 0], key=lambda x: x["confidence"], reverse=True)[:5]},
    ]

    return mover_groups, pred_groups


def _avg_field(holdings, key, digits=2):
    """Mean of a numeric field across holdings, ignoring missing values."""
    vals = [h[key] for h in holdings if h.get(key) is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), digits)


def build_funds(market_data):
    """Join live market data onto fund holdings and compute aggregate metrics."""

    lookup = {item["ticker"]: item for item in market_data}
    NOTIONAL = 10_000
    funds = []

    for fund in FUNDS:
        holdings = [lookup[t] for t in fund["tickers"] if t in lookup]
        total = len(holdings)
        updated_at = datetime.now().strftime("%-I:%M %p")

        if total == 0:
            funds.append({
                "name":            fund["name"],
                "holdings":        0,
                "pct_change":      None,
                "dollar_change":   None,
                "total_value":     None,
                "top_performer":   None,
                "worst_performer": None,
                "outlook":         None,
                "avg_eps":         None,
                "avg_rsi":         None,
                "avg_boll":        None,
                "avg_vol":         None,
                "tickers":         ", ".join(fund["tickers"]),
                "avg_beta":        None,
                "dominant_sector": None,
                "direction":       0,
                "avg_conf":        None,
                "updated_at":      updated_at,
            })
            continue

        pct_change = round(sum(h["pct_change"] for h in holdings) / total, 2)
        dollar_change = round(sum(NOTIONAL * h["pct_change"] / 100 for h in holdings), 2)
        total_value = round(sum(NOTIONAL * (1 + h["pct_change"] / 100) for h in holdings), 2)

        top = max(holdings, key=lambda x: x["pct_change"])
        worst = min(holdings, key=lambda x: x["pct_change"])

        up_count = sum(1 for h in holdings if h["direction"] == 1)
        sectors = [h["sector"] for h in holdings if h.get("sector")]
        dominant_sector = Counter(sectors).most_common(1)[0][0] if sectors else None

        funds.append({
            "name":            fund["name"],
            "holdings":        total,
            "pct_change":      pct_change,
            "dollar_change":   dollar_change,
            "total_value":     total_value,
            "top_performer":   top["ticker"],
            "worst_performer": worst["ticker"],
            "outlook":         f"{up_count}/{total} up",
            "avg_eps":         _avg_field(holdings, "eps", 2),
            "avg_rsi":         _avg_field(holdings, "rsi", 1),
            "avg_boll":        _avg_field(holdings, "bollinger_pos", 2),
            "avg_vol":         _avg_field(holdings, "volatility", 4),
            "tickers":         ", ".join(fund["tickers"]),
            "avg_beta":        _avg_field(holdings, "beta", 2),
            "dominant_sector": dominant_sector,
            "direction":       1 if up_count >= total / 2 else 0,
            "avg_conf":        round(sum(h["confidence"] for h in holdings) / total, 1),
            "updated_at":      updated_at,
        })

    return funds


@app.template_filter("vol")
def format_volume(v):
    """Jinja2 filter: 54200000 → '54.2M'."""
    if v >= 1_000_000_000:
        return f"{v/1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.1f}K"
    return str(int(v))


@app.template_filter("money")
def format_money(v):
    if v is None:
        return "—"
    return f"{v:,.0f}"


def _load_dashboard_context():
    """Shared data assembly for home page and /api/market-data."""
    market_data_all = fetch_market_data(get_fetch_tickers())
    watchlist_rows, _ = _split_watchlist_rows(market_data_all)
    mover_groups, pred_groups = build_groups(watchlist_rows)
    funds = build_funds(market_data_all)
    return watchlist_rows, mover_groups, pred_groups, funds


@app.route("/")
def home():
    """Main dashboard — fetches live data and renders the full landing screen."""
    watchlist_rows, mover_groups, pred_groups, funds = _load_dashboard_context()

    return render_template(
        "landing-screen.html",
        watchlist=watchlist_rows,
        funds=funds,
        moverGroups=mover_groups,
        predGroups=pred_groups,
        watchCount=len(watchlist_rows),
        fundCount=len(funds),
        theme="light",
        now=datetime.now().strftime("%-I:%M %p"),
    )


@app.route("/api/market-data")
def api_market_data():
    """JSON endpoint for future live polling (no full page reload)."""
    watchlist_rows, mover_groups, pred_groups, _funds = _load_dashboard_context()

    return jsonify({
        "watchlist": watchlist_rows,
        "moverGroups": mover_groups,
        "predGroups": pred_groups,
    })


@app.route("/api/watchlist", methods=["GET"])
def api_watchlist_get():
    return jsonify({"tickers": load_watchlist()})


@app.route("/api/watchlist", methods=["POST"])
def api_watchlist_add():
    body = request.get_json(silent=True) or {}
    tickers = body.get("tickers")
    try:
        result = add_tickers(tickers)
        return jsonify(result)
    except WatchlistError as e:
        return jsonify({"error": e.message}), e.status_code


@app.route("/api/watchlist", methods=["DELETE"])
def api_watchlist_remove():
    body = request.get_json(silent=True) or {}
    ticker = body.get("ticker")
    try:
        tickers = remove_ticker(ticker)
        return jsonify({"tickers": tickers})
    except WatchlistError as e:
        return jsonify({"error": e.message}), e.status_code


@app.route("/api/tickers/search")
def api_tickers_search():
    q = request.args.get("q", "")
    results = search_tickers(q, watchlist_symbols=load_watchlist())
    return jsonify({"results": results})


@app.route("/predict", methods=["POST"])
def predict():
    """Legacy single-ticker prediction endpoint used by index.html."""
    ticker = request.form.get("ticker")
    prediction, confidence = predict_stock(ticker)
    direction = "Up" if prediction[0] == 1 else "Down"
    confidence_pct = round(float(confidence[0].max()) * 100, 2)
    return render_template(
        "index.html",
        ticker=ticker,
        direction=direction,
        confidence=confidence_pct,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)

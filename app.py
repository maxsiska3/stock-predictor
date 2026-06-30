# app.py — Flask web server for Kouros
# Routes, auth, template rendering, and dashboard data assembly.

import logging
import os
from collections import Counter
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user

from utils.auth import AuthError, authenticate_user, create_user, get_user_by_id
from utils.db import init_db
from utils.fund_store import FundError, add_tickers_to_fund, create_fund, delete_fund, get_user_funds, remove_ticker_from_fund
from utils.market import fetch_market_data
from utils.position_store import PositionError, delete_position, get_all_positions, upsert_position
from utils.predict import predict_stock
from utils.refresh import start_background_refresh
from utils.ticker_search import search_tickers
from utils.watchlist_store import WatchlistError, add_tickers, load_watchlist, remove_ticker

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["REMEMBER_COOKIE_DURATION"] = 60 * 60 * 24 * 30  # 30 days

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)


# SPY is always fetched so every fund can show a vs-S&P benchmark.
_ALWAYS_FETCH = ["SPY"]


def get_user_fetch_tickers(user_id):
    """All tickers needed for one user's dashboard (watchlist + fund holdings + SPY)."""
    watchlist = load_watchlist(user_id)
    user_funds = get_user_funds(user_id)
    fund_tickers = [t for f in user_funds for t in f["tickers"]]
    all_symbols = list(dict.fromkeys(watchlist + fund_tickers + _ALWAYS_FETCH))
    return all_symbols


def _split_watchlist_rows(market_data_all, user_id):
    watchlist_symbols = set(load_watchlist(user_id))
    watchlist_rows = [r for r in market_data_all if r["ticker"] in watchlist_symbols]
    return watchlist_rows, watchlist_symbols


def _enrich_with_positions(watchlist_rows, positions):
    """Attach position data (shares, avg_cost, market_value, gain_loss, return_pct) to each row.

    Adds None values when the user has no position logged for that ticker.
    """
    enriched = []
    for row in watchlist_rows:
        pos = positions.get(row["ticker"])
        if pos:
            shares    = pos["shares"]
            avg_cost  = pos["avg_cost"]
            mkt_value = round(shares * row["price"], 2)
            gain_loss = round(mkt_value - shares * avg_cost, 2)
            return_pct = round((gain_loss / (shares * avg_cost)) * 100, 2) if avg_cost else None
        else:
            shares = avg_cost = mkt_value = gain_loss = return_pct = None

        enriched.append({
            **row,
            "shares":     shares,
            "avg_cost":   avg_cost,
            "mkt_value":  mkt_value,
            "gain_loss":  gain_loss,
            "return_pct": return_pct,
        })
    return enriched


def build_groups(market_data):
    mover_groups = [
        {"title": "Gainers", "key": "gainers", "dot": "var(--up)",
         "rows": sorted(market_data, key=lambda x: x["pct_change"], reverse=True)[:5]},
        {"title": "Losers", "key": "losers", "dot": "var(--down)",
         "rows": sorted(market_data, key=lambda x: x["pct_change"], reverse=False)[:5]},
        {"title": "Most Active", "key": "volume", "dot": "var(--accent)",
         "rows": sorted(market_data, key=lambda x: x["volume"], reverse=True)[:5]},
    ]

    pred_groups = [
        {"title": "Predicted Up Tomorrow", "dot": "var(--up)",
         "rows": sorted([x for x in market_data if x["direction"] == 1], key=lambda x: x["confidence"], reverse=True)[:5]},
        {"title": "Predicted Down Tomorrow", "dot": "var(--down)",
         "rows": sorted([x for x in market_data if x["direction"] == 0], key=lambda x: x["confidence"], reverse=True)[:5]},
    ]

    return mover_groups, pred_groups


def _avg_field(holdings, key, digits=2):
    vals = [h[key] for h in holdings if h.get(key) is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), digits)


def build_funds(market_data, user_funds):
    """Build aggregated fund rows from dynamic user funds.

    Args:
        market_data: list of market data dicts (all tickers fetched for this user)
        user_funds: list of {id, name, tickers} from fund_store

    Returns:
        list of fund aggregate dicts ready for the template
    """
    lookup = {item["ticker"]: item for item in market_data}
    spy = lookup.get("SPY")
    spy_pct = spy["pct_change"] if spy else None

    NOTIONAL = 10_000
    funds = []

    for fund in user_funds:
        holdings = [lookup[t] for t in fund["tickers"] if t in lookup]
        total = len(holdings)
        updated_at = datetime.now().strftime("%-I:%M %p")

        if total == 0:
            funds.append({
                "id": fund["id"], "name": fund["name"], "holdings": 0,
                "pct_change": None, "dollar_change": None, "total_value": None,
                "top_performer": None, "worst_performer": None, "outlook": None,
                "avg_eps": None, "avg_rsi": None, "avg_boll": None, "avg_vol": None,
                "tickers": ", ".join(fund["tickers"]),
                "avg_beta": None, "dominant_sector": None,
                "direction": 0, "avg_conf": None, "updated_at": updated_at,
                "vs_spy": None,
            })
            continue

        pct_change     = round(sum(h["pct_change"] for h in holdings) / total, 2)
        dollar_change  = round(sum(NOTIONAL * h["pct_change"] / 100 for h in holdings), 2)
        total_value    = round(sum(NOTIONAL * (1 + h["pct_change"] / 100) for h in holdings), 2)
        top            = max(holdings, key=lambda x: x["pct_change"])
        worst          = min(holdings, key=lambda x: x["pct_change"])
        up_count       = sum(1 for h in holdings if h["direction"] == 1)
        sectors        = [h["sector"] for h in holdings if h.get("sector")]
        dominant_sector = Counter(sectors).most_common(1)[0][0] if sectors else None
        vs_spy = round(pct_change - spy_pct, 2) if spy_pct is not None else None

        funds.append({
            "id": fund["id"], "name": fund["name"], "holdings": total,
            "pct_change": pct_change, "dollar_change": dollar_change,
            "total_value": total_value,
            "top_performer": top["ticker"], "worst_performer": worst["ticker"],
            "outlook": f"{up_count}/{total} up",
            "avg_eps": _avg_field(holdings, "eps", 2),
            "avg_rsi": _avg_field(holdings, "rsi", 1),
            "avg_boll": _avg_field(holdings, "bollinger_pos", 2),
            "avg_vol": _avg_field(holdings, "volatility", 4),
            "tickers": ", ".join(fund["tickers"]),
            "avg_beta": _avg_field(holdings, "beta", 2),
            "dominant_sector": dominant_sector,
            "direction": 1 if up_count >= total / 2 else 0,
            "avg_conf": round(sum(h["confidence"] for h in holdings) / total, 1),
            "updated_at": updated_at,
            "vs_spy": vs_spy,
        })

    return funds


def build_sector_chart(watchlist_rows):
    """Compute sector weights from the watchlist for the sidebar chart.

    Returns a list sorted by weight descending:
        [{"sector": "Technology", "count": 4, "pct": 40.0}, ...]
    """
    sectors = [r["sector"] for r in watchlist_rows if r.get("sector")]
    if not sectors:
        return []
    total = len(sectors)
    counts = Counter(sectors)
    return sorted(
        [{"sector": s, "count": c, "pct": round(c / total * 100, 1)} for s, c in counts.items()],
        key=lambda x: x["pct"],
        reverse=True,
    )


@app.template_filter("vol")
def format_volume(v):
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


def _load_dashboard_context(user_id):
    user_funds    = get_user_funds(user_id)
    positions     = get_all_positions(user_id)
    tickers       = get_user_fetch_tickers(user_id)
    market_data   = fetch_market_data(tickers)

    watchlist_rows, _ = _split_watchlist_rows(market_data, user_id)
    watchlist_rows    = _enrich_with_positions(watchlist_rows, positions)

    mover_groups, pred_groups = build_groups(watchlist_rows)
    funds         = build_funds(market_data, user_funds)
    sector_groups = build_sector_chart(watchlist_rows)

    return watchlist_rows, mover_groups, pred_groups, funds, sector_groups


# ── Auth routes ─────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        user = authenticate_user(request.form.get("email"), request.form.get("password"))
        if user:
            login_user(user, remember=True)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("home"))
        flash("Invalid email or password.", "error")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        try:
            user = create_user(
                request.form.get("email"),
                request.form.get("password"),
                request.form.get("display_name"),
            )
            login_user(user, remember=True)
            return redirect(url_for("home"))
        except AuthError as e:
            flash(e.message, "error")

    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ── Dashboard routes ────────────────────────────────────────

@app.route("/")
@login_required
def home():
    watchlist_rows, mover_groups, pred_groups, funds, sector_groups = _load_dashboard_context(current_user.id)
    user_funds = get_user_funds(current_user.id)

    return render_template(
        "landing-screen.html",
        watchlist=watchlist_rows,
        funds=funds,
        moverGroups=mover_groups,
        predGroups=pred_groups,
        watchCount=len(watchlist_rows),
        fundCount=len(funds),
        sectorGroups=sector_groups,
        watchlistSymbols=[r["ticker"] for r in watchlist_rows],
        theme="light",
        now=datetime.now().strftime("%-I:%M %p"),
    )


@app.route("/api/market-data")
@login_required
def api_market_data():
    watchlist_rows, mover_groups, pred_groups, _funds, _sectors = _load_dashboard_context(current_user.id)
    return jsonify({
        "watchlist": watchlist_rows,
        "moverGroups": mover_groups,
        "predGroups": pred_groups,
    })


# ── Watchlist API ────────────────────────────────────────────

@app.route("/api/watchlist", methods=["GET"])
@login_required
def api_watchlist_get():
    return jsonify({"tickers": load_watchlist(current_user.id)})


@app.route("/api/watchlist", methods=["POST"])
@login_required
def api_watchlist_add():
    body = request.get_json(silent=True) or {}
    tickers = body.get("tickers")
    try:
        result = add_tickers(current_user.id, tickers)
        return jsonify(result)
    except WatchlistError as e:
        return jsonify({"error": e.message}), e.status_code


@app.route("/api/watchlist", methods=["DELETE"])
@login_required
def api_watchlist_remove():
    body = request.get_json(silent=True) or {}
    ticker = body.get("ticker")
    try:
        tickers = remove_ticker(current_user.id, ticker)
        return jsonify({"tickers": tickers})
    except WatchlistError as e:
        return jsonify({"error": e.message}), e.status_code


@app.route("/api/tickers/search")
@login_required
def api_tickers_search():
    q = request.args.get("q", "")
    results = search_tickers(q, watchlist_symbols=load_watchlist(current_user.id))
    return jsonify({"results": results})


# ── Funds API ────────────────────────────────────────────────

@app.route("/api/funds", methods=["GET"])
@login_required
def api_funds_get():
    funds = get_user_funds(current_user.id)
    return jsonify({"funds": funds})


@app.route("/api/funds", methods=["POST"])
@login_required
def api_funds_create():
    body = request.get_json(silent=True) or {}
    try:
        fund = create_fund(current_user.id, body.get("name"), body.get("tickers", []))
        return jsonify(fund), 201
    except FundError as e:
        return jsonify({"error": e.message}), e.status_code


@app.route("/api/funds/<int:fund_id>", methods=["DELETE"])
@login_required
def api_funds_delete(fund_id):
    try:
        delete_fund(fund_id, current_user.id)
        return jsonify({"ok": True})
    except FundError as e:
        return jsonify({"error": e.message}), e.status_code


@app.route("/api/funds/<int:fund_id>/tickers", methods=["POST"])
@login_required
def api_fund_tickers_add(fund_id):
    body = request.get_json(silent=True) or {}
    try:
        tickers = add_tickers_to_fund(fund_id, current_user.id, body.get("tickers", []))
        return jsonify({"tickers": tickers})
    except FundError as e:
        return jsonify({"error": e.message}), e.status_code


@app.route("/api/funds/<int:fund_id>/tickers", methods=["DELETE"])
@login_required
def api_fund_tickers_remove(fund_id):
    body = request.get_json(silent=True) or {}
    try:
        tickers = remove_ticker_from_fund(fund_id, current_user.id, body.get("ticker"))
        return jsonify({"tickers": tickers})
    except FundError as e:
        return jsonify({"error": e.message}), e.status_code


# ── Positions API ────────────────────────────────────────────

@app.route("/api/positions", methods=["GET"])
@login_required
def api_positions_get():
    positions = get_all_positions(current_user.id)
    return jsonify({"positions": positions})


@app.route("/api/positions", methods=["PUT"])
@login_required
def api_positions_upsert():
    body = request.get_json(silent=True) or {}
    try:
        pos = upsert_position(
            current_user.id,
            body.get("symbol"),
            body.get("shares"),
            body.get("avg_cost"),
            body.get("purchased_at"),
        )
        return jsonify(pos)
    except PositionError as e:
        return jsonify({"error": e.message}), e.status_code


@app.route("/api/positions/<symbol>", methods=["DELETE"])
@login_required
def api_positions_delete(symbol):
    delete_position(current_user.id, symbol)
    return jsonify({"ok": True})


@app.route("/predict", methods=["POST"])
@login_required
def predict():
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


# ── Startup ─────────────────────────────────────────────────

init_db()
start_background_refresh()

# Cache warm runs in the background thread — do not block Gunicorn startup on Render.


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, port=int(os.environ.get("PORT", 5001)))

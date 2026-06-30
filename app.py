# app.py — Flask web server for Kouros
# Routes, auth, template rendering, and dashboard data assembly.

import os
from collections import Counter
from datetime import datetime

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user

from utils.auth import AuthError, authenticate_user, create_user, get_user_by_id
from utils.config import FUNDS, get_fund_tickers
from utils.db import init_db
from utils.market import fetch_market_data
from utils.predict import predict_stock
from utils.refresh import get_union_fetch_tickers, start_background_refresh
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


def get_user_fetch_tickers(user_id):
    """Tickers needed for one user's dashboard (watchlist + fund holdings)."""
    watchlist = load_watchlist(user_id)
    return list(dict.fromkeys(watchlist + list(get_fund_tickers())))


def _split_watchlist_rows(market_data_all, user_id):
    watchlist_symbols = set(load_watchlist(user_id))
    watchlist_rows = [r for r in market_data_all if r["ticker"] in watchlist_symbols]
    return watchlist_rows, watchlist_symbols


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


def build_funds(market_data):
    lookup = {item["ticker"]: item for item in market_data}
    NOTIONAL = 10_000
    funds = []

    for fund in FUNDS:
        holdings = [lookup[t] for t in fund["tickers"] if t in lookup]
        total = len(holdings)
        updated_at = datetime.now().strftime("%-I:%M %p")

        if total == 0:
            funds.append({
                "name": fund["name"], "holdings": 0,
                "pct_change": None, "dollar_change": None, "total_value": None,
                "top_performer": None, "worst_performer": None, "outlook": None,
                "avg_eps": None, "avg_rsi": None, "avg_boll": None, "avg_vol": None,
                "tickers": ", ".join(fund["tickers"]),
                "avg_beta": None, "dominant_sector": None,
                "direction": 0, "avg_conf": None, "updated_at": updated_at,
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
            "name": fund["name"], "holdings": total,
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
        })

    return funds


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
    market_data_all = fetch_market_data(get_user_fetch_tickers(user_id))
    watchlist_rows, _ = _split_watchlist_rows(market_data_all, user_id)
    mover_groups, pred_groups = build_groups(watchlist_rows)
    funds = build_funds(market_data_all)
    return watchlist_rows, mover_groups, pred_groups, funds


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
    watchlist_rows, mover_groups, pred_groups, funds = _load_dashboard_context(current_user.id)

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
@login_required
def api_market_data():
    watchlist_rows, mover_groups, pred_groups, _funds = _load_dashboard_context(current_user.id)
    return jsonify({
        "watchlist": watchlist_rows,
        "moverGroups": mover_groups,
        "predGroups": pred_groups,
    })


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

# Warm cache once on startup (union of all tickers).
try:
    union = get_union_fetch_tickers()
    if union:
        fetch_market_data(union)
except Exception as e:
    print(f"Startup cache warm skipped: {e}")


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, port=int(os.environ.get("PORT", 5001)))

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
from utils.config import BENCHMARK_OPTIONS, BENCHMARK_TICKERS
from utils.db import DB_PATH, init_db
from utils.yfinance_setup import configure_yfinance
from utils.fund_store import (
    FundError,
    add_tickers_to_fund,
    clear_fund_holding_position,
    create_fund,
    delete_fund,
    update_fund,
    get_user_funds,
    remove_ticker_from_fund,
    upsert_fund_holding_position,
)
from utils.market import fetch_market_data
from utils.position_store import PositionError, delete_position, get_all_positions, upsert_position
from utils.predict import predict_stock
from utils.refresh import start_background_refresh
from utils.ticker_search import search_tickers
from utils.watchlist_store import (
    WatchlistError,
    add_tickers,
    ensure_watchlist_quote_types,
    load_watchlist,
    load_watchlist_quote_types,
    remove_ticker,
)

app = Flask(__name__)
logger = logging.getLogger(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["REMEMBER_COOKIE_DURATION"] = 60 * 60 * 24 * 30  # 30 days

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"


@app.template_global()
def asset_url(filename):
    """
    Static asset URL with a cache-busting ?v=<mtime> query string. Without this,
    browsers can keep serving a stale cached dashboard.js/styles.css for hours
    after a deploy (Flask's default static Cache-Control), so UI fixes silently
    fail to appear until a hard refresh.
    """
    static_path = os.path.join(app.static_folder, filename)
    try:
        version = int(os.path.getmtime(static_path))
    except OSError:
        version = 0
    return url_for("static", filename=filename) + f"?v={version}"


@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)


def get_user_fetch_tickers(user_id):
    """All tickers needed for one user's dashboard (watchlist + fund holdings + benchmarks)."""
    watchlist = load_watchlist(user_id)
    user_funds = get_user_funds(user_id)
    fund_tickers = [t for f in user_funds for t in f["tickers"]]
    all_symbols = list(dict.fromkeys(watchlist + fund_tickers + BENCHMARK_TICKERS))
    return all_symbols


def _apply_stored_quote_types(watchlist_rows, quote_types):
    """Use DB quote_type for Stocks/ETFs grouping — survives .info rate limits."""
    for row in watchlist_rows:
        sym = row["ticker"]
        if quote_types.get(sym):
            row["quote_type"] = quote_types[sym]
        else:
            row["quote_type"] = (row.get("quote_type") or "EQUITY").upper()
    return watchlist_rows


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


def _row_ticker(row):
    """Safely extract ticker from a market row dict (or None)."""
    if not row:
        return None
    return row.get("ticker")


def _is_up(row):
    pct = row.get("pct_change")
    return pct is not None and pct > 0


def _is_down(row):
    pct = row.get("pct_change")
    return pct is not None and pct < 0


def _format_clock_time(when=None):
    """Cross-platform 12h clock label (macOS %-I vs Linux %I)."""
    when = when or datetime.now()
    try:
        return when.strftime("%-I:%M %p")
    except ValueError:
        return when.strftime("%I:%M %p").lstrip("0")


def build_groups(market_data):
    gainers = sorted(
        [x for x in market_data if _is_up(x)],
        key=lambda x: x["pct_change"],
        reverse=True,
    )[:5]
    losers = sorted(
        [x for x in market_data if _is_down(x)],
        key=lambda x: x["pct_change"],
    )[:5]

    mover_groups = [
        {"title": "Gainers", "key": "gainers", "dot": "var(--up)", "rows": gainers},
        {"title": "Losers", "key": "losers", "dot": "var(--down)", "rows": losers},
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


def _vs_benchmark(fund_pct, lookup, ticker):
    """Daily % change minus index ETF daily % change."""
    bench = lookup.get(ticker)
    if bench is None or fund_pct is None:
        return None
    return round(fund_pct - bench["pct_change"], 2)


def _attach_vs_benchmarks(rows, lookup):
    """Add vs_spy / vs_dow / vs_nasdaq to each row for the benchmark column."""
    return [
        {
            **row,
            "vs_spy": _vs_benchmark(row.get("pct_change"), lookup, "SPY"),
            "vs_dow": _vs_benchmark(row.get("pct_change"), lookup, "DIA"),
            "vs_nasdaq": _vs_benchmark(row.get("pct_change"), lookup, "QQQ"),
        }
        for row in rows
    ]


def _enrich_holding_row(market_row, holding):
    """Attach fund holding position fields to a market data row."""
    shares = holding.get("shares")
    avg_cost = holding.get("avg_cost")
    if shares is not None and avg_cost is not None:
        mkt_value = round(shares * market_row["price"], 2)
        cost_basis = shares * avg_cost
        gain_loss = round(mkt_value - cost_basis, 2)
        return_pct = round((gain_loss / cost_basis) * 100, 2) if cost_basis else None
    else:
        mkt_value = gain_loss = return_pct = None

    return {
        **market_row,
        "fund_id": holding.get("fund_id"),
        "shares": shares,
        "avg_cost": avg_cost,
        "mkt_value": mkt_value,
        "gain_loss": gain_loss,
        "return_pct": return_pct,
    }


FUND_NOTIONAL = 10_000


def _compute_fund_daily_change(holding_rows):
    """Daily $ change, % change, and current value for a fund summary row.

    Holdings with logged shares use actual share count; others use equal
    $10k notional. pct_change is always dollar_change / prior-day value
    so Chg % and $ Change stay in sync.
    """
    if not holding_rows:
        return None, None, None

    dollar_change = 0.0
    prior_value = 0.0
    current_value = 0.0

    for h in holding_rows:
        pct = h.get("pct_change")
        change = h.get("change")
        price = h.get("price")
        shares = h.get("shares")

        if shares is not None and shares > 0 and change is not None and price is not None:
            dollar_change += shares * change
            prior_value += shares * (price - change)
            current_value += shares * price
        elif pct is not None:
            dollar_change += FUND_NOTIONAL * pct / 100
            prior_value += FUND_NOTIONAL
            current_value += FUND_NOTIONAL * (1 + pct / 100)

    if prior_value <= 0:
        return None, None, None

    dollar_change = round(dollar_change, 2)
    pct_change = round((dollar_change / prior_value) * 100, 2)
    current_value = round(current_value, 2)
    return pct_change, dollar_change, current_value


def _aggregate_fund_positions(holding_rows):
    """Portfolio-level totals from per-ticker positions inside a fund."""
    positioned = [
        h for h in holding_rows
        if h.get("shares") is not None and h.get("avg_cost") is not None
    ]
    if not positioned:
        return {
            "shares": None, "avg_cost": None, "mkt_value": None,
            "gain_loss": None, "return_pct": None,
        }

    total_cost = sum(h["shares"] * h["avg_cost"] for h in positioned)
    total_mkt = sum(h["mkt_value"] for h in positioned)
    gain_loss = round(total_mkt - total_cost, 2)
    return_pct = round((gain_loss / total_cost) * 100, 2) if total_cost else None

    total_shares = sum(h["shares"] for h in positioned)
    return {
        "shares": round(total_shares, 4) if total_shares else None,
        "avg_cost": round(total_cost / total_shares, 2) if total_shares else None,
        "mkt_value": round(total_mkt, 2),
        "gain_loss": gain_loss,
        "return_pct": return_pct,
    }


def build_funds(market_data, user_funds):
    """Build fund summary rows plus per-holding detail for expandable child rows."""
    lookup = {item["ticker"]: item for item in market_data}
    funds = []

    for fund in user_funds:
        fund_id = fund["id"]
        holdings_meta = fund.get("holdings") or [
            {"symbol": t, "shares": None, "avg_cost": None} for t in fund.get("tickers", [])
        ]
        market_holdings = []
        holding_rows = []

        for h in holdings_meta:
            sym = h["symbol"]
            if sym not in lookup:
                continue
            meta = {**h, "fund_id": fund_id}
            row = _enrich_holding_row(lookup[sym], meta)
            market_holdings.append(lookup[sym])
            holding_rows.append(row)

        holding_rows = _attach_vs_benchmarks(holding_rows, lookup)
        total = len(market_holdings)
        updated_at = _format_clock_time()
        position_totals = _aggregate_fund_positions(holding_rows)

        if total == 0:
            funds.append({
                "id": fund_id, "name": fund["name"], "holdings": 0,
                "pct_change": None, "dollar_change": None, "total_value": None,
                "top_performer": None, "worst_performer": None, "outlook": None,
                "avg_eps": None, "avg_rsi": None, "avg_boll": None, "avg_vol": None,
                "avg_macd": None, "avg_beta": None, "dominant_sector": None,
                "direction": 0, "avg_conf": None, "updated_at": updated_at,
                "vs_spy": None, "vs_dow": None, "vs_nasdaq": None,
                "holding_rows": [],
                "symbols": [h["symbol"] for h in holdings_meta],
                **position_totals,
            })
            continue

        # Daily change: value-weighted (shares when logged, else $10k notional per ticker)
        pct_change, dollar_change, total_value = _compute_fund_daily_change(holding_rows)
        up_holdings = [h for h in market_holdings if _is_up(h)]
        down_holdings = [h for h in market_holdings if _is_down(h)]
        top = max(up_holdings, key=lambda x: x["pct_change"]) if up_holdings else (
            max(market_holdings, key=lambda x: x["pct_change"]) if market_holdings else None
        )
        worst = min(down_holdings, key=lambda x: x["pct_change"]) if down_holdings else (
            min(market_holdings, key=lambda x: x["pct_change"]) if market_holdings else None
        )
        pred_up_count = sum(1 for h in market_holdings if h["direction"] == 1)
        sectors = [h["sector"] for h in market_holdings if h.get("sector")]
        dominant_sector = Counter(sectors).most_common(1)[0][0] if sectors else None

        funds.append({
            "id": fund_id, "name": fund["name"], "holdings": total,
            "pct_change": pct_change, "dollar_change": dollar_change,
            "total_value": total_value,
            "top_performer": _row_ticker(top),
            "worst_performer": _row_ticker(worst),
            "outlook": f"{pred_up_count}/{total} up",
            "avg_eps": _avg_field(market_holdings, "eps", 2),
            "avg_rsi": _avg_field(market_holdings, "rsi", 1),
            "avg_boll": _avg_field(market_holdings, "bollinger_pos", 2),
            "avg_vol": _avg_field(market_holdings, "volatility", 4),
            "avg_macd": _avg_field(market_holdings, "macd", 2),
            "avg_beta": _avg_field(market_holdings, "beta", 2),
            "dominant_sector": dominant_sector,
            "direction": 1 if pred_up_count >= total / 2 else 0,
            "avg_conf": round(sum(h["confidence"] for h in market_holdings) / total, 1),
            "updated_at": updated_at,
            "vs_spy": _vs_benchmark(pct_change, lookup, "SPY"),
            "vs_dow": _vs_benchmark(pct_change, lookup, "DIA"),
            "vs_nasdaq": _vs_benchmark(pct_change, lookup, "QQQ"),
            "holding_rows": holding_rows,
            "symbols": [h["symbol"] for h in holdings_meta],
            **position_totals,
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
    # wait=False: page loads always read from cache instantly — the background
    # refresh thread (utils/refresh.py) is solely responsible for talking to
    # yfinance, so a slow/rate-limited Yahoo response never stalls a request.
    ensure_watchlist_quote_types(user_id)
    quote_types     = load_watchlist_quote_types(user_id)
    market_data   = fetch_market_data(tickers, wait=False)

    watchlist_rows, _ = _split_watchlist_rows(market_data, user_id)
    watchlist_rows    = _apply_stored_quote_types(watchlist_rows, quote_types)
    watchlist_rows    = _enrich_with_positions(watchlist_rows, positions)
    lookup            = {item["ticker"]: item for item in market_data}
    watchlist_rows    = _attach_vs_benchmarks(watchlist_rows, lookup)

    # Split into stocks / ETFs / indexes for grouped display in the watchlist table.
    # Indexes (^GSPC, ^DJI, ^IXIC) show the real index level, not an ETF price.
    watchlist_indexes = [r for r in watchlist_rows if r.get("quote_type", "EQUITY") == "INDEX"]
    watchlist_etfs    = [r for r in watchlist_rows if r.get("quote_type", "EQUITY") == "ETF"]
    watchlist_stocks  = [
        r for r in watchlist_rows
        if r.get("quote_type", "EQUITY") not in ("ETF", "INDEX")
    ]

    mover_groups, pred_groups = build_groups(watchlist_rows)
    funds         = build_funds(market_data, user_funds)
    sector_groups = build_sector_chart(watchlist_rows)

    return watchlist_stocks, watchlist_etfs, watchlist_indexes, watchlist_rows, mover_groups, pred_groups, funds, sector_groups


# ── Auth routes ─────────────────────────────────────────────

@app.route("/health")
def health():
    return "ok", 200


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
    # Raw symbols from DB — always available even when market data fetch fails.
    # Used by the Add Fund modal to list tickers the user can add to a fund.
    raw_watchlist_symbols = load_watchlist(current_user.id)

    watchlist_stocks, watchlist_etfs, watchlist_indexes, watchlist_rows, mover_groups, pred_groups, funds, sector_groups = _load_dashboard_context(current_user.id)

    return render_template(
        "landing-screen.html",
        watchlist_stocks=watchlist_stocks,
        watchlist_etfs=watchlist_etfs,
        watchlist_indexes=watchlist_indexes,
        watchlist=watchlist_rows,
        funds=funds,
        moverGroups=mover_groups,
        predGroups=pred_groups,
        watchCount=len(watchlist_rows),
        fundCount=len(funds),
        sectorGroups=sector_groups,
        watchlistSymbols=raw_watchlist_symbols,
        benchmarkOptions=BENCHMARK_OPTIONS,
        theme="light",
        now=_format_clock_time(),
    )


@app.route("/api/market-data")
@login_required
def api_market_data():
    _stocks, _etfs, _indexes, watchlist_rows, mover_groups, pred_groups, _funds, _sectors = _load_dashboard_context(current_user.id)
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
    quote_types = body.get("quote_types")
    try:
        result = add_tickers(current_user.id, tickers, quote_types=quote_types)
        return jsonify(result)
    except WatchlistError as e:
        return jsonify({"error": e.message}), e.status_code
    except Exception:
        logger.exception("POST /api/watchlist failed for user %s", current_user.id)
        return jsonify({"error": "Could not save tickers — try again"}), 500


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
    context = request.args.get("context", "watchlist")
    try:
        watchlist_syms = load_watchlist(current_user.id) if context == "watchlist" else []
        results = search_tickers(q, watchlist_symbols=watchlist_syms)
        return jsonify({"results": results})
    except Exception:
        logger.exception("GET /api/tickers/search failed for q=%r", q)
        return jsonify({"results": [], "error": "Search unavailable — try again"}), 500


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


@app.route("/api/funds/<int:fund_id>", methods=["PUT"])
@login_required
def api_funds_update(fund_id):
    body = request.get_json(silent=True) or {}
    try:
        fund = update_fund(
            fund_id,
            current_user.id,
            body.get("name"),
            body.get("tickers", []),
        )
        return jsonify(fund)
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


@app.route("/api/funds/<int:fund_id>/holdings/<symbol>/position", methods=["PUT"])
@login_required
def api_fund_holding_position_upsert(fund_id, symbol):
    body = request.get_json(silent=True) or {}
    try:
        pos = upsert_fund_holding_position(
            fund_id,
            current_user.id,
            symbol,
            body.get("shares"),
            body.get("avg_cost"),
        )
        return jsonify(pos)
    except FundError as e:
        return jsonify({"error": e.message}), e.status_code


@app.route("/api/funds/<int:fund_id>/holdings/<symbol>/position", methods=["DELETE"])
@login_required
def api_fund_holding_position_clear(fund_id, symbol):
    try:
        clear_fund_holding_position(fund_id, current_user.id, symbol)
        return jsonify({"ok": True})
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

configure_yfinance()
init_db()
logger.info("SQLite database: %s", DB_PATH)
start_background_refresh()

# Cache warm runs in the background thread — do not block Gunicorn startup on Render.


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, port=int(os.environ.get("PORT", 5001)))

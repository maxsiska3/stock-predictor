# utils/watchlist_store.py — per-user watchlist in SQLite
#
# Each function takes user_id. Flask routes pass current_user.id from Flask-Login.

from utils.db import commit_with_retry, get_connection, utc_now_iso
from utils.market import clear_cache
from utils.ticker_search import lookup_quote_type

MAX_TICKERS = 25


class WatchlistError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _normalize_symbol(symbol):
    if symbol is None or not str(symbol).strip():
        raise WatchlistError("Ticker is required")
    return str(symbol).strip().upper()


def _normalize_list(tickers):
    seen = set()
    result = []
    for ticker in tickers:
        sym = _normalize_symbol(ticker)
        if sym not in seen:
            seen.add(sym)
            result.append(sym)
    return result


def load_watchlist(user_id, conn=None):
    """Return the user's saved symbols in insertion order."""
    if conn is not None:
        rows = conn.execute(
            "SELECT symbol FROM watchlist WHERE user_id = ? ORDER BY added_at ASC, id ASC",
            (user_id,),
        ).fetchall()
        return [row["symbol"] for row in rows]

    with get_connection() as c:
        rows = c.execute(
            "SELECT symbol FROM watchlist WHERE user_id = ? ORDER BY added_at ASC, id ASC",
            (user_id,),
        ).fetchall()
    return [row["symbol"] for row in rows]


def load_watchlist_quote_types(user_id):
    """Return {symbol: quote_type} for the user's watchlist."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT symbol, quote_type FROM watchlist WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {
        row["symbol"]: (row["quote_type"] or "EQUITY").upper()
        for row in rows
    }


def ensure_watchlist_quote_types(user_id):
    """Backfill quote_type for legacy rows using Yahoo search (not .info)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, symbol FROM watchlist
            WHERE user_id = ? AND (quote_type IS NULL OR quote_type = '')
            """,
            (user_id,),
        ).fetchall()
        if not rows:
            return

        for row in rows:
            quote_type = lookup_quote_type(row["symbol"])
            conn.execute(
                "UPDATE watchlist SET quote_type = ? WHERE id = ?",
                (quote_type, row["id"]),
            )
        commit_with_retry(conn)


def save_watchlist(user_id, tickers):
    """Replace the user's entire watchlist with a normalized list."""
    normalized = _normalize_list(tickers)
    if len(normalized) > MAX_TICKERS:
        raise WatchlistError(f"Max {MAX_TICKERS} tickers")

    with get_connection() as conn:
        conn.execute("DELETE FROM watchlist WHERE user_id = ?", (user_id,))
        for symbol in normalized:
            conn.execute(
                """
                INSERT INTO watchlist (user_id, symbol, added_at, quote_type)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, symbol, utc_now_iso(), lookup_quote_type(symbol)),
            )
        commit_with_retry(conn)


def _validate_ticker(symbol):
    try:
        import yfinance as yf
        from utils.yfinance_setup import configure_yfinance
        configure_yfinance()
        hist = yf.Ticker(symbol).history(period="5d")
        return hist is not None and not hist.empty
    except Exception:
        return False


def _normalize_quote_types(quote_types):
    if not quote_types:
        return {}
    normalized = {}
    for raw_sym, raw_type in quote_types.items():
        try:
            sym = _normalize_symbol(raw_sym)
        except WatchlistError:
            continue
        normalized[sym] = str(raw_type or "EQUITY").strip().upper() or "EQUITY"
    return normalized


def add_tickers(user_id, symbols, quote_types=None, trusted_from_search=True):
    """Batch add symbols for one user. Same return shape as before."""
    if not symbols:
        raise WatchlistError("No tickers provided")

    with get_connection() as conn:
        current = load_watchlist(user_id, conn=conn)
        current_set = set(current)
        added, skipped, failed = [], [], []
        type_map = _normalize_quote_types(quote_types)

        for raw in symbols:
            try:
                sym = _normalize_symbol(raw)
            except WatchlistError:
                failed.append({"symbol": str(raw), "reason": "Ticker is required"})
                continue

            if sym in current_set:
                reason = "Already in watchlist" if sym in current else "Duplicate in request"
                skipped.append({"symbol": sym, "reason": reason})
                continue

            if len(current) + len(added) >= MAX_TICKERS:
                failed.append({"symbol": sym, "reason": f"Max {MAX_TICKERS} tickers"})
                continue

            if not trusted_from_search and not _validate_ticker(sym):
                failed.append({"symbol": sym, "reason": "Invalid ticker"})
                continue

            added.append(sym)
            current_set.add(sym)

        updated = current + added

        if added:
            for symbol in added:
                quote_type = type_map.get(symbol) or lookup_quote_type(symbol)
                conn.execute(
                    """
                    INSERT INTO watchlist (user_id, symbol, added_at, quote_type)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, symbol, utc_now_iso(), quote_type),
                )
            commit_with_retry(conn)

    if added:
        clear_cache(added)

    return {
        "tickers": updated,
        "added": added,
        "skipped": skipped,
        "failed": failed,
    }


def remove_ticker(user_id, symbol):
    """Remove one symbol from the user's watchlist."""
    sym = _normalize_symbol(symbol)
    current = load_watchlist(user_id)

    if sym not in current:
        raise WatchlistError("Ticker not in watchlist")

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND symbol = ?",
            (user_id, sym),
        )
        commit_with_retry(conn)

    clear_cache([sym])
    return [t for t in current if t != sym]

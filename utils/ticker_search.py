# utils/ticker_search.py — live symbol search for the add-ticker popup
#
# The user types in a search box; this module returns matching symbols they can
# check and add. Raw search text is NEVER added to the watchlist — only symbols
# picked from these results (enforced in dashboard.js + add_tickers).

from datetime import datetime, timedelta

import yfinance as yf

# Only show types that make sense on a stock dashboard (skip indices, currencies, etc.).
_ALLOWED_QUOTE_TYPES = {"EQUITY", "ETF"}

# In-memory cache — same idea as utils/market.py (lives until server restarts).
# We cache symbol+name rows from yfinance, NOT in_watchlist (that changes when user adds/removes).
_search_cache = {}
_SEARCH_TTL = timedelta(minutes=5)


def _search_cache_key(query):
    """'NVDA' and 'nvda' should hit the same cache entry."""
    return str(query).strip().lower()


def _get_cached_rows(query):
    entry = _search_cache.get(_search_cache_key(query))
    if not entry:
        return None

    if datetime.now() - entry["updated_at"] > _SEARCH_TTL:
        del _search_cache[_search_cache_key(query)]
        return None

    return entry["rows"]


def _set_cached_rows(query, rows):
    _search_cache[_search_cache_key(query)] = {
        "rows": rows,
        "updated_at": datetime.now(),
    }


def _parse_quotes(quotes, limit):
    """Turn raw yfinance quotes into [{symbol, name}, ...] — no in_watchlist yet."""
    rows = []
    seen_symbols = set()

    for quote in quotes:
        if len(rows) >= limit:
            break

        symbol = quote.get("symbol")
        if not symbol:
            continue

        symbol = str(symbol).upper()
        if symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)

        quote_type = (quote.get("quoteType") or "").upper()
        if quote_type and quote_type not in _ALLOWED_QUOTE_TYPES:
            continue

        name = quote.get("longname") or quote.get("shortname") or symbol
        rows.append({"symbol": symbol, "name": name})

    return rows


def _fetch_rows(query, limit):
    """
    Get symbol+name rows — from cache if fresh, otherwise yfinance.Search.
    This is the slow/network part; only this result gets cached.
    """
    cached = _get_cached_rows(query)
    if cached is not None:
        return cached[:limit]

    try:
        response = yf.Search(query, max_results=limit * 2)
        quotes = response.quotes or []
    except Exception:
        return []

    rows = _parse_quotes(quotes, limit)
    _set_cached_rows(query, rows)
    return rows


def _attach_watchlist_flags(rows, watchlist_symbols):
    """
    Mark which results are already saved.
    Done on every request so cache stays valid after add/remove.
    """
    on_watchlist = {str(s).strip().upper() for s in (watchlist_symbols or [])}
    return [
        {**row, "in_watchlist": row["symbol"] in on_watchlist}
        for row in rows
    ]


def search_tickers(query, watchlist_symbols=None, limit=10):
    """
    Return close matches for what the user is typing.

    Args:
        query: text from the search input (e.g. "nv", "apple")
        watchlist_symbols: symbols already saved — UI disables those rows
        limit: max results to return (keeps the popup small)

    Returns:
        [
            {"symbol": "NVDA", "name": "NVIDIA Corporation", "in_watchlist": False},
            ...
        ]
    """
    if not query or not str(query).strip():
        return []

    q = str(query).strip()
    rows = _fetch_rows(q, limit)
    return _attach_watchlist_flags(rows, watchlist_symbols)

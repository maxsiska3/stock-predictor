# utils/ticker_search.py — live symbol search for the add-ticker popup
#
# The user types in a search box; this module returns matching symbols they can
# check and add. Raw search text is NEVER added to the watchlist — only symbols
# picked from these results (enforced in dashboard.js + add_tickers).

import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import yfinance as yf

from utils.yfinance_setup import configure_yfinance, get_yf_session
from utils.symbols import is_index_symbol, resolve_search_query

configure_yfinance()
_SESSION = get_yf_session()

logger = logging.getLogger(__name__)

# Block non-investable types. Using a blocklist (not allowlist) because yfinance
# returns different quoteType strings across versions (e.g. "EQUITY", "equity",
# "commonStock"). Blocking known noise types is more robust.
_BLOCKED_QUOTE_TYPES = {"INDEX", "CURRENCY", "CRYPTOCURRENCY", "FUTURE", "OPTION", "FOREX"}

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-^=]{0,9}$")

# In-memory cache — same idea as utils/market.py (lives until server restarts).
# We cache symbol+name rows from yfinance, NOT in_watchlist (that changes when user adds/removes).
_search_cache = {}
_SEARCH_TTL = timedelta(minutes=5)

_YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
_YAHOO_UA = "Mozilla/5.0 (compatible; Kouros/1.0; +https://github.com/maxsiska3/stock-predictor)"


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
        if is_index_symbol(symbol):
            continue
        seen_symbols.add(symbol)

        quote_type = (quote.get("quoteType") or quote.get("typeDisp") or "").upper()
        if quote_type in _BLOCKED_QUOTE_TYPES:
            continue

        name = quote.get("longname") or quote.get("longName") or quote.get("shortname") or quote.get("shortName") or symbol
        rows.append({
            "symbol": symbol,
            "name": name,
            "quote_type": quote_type or "EQUITY",
        })

    return rows


def _yahoo_http_search(query, limit):
    """Direct Yahoo search API — works when yfinance.Search is blocked on cloud hosts."""
    params = urllib.parse.urlencode({
        "q": query,
        "quotesCount": limit * 2,
        "newsCount": 0,
    })
    req = urllib.request.Request(
        f"{_YAHOO_SEARCH_URL}?{params}",
        headers={"User-Agent": _YAHOO_UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode())
        return _parse_quotes(payload.get("quotes") or [], limit)
    except Exception as exc:
        logger.warning("Yahoo HTTP search failed for %r: %s", query, exc)
        return []


def _yfinance_search(query, limit):
    try:
        response = yf.Search(query, max_results=limit * 2, session=_SESSION)
        return _parse_quotes(response.quotes or [], limit)
    except Exception as exc:
        logger.warning("yfinance.Search failed for %r: %s", query, exc)
        return []


def _lookup_exact_symbol(symbol):
    """Fallback when search returns nothing but input looks like a ticker symbol."""
    try:
        info = yf.Ticker(symbol, session=_SESSION).info or {}
    except Exception as exc:
        logger.warning("Ticker info lookup failed for %s: %s", symbol, exc)
        return []

    resolved = (info.get("symbol") or symbol).upper()
    quote_type = (info.get("quoteType") or "").upper()
    if quote_type in _BLOCKED_QUOTE_TYPES:
        return []

    if not info.get("regularMarketPrice") and not info.get("currentPrice") and not info.get("previousClose"):
        return []

    name = info.get("longName") or info.get("shortName") or resolved
    return [{"symbol": resolved, "name": name, "quote_type": quote_type or "EQUITY"}]


def lookup_quote_type(symbol):
    """Resolve ETF vs EQUITY via Yahoo search — does not use .info."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        return "EQUITY"

    cached = _get_cached_rows(sym)
    if cached is not None:
        for row in cached:
            if row["symbol"] == sym:
                return row.get("quote_type") or "EQUITY"

    rows = _yahoo_http_search(sym, limit=8)
    if not rows:
        rows = _yfinance_search(sym, limit=8)
    if rows:
        _set_cached_rows(sym, rows)

    for row in rows:
        if row["symbol"] == sym:
            return row.get("quote_type") or "EQUITY"
    return "EQUITY"


def _fetch_rows(query, limit):
    """
    Get symbol+name rows — from cache if fresh, otherwise search providers.
    """
    alias = resolve_search_query(query)
    search_q = alias or query

    cached = _get_cached_rows(search_q)
    if cached is not None:
        return cached[:limit]

    rows = _yfinance_search(search_q, limit)
    if not rows:
        rows = _yahoo_http_search(search_q, limit)

    symbol_guess = search_q.strip().upper()
    if not rows and _TICKER_RE.match(symbol_guess):
        if is_index_symbol(symbol_guess):
            rows = []
        else:
            rows = _lookup_exact_symbol(symbol_guess)

    _set_cached_rows(search_q, rows)
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

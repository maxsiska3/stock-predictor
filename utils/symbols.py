# utils/symbols.py — watchlist symbol rules (indices vs tradable ETFs)

# Yahoo index tickers → ETF proxies used for benchmarks and watchlist prices.
INDEX_TO_ETF = {
    "^GSPC": "SPY",
    "GSPC": "SPY",
    "^SPX": "SPY",
    "SPX": "SPY",
    "^DJI": "DIA",
    "DJI": "DIA",
    "^DJIA": "DIA",
    "^IXIC": "QQQ",
    "IXIC": "QQQ",
    "^NDX": "QQQ",
    "NDX": "QQQ",
}

# Common search phrases → ETF ticker (tradable price, not index level).
SEARCH_ALIASES = {
    "s&p": "SPY",
    "s&p 500": "SPY",
    "s and p": "SPY",
    "s and p 500": "SPY",
    "sp500": "SPY",
    "sp 500": "SPY",
    "dow jones": "DIA",
    "dow jones industrial": "DIA",
    "dow jones industrial average": "DIA",
    "nasdaq": "QQQ",
    "nasdaq 100": "QQQ",
    "nasdaq composite": "QQQ",
}


def is_index_symbol(symbol):
    """True for Yahoo index tickers (^GSPC, ^DJI) and known index aliases."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        return False
    if sym.startswith("^"):
        return True
    return sym in INDEX_TO_ETF


def etf_for_index(symbol):
    """Return the ETF proxy for an index symbol, or None."""
    sym = str(symbol or "").strip().upper()
    return INDEX_TO_ETF.get(sym)


def index_rejection_message(symbol):
    """User-facing reason when an index symbol is blocked from the watchlist."""
    sym = str(symbol or "").strip().upper()
    etf = etf_for_index(sym)
    if etf:
        return f"Index levels can't be tracked — use {etf} (the ETF) for tradable prices"
    if sym.startswith("^"):
        return "Market indexes can't be added — search for an ETF instead (e.g. SPY, DIA, QQQ)"
    return "This symbol isn't supported on the watchlist"


def resolve_search_query(query):
    """Map friendly names like 'S&P 500' to an ETF ticker for search."""
    key = str(query or "").strip().lower()
    return SEARCH_ALIASES.get(key)

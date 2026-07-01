# utils/symbols.py — helpers for recognizing market index tickers (^GSPC, ^DJI, ...)
#
# Indexes are legitimate watchlist entries (e.g. tracking the real S&P 500 level
# instead of the SPY ETF price) — this module only tags them so the UI can label
# and group them correctly. It does NOT block or rewrite them.


def is_index_symbol(symbol):
    """True for Yahoo index tickers, which always start with '^' (e.g. ^GSPC, ^DJI)."""
    sym = str(symbol or "").strip().upper()
    return sym.startswith("^")

# utils/yahoo_links.py — Yahoo Finance quote URLs for attribution links

import urllib.parse


def yahoo_quote_url(symbol):
    """Link a ticker to its Yahoo Finance quote page (required by Yahoo attribution policy)."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        return "https://finance.yahoo.com/"
    return f"https://finance.yahoo.com/quote/{urllib.parse.quote(sym, safe='')}"

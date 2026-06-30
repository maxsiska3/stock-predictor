# utils/refresh.py — background market data refresh
#
# Runs in a daemon thread so page loads usually hit warm per-ticker cache.
# Refreshes the union of all users' watchlists plus fund holdings every 60s.

import logging
import threading
import time

from utils.config import get_fund_tickers
from utils.db import get_all_watchlist_symbols
from utils.market import fetch_market_data

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SEC = 60


def get_union_fetch_tickers():
    """All symbols any user tracks, plus hardcoded fund tickers."""
    symbols = set(get_all_watchlist_symbols())
    symbols.update(get_fund_tickers())
    return sorted(symbols)


def _refresh_loop():
    while True:
        try:
            tickers = get_union_fetch_tickers()
            if tickers:
                fetch_market_data(tickers)
                logger.info("Market cache refreshed for %d tickers", len(tickers))
        except Exception:
            logger.exception("Background market refresh failed")
        time.sleep(REFRESH_INTERVAL_SEC)


def start_background_refresh():
    """Start the daemon refresh thread once per process."""
    thread = threading.Thread(target=_refresh_loop, name="market-refresh", daemon=True)
    thread.start()

# utils/refresh.py — background market data refresh
#
# Runs in a daemon thread so page loads always hit a warm per-ticker cache —
# the web request path never blocks on yfinance (see fetch_market_data wait=False).
# Refreshes the union of all users' watchlists, dynamic fund holdings, and
# the benchmark index ETFs every cycle.

import logging
import threading
import time

from utils.config import BENCHMARK_TICKERS
from utils.db import get_all_fund_symbols, get_all_watchlist_symbols
from utils.market import fetch_market_data

logger = logging.getLogger(__name__)

# Stay comfortably under market._CACHE_TTL (90s) so rows are refreshed before
# they go stale — otherwise web requests would see "stale" rows every cycle.
REFRESH_INTERVAL_SEC = 60
# Give Gunicorn a moment to bind and pass the first health check before the
# initial yfinance burst.
STARTUP_DELAY_SEC = 15


def get_union_fetch_tickers():
    """All symbols any user tracks across watchlists and funds, plus index benchmarks."""
    symbols = set(get_all_watchlist_symbols())
    symbols.update(get_all_fund_symbols())
    symbols.update(BENCHMARK_TICKERS)
    return sorted(symbols)


def _refresh_loop():
    time.sleep(STARTUP_DELAY_SEC)
    while True:
        try:
            tickers = get_union_fetch_tickers()
            if tickers:
                fetch_market_data(tickers, wait=True)
                logger.info("Market cache refreshed for %d tickers", len(tickers))
        except Exception:
            logger.exception("Background market refresh failed")
        time.sleep(REFRESH_INTERVAL_SEC)


def start_background_refresh():
    """Start the daemon refresh thread once per process."""
    thread = threading.Thread(target=_refresh_loop, name="market-refresh", daemon=True)
    thread.start()

# utils/refresh.py — background market data refresh
#
# Runs in a daemon thread so page loads usually hit warm per-ticker cache.
# Refreshes the union of all users' watchlists, dynamic fund holdings, and
# SPY (always needed for the vs-S&P benchmark) every 60 seconds.

import logging
import os
import threading
import time

from utils.config import BENCHMARK_TICKERS
from utils.db import get_all_fund_symbols, get_all_watchlist_symbols
from utils.market import fetch_market_data

logger = logging.getLogger(__name__)

_HOSTED = bool(os.environ.get("RENDER") or os.environ.get("DATABASE_PATH", "").startswith("/data/"))
REFRESH_INTERVAL_SEC = 120 if _HOSTED else 60
# Let Gunicorn pass health checks before the first yfinance burst on Render.
STARTUP_DELAY_SEC = 60 if _HOSTED else 20


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
                fetch_market_data(tickers)
                logger.info("Market cache refreshed for %d tickers", len(tickers))
        except Exception:
            logger.exception("Background market refresh failed")
        time.sleep(REFRESH_INTERVAL_SEC)


def start_background_refresh():
    """Start the daemon refresh thread once per process."""
    thread = threading.Thread(target=_refresh_loop, name="market-refresh", daemon=True)
    thread.start()

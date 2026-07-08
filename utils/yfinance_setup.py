# utils/yfinance_setup.py — writable cache dir + optional curl_cffi session for yfinance

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
_configured = False
_session = None

_CACHE_DIR = Path(os.environ.get("YFINANCE_CACHE_DIR") or "/tmp/yfinance-cache")


def configure_yfinance():
    """Point yfinance's tz/cookie caches at a writable directory."""
    global _configured
    if _configured:
        return

    import yfinance as yf

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(_CACHE_DIR))
        logger.info("yfinance cache directory: %s", _CACHE_DIR)
    except OSError as exc:
        logger.warning("yfinance cache setup failed: %s", exc)

    _configured = True


def get_yf_session():
    """Shared curl_cffi session when available; otherwise yfinance's default."""
    global _session
    if _session is not None:
        return _session

    try:
        from curl_cffi import requests as creq
        _session = creq.Session(impersonate="chrome")
        logger.info("yfinance using curl_cffi impersonated session")
    except Exception as exc:
        logger.warning("curl_cffi unavailable, falling back to default session: %s", exc)
        _session = False

    return _session or None


def reset_yf_session():
    """Drop the cached session so the next get_yf_session() call builds a fresh one.

    A burst of requests (e.g. scanning the whole watchlist) can get Yahoo to start
    rejecting every request made through one session's cookies, even ones for
    tickers that would otherwise succeed. Once that happens the poisoned session
    never recovers on its own, but a brand-new session (fresh cookies) works
    immediately — so this is the recovery path callers use after a failed fetch.
    """
    global _session
    _session = None

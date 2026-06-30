# utils/yfinance_setup.py — writable cache dir + browser-impersonating session
#
# Yahoo blocks plain `requests`-based traffic from datacenter IPs (Render, Heroku,
# AWS, etc.) far more aggressively than it rate-limits real request volume — the
# block is largely based on TLS/HTTP fingerprint, not just call count. Routing
# yfinance through a curl_cffi session that impersonates a real Chrome browser
# avoids almost all of the "Too Many Requests" errors seen when hosted.

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
_configured = False
_session = None

# IMPORTANT: yf.set_tz_cache_location() also relocates yfinance's *cookie/crumb*
# cache (see yfinance/cache.py — set_cache_location sets Tz + Cookie + ISIN
# caches together). That cookie is what .info needs to authenticate with Yahoo.
# Previously this pointed at Render's persistent /data disk, so a single bad/
# blocked cookie cached during an earlier rate-limited deploy would survive
# every future redeploy forever — explaining why price data recovered but
# P/E, EPS, beta, and sector stayed permanently blank. Always use an ephemeral
# directory instead so a fresh cookie/crumb is negotiated on every restart.
_CACHE_DIR = Path(os.environ.get("YFINANCE_CACHE_DIR") or "/tmp/yfinance-cache")

# One-time cleanup: remove any cookie cache yfinance may have written to the
# persistent disk in earlier deploys, so it can never be reused again.
_STALE_CACHE_DIRS = [Path("/data/yfinance-cache")]


def _purge_stale_cookie_caches():
    for stale_dir in _STALE_CACHE_DIRS:
        for name in ("cookies.db", "cookies.db-wal", "cookies.db-shm"):
            stale_file = stale_dir / name
            try:
                if stale_file.exists():
                    stale_file.unlink()
                    logger.info("Removed stale yfinance cookie cache: %s", stale_file)
            except OSError as exc:
                logger.warning("Could not remove stale cookie cache %s: %s", stale_file, exc)


def configure_yfinance():
    """Point yfinance's tz/cookie caches at a fresh, ephemeral directory."""
    global _configured
    if _configured:
        return

    import yfinance as yf

    _purge_stale_cookie_caches()

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(_CACHE_DIR))
        logger.info("yfinance cache directory: %s", _CACHE_DIR)
    except OSError as exc:
        logger.warning("yfinance cache setup failed: %s", exc)

    _configured = True


def get_yf_session():
    """
    Shared curl_cffi session impersonating Chrome — pass to every yf.Ticker /
    yf.download / yf.Search call. Falls back to None (yfinance's default
    requests session) if curl_cffi isn't installed for some reason.
    """
    global _session
    if _session is not None:
        return _session

    try:
        from curl_cffi import requests as creq
        _session = creq.Session(impersonate="chrome")
        logger.info("yfinance using curl_cffi impersonated session")
    except Exception as exc:
        logger.warning("curl_cffi unavailable, falling back to default session: %s", exc)
        _session = False  # sentinel: "tried and failed" so we don't retry every call

    return _session or None

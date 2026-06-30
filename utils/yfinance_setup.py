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


def configure_yfinance():
    """Point yfinance timezone/cookie caches at a writable directory."""
    global _configured
    if _configured:
        return

    import yfinance as yf

    cache_dir = os.environ.get("YFINANCE_CACHE_DIR")
    if not cache_dir:
        candidates = []
        db_path = os.environ.get("DATABASE_PATH")
        if db_path:
            candidates.append(Path(db_path).parent / "yfinance-cache")
        candidates.extend([Path("/data/yfinance-cache"), Path("/tmp/yfinance-cache")])

        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                cache_dir = str(candidate)
                break
            except OSError:
                continue

    if cache_dir:
        try:
            yf.set_tz_cache_location(cache_dir)
            logger.info("yfinance cache directory: %s", cache_dir)
        except Exception as exc:
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

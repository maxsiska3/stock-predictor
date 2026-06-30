# utils/yfinance_setup.py — writable cache dir for yfinance on Render/containers

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
_configured = False


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

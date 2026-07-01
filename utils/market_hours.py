# utils/market_hours.py — NYSE regular-session awareness
#
# Wall-clock only (no holiday calendar, no network call) — good enough to tell
# "the market is closed right now" from "it might be open", which is what the
# dashboard needs to label prices honestly instead of implying they're live
# when they're really just the last close being re-confirmed on every refresh.

from datetime import datetime, time
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")
_OPEN = time(9, 30)
_CLOSE = time(16, 0)


def market_status(now=None):
    """Return 'open', 'closed', or 'weekend' for the NYSE regular session."""
    now_et = (now or datetime.now(_EASTERN)).astimezone(_EASTERN)
    if now_et.weekday() >= 5:
        return "weekend"
    if _OPEN <= now_et.time() < _CLOSE:
        return "open"
    return "closed"


def is_market_open(now=None):
    return market_status(now) == "open"


def market_status_label(now=None):
    status = market_status(now)
    if status == "open":
        return "Market open"
    if status == "weekend":
        return "Market closed (weekend)"
    return "Market closed"

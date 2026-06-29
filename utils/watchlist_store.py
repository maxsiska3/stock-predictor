# utils/watchlist_store.py — persisted watchlist (data/watchlist.json)
#
# Single source of truth for which tickers appear in the dashboard watchlist.
# Flask routes call these functions; market data fetching reads load_watchlist().

import json
import os
from pathlib import Path

import yfinance as yf

from utils.market import clear_cache

# Stored next to the project root, not in git (see .gitignore).
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WATCHLIST_PATH = DATA_DIR / "watchlist.json"

# yfinance batch fetches get slow above ~15–20 symbols; cap keeps UI responsive.
MAX_TICKERS = 25


class WatchlistError(Exception):
    """Raised when add/remove validation fails. status_code maps to HTTP 400."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _normalize_symbol(symbol):
    """Strip whitespace and uppercase so ' nvda ' and 'NVDA' match the same entry."""
    if symbol is None or not str(symbol).strip():
        raise WatchlistError("Ticker is required")
    return str(symbol).strip().upper()


def _normalize_list(tickers):
    """Uppercase, dedupe, and preserve first-seen order (used on load and save)."""
    seen = set()
    result = []
    for ticker in tickers:
        sym = _normalize_symbol(ticker)
        if sym not in seen:
            seen.add(sym)
            result.append(sym)
    return result


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _write_watchlist(tickers):
    """
    Write tickers to disk atomically: temp file first, then replace.
    If the process crashes mid-write, the old watchlist.json stays intact.
    """
    _ensure_data_dir()
    tmp_path = WATCHLIST_PATH.with_suffix(".json.tmp")
    payload = {"tickers": tickers}
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, WATCHLIST_PATH)


def save_watchlist(tickers):
    """Validate, normalize, and persist. Empty list is allowed."""
    normalized = _normalize_list(tickers)
    if len(normalized) > MAX_TICKERS:
        raise WatchlistError(f"Max {MAX_TICKERS} tickers")
    _write_watchlist(normalized)


def load_watchlist():
    """
    Read data/watchlist.json.
    - First run: create { "tickers": [] } and return [].
    - Bad data: re-save normalized form (fixes case/duplicates in file).
    """
    if not WATCHLIST_PATH.exists():
        _write_watchlist([])
        return []

    with open(WATCHLIST_PATH, encoding="utf-8") as f:
        data = json.load(f)

    tickers = data.get("tickers", [])
    if not isinstance(tickers, list):
        raise WatchlistError("Invalid watchlist file")

    normalized = _normalize_list(tickers) if tickers else []
    if normalized != tickers:
        _write_watchlist(normalized)
    return normalized


def _validate_ticker(symbol):
    """
    Confirm yfinance has recent price history for this symbol.
    Skipped by add_tickers when trusted_from_search=True (symbols already came from
    yfinance.Search, so a second round-trip would just slow things down).
    """
    try:
        hist = yf.Ticker(symbol).history(period="5d")
        return hist is not None and not hist.empty
    except Exception:
        return False


def add_tickers(symbols, trusted_from_search=True):
    """
    Batch add symbols selected from the search results modal.

    Args:
        symbols: list of ticker strings the user clicked in the modal.
        trusted_from_search: when True (the default for UI calls) the expensive per-symbol
            yfinance validation is skipped — the symbols already came from yfinance.Search
            so a second round-trip would just add several seconds of latency.
            Pass False for scripted / non-UI calls where you want full validation.

    Returns:
        {
            "tickers": [...],   # full list after add
            "added":   [...],
            "skipped": [{"symbol": "AAPL", "reason": "..."}],
            "failed":  [{"symbol": "ZZZZ", "reason": "..."}],
        }

    Skipped reasons: "Already in watchlist" | "Duplicate in request"
    Failed reasons:  "Ticker is required" | "Invalid ticker" | "Max 25 tickers"
    """
    if not symbols:
        raise WatchlistError("No tickers provided")

    current = load_watchlist()
    # current_set tracks saved + newly added symbols in this request (for duplicate checks).
    current_set = set(current)
    added, skipped, failed = [], [], []

    for raw in symbols:
        try:
            sym = _normalize_symbol(raw)
        except WatchlistError:
            failed.append({"symbol": str(raw), "reason": "Ticker is required"})
            continue

        if sym in current_set:
            # Distinguish already-saved vs two rows selected for same symbol in one POST.
            reason = "Already in watchlist" if sym in current else "Duplicate in request"
            skipped.append({"symbol": sym, "reason": reason})
            continue

        if len(current) + len(added) >= MAX_TICKERS:
            failed.append({"symbol": sym, "reason": f"Max {MAX_TICKERS} tickers"})
            continue

        # Only call yfinance when symbols are NOT trusted (e.g. scripted API calls).
        if not trusted_from_search and not _validate_ticker(sym):
            failed.append({"symbol": sym, "reason": "Invalid ticker"})
            continue

        added.append(sym)
        current_set.add(sym)

    updated = current + added

    # Only touch disk and market cache when at least one symbol was actually added.
    if added:
        save_watchlist(updated)
        clear_cache()

    return {
        "tickers": updated,
        "added": added,
        "skipped": skipped,
        "failed": failed,
    }


def remove_ticker(symbol):
    """
    Remove one symbol from the saved watchlist.
    Empty watchlist is allowed.

    Returns the updated ticker list.
    Raises WatchlistError if the symbol is not on the watchlist.
    """
    sym = _normalize_symbol(symbol)
    current = load_watchlist()

    if sym not in current:
        raise WatchlistError("Ticker not in watchlist")

    # List comprehension keeps remaining symbols in their original order.
    updated = [t for t in current if t != sym]
    save_watchlist(updated)
    clear_cache()
    return updated

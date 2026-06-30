# utils/position_store.py — per-user cost-basis positions in SQLite
#
# A position records how many shares the user owns at what average cost.
# These numbers are user-entered and not validated against live prices.

from utils.db import get_connection, utc_now_iso


class PositionError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_all_positions(user_id):
    """Return a dict of all positions keyed by symbol.

    Returns:
        {"AAPL": {"shares": 10.0, "avg_cost": 178.50, "purchased_at": "2024-01-15"}, ...}
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT symbol, shares, avg_cost, purchased_at FROM positions WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {
        row["symbol"]: {
            "shares": row["shares"],
            "avg_cost": row["avg_cost"],
            "purchased_at": row["purchased_at"],
        }
        for row in rows
    }


def upsert_position(user_id, symbol, shares, avg_cost, purchased_at=None):
    """Create or update a position. Overwrites existing entry.

    Args:
        user_id: owner
        symbol: ticker (normalized to upper case)
        shares: number of shares (must be > 0)
        avg_cost: average purchase price per share (must be > 0)
        purchased_at: ISO date string, optional

    Raises:
        PositionError: if shares or avg_cost are not positive numbers
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise PositionError("Symbol is required")

    try:
        shares = float(shares)
        avg_cost = float(avg_cost)
    except (TypeError, ValueError):
        raise PositionError("Shares and avg cost must be numbers")

    if shares <= 0:
        raise PositionError("Shares must be greater than 0")
    if avg_cost <= 0:
        raise PositionError("Average cost must be greater than 0")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO positions (user_id, symbol, shares, avg_cost, purchased_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, symbol) DO UPDATE SET
                shares       = excluded.shares,
                avg_cost     = excluded.avg_cost,
                purchased_at = excluded.purchased_at,
                updated_at   = excluded.updated_at
            """,
            (user_id, sym, shares, avg_cost, purchased_at, utc_now_iso()),
        )
        conn.commit()

    return {"symbol": sym, "shares": shares, "avg_cost": avg_cost, "purchased_at": purchased_at}


def delete_position(user_id, symbol):
    """Remove a position. No-op if it doesn't exist."""
    sym = str(symbol or "").strip().upper()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND symbol = ?",
            (user_id, sym),
        )
        conn.commit()

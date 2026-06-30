# utils/fund_store.py — per-user fund CRUD backed by SQLite
#
# A fund is a named group of tickers the user chooses. Each user can have
# multiple funds with any subset of their watchlist (or any valid ticker).

from utils.db import get_connection, utc_now_iso

MAX_FUNDS = 10
MAX_FUND_TICKERS = 30


class FundError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_user_funds(user_id):
    """Return all funds for a user with holdings (symbol, shares, avg_cost).

    Returns:
        [{"id": 1, "name": "My Fund", "holdings": [
            {"symbol": "AAPL", "shares": 10.0, "avg_cost": 178.5}, ...
        ]}, ...]
    """
    with get_connection() as conn:
        fund_rows = conn.execute(
            "SELECT id, name FROM user_funds WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ).fetchall()

        funds = []
        for f in fund_rows:
            holding_rows = conn.execute(
                """
                SELECT symbol, shares, avg_cost
                FROM fund_holdings WHERE fund_id = ? ORDER BY id ASC
                """,
                (f["id"],),
            ).fetchall()
            funds.append({
                "id": f["id"],
                "name": f["name"],
                "holdings": [
                    {
                        "symbol": h["symbol"],
                        "shares": h["shares"],
                        "avg_cost": h["avg_cost"],
                    }
                    for h in holding_rows
                ],
                # Flat ticker list — convenient for fetch pipeline
                "tickers": [h["symbol"] for h in holding_rows],
            })

    return funds


def create_fund(user_id, name, tickers):
    """Create a new named fund with an initial list of tickers.

    Args:
        user_id: owner
        name: display name for the fund (must be non-empty, unique per user)
        tickers: list of symbols to add immediately

    Returns:
        {"id": <id>, "name": ..., "tickers": [...]}

    Raises:
        FundError: if name is blank, already used, or too many funds
    """
    name = str(name or "").strip()
    if not name:
        raise FundError("Fund name is required")

    with get_connection() as conn:
        existing_count = conn.execute(
            "SELECT COUNT(*) FROM user_funds WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        if existing_count >= MAX_FUNDS:
            raise FundError(f"Maximum {MAX_FUNDS} funds per user")

        duplicate = conn.execute(
            "SELECT id FROM user_funds WHERE user_id = ? AND LOWER(name) = LOWER(?)",
            (user_id, name),
        ).fetchone()
        if duplicate:
            raise FundError(f"A fund named '{name}' already exists")

        cursor = conn.execute(
            "INSERT INTO user_funds (user_id, name, created_at) VALUES (?, ?, ?)",
            (user_id, name, utc_now_iso()),
        )
        fund_id = cursor.lastrowid

        # Add tickers, ignoring duplicates and bad symbols
        clean_tickers = _clean_tickers(tickers)[:MAX_FUND_TICKERS]
        for sym in clean_tickers:
            conn.execute(
                "INSERT OR IGNORE INTO fund_holdings (fund_id, symbol) VALUES (?, ?)",
                (fund_id, sym),
            )
        conn.commit()

    return {"id": fund_id, "name": name, "tickers": clean_tickers, "holdings": [
        {"symbol": s, "shares": None, "avg_cost": None} for s in clean_tickers
    ]}


def update_fund(fund_id, user_id, name, tickers):
    """Rename a fund and sync its holdings to the given ticker list."""
    name = str(name or "").strip()
    if not name:
        raise FundError("Fund name is required")

    clean = _clean_tickers(tickers)
    if len(clean) > MAX_FUND_TICKERS:
        raise FundError(f"Maximum {MAX_FUND_TICKERS} tickers per fund")

    with get_connection() as conn:
        fund = conn.execute(
            "SELECT id FROM user_funds WHERE id = ? AND user_id = ?",
            (fund_id, user_id),
        ).fetchone()
        if not fund:
            raise FundError("Fund not found", 404)

        duplicate = conn.execute(
            "SELECT id FROM user_funds WHERE user_id = ? AND LOWER(name) = LOWER(?) AND id != ?",
            (user_id, name, fund_id),
        ).fetchone()
        if duplicate:
            raise FundError(f"A fund named '{name}' already exists")

        conn.execute(
            "UPDATE user_funds SET name = ? WHERE id = ?", (name, fund_id)
        )

        current_rows = conn.execute(
            "SELECT symbol FROM fund_holdings WHERE fund_id = ? ORDER BY id ASC",
            (fund_id,),
        ).fetchall()
        current = {r["symbol"] for r in current_rows}
        desired = set(clean)

        for sym in current - desired:
            conn.execute(
                "DELETE FROM fund_holdings WHERE fund_id = ? AND symbol = ?",
                (fund_id, sym),
            )

        for sym in desired - current:
            conn.execute(
                "INSERT OR IGNORE INTO fund_holdings (fund_id, symbol) VALUES (?, ?)",
                (fund_id, sym),
            )

        conn.commit()

        rows = conn.execute(
            """
            SELECT symbol, shares, avg_cost
            FROM fund_holdings WHERE fund_id = ? ORDER BY id ASC
            """,
            (fund_id,),
        ).fetchall()

    return {
        "id": fund_id,
        "name": name,
        "tickers": [r["symbol"] for r in rows],
        "holdings": [
            {"symbol": r["symbol"], "shares": r["shares"], "avg_cost": r["avg_cost"]}
            for r in rows
        ],
    }


def rename_fund(fund_id, user_id, new_name):
    """Rename a fund. Raises FundError if not found or name already in use."""
    new_name = str(new_name or "").strip()
    if not new_name:
        raise FundError("Fund name is required")

    with get_connection() as conn:
        fund = conn.execute(
            "SELECT id FROM user_funds WHERE id = ? AND user_id = ?",
            (fund_id, user_id),
        ).fetchone()
        if not fund:
            raise FundError("Fund not found", 404)

        duplicate = conn.execute(
            "SELECT id FROM user_funds WHERE user_id = ? AND LOWER(name) = LOWER(?) AND id != ?",
            (user_id, new_name, fund_id),
        ).fetchone()
        if duplicate:
            raise FundError(f"A fund named '{new_name}' already exists")

        conn.execute(
            "UPDATE user_funds SET name = ? WHERE id = ?", (new_name, fund_id)
        )
        conn.commit()


def add_tickers_to_fund(fund_id, user_id, tickers):
    """Append tickers to an existing fund. Returns updated ticker list.

    Raises:
        FundError: if fund not found or over the ticker limit
    """
    with get_connection() as conn:
        fund = conn.execute(
            "SELECT id FROM user_funds WHERE id = ? AND user_id = ?",
            (fund_id, user_id),
        ).fetchone()
        if not fund:
            raise FundError("Fund not found", 404)

        current_count = conn.execute(
            "SELECT COUNT(*) FROM fund_holdings WHERE fund_id = ?", (fund_id,)
        ).fetchone()[0]

        clean = _clean_tickers(tickers)
        remaining_slots = MAX_FUND_TICKERS - current_count
        if remaining_slots <= 0:
            raise FundError(f"Fund already has the maximum of {MAX_FUND_TICKERS} tickers")

        added = []
        for sym in clean[:remaining_slots]:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO fund_holdings (fund_id, symbol) VALUES (?, ?)",
                    (fund_id, sym),
                )
                added.append(sym)
            except Exception:
                pass

        conn.commit()

        rows = conn.execute(
            "SELECT symbol FROM fund_holdings WHERE fund_id = ? ORDER BY id ASC",
            (fund_id,),
        ).fetchall()

    return [r["symbol"] for r in rows]


def remove_ticker_from_fund(fund_id, user_id, symbol):
    """Remove one ticker from a fund.

    Returns:
        Updated ticker list for the fund.
    """
    sym = str(symbol or "").strip().upper()
    with get_connection() as conn:
        fund = conn.execute(
            "SELECT id FROM user_funds WHERE id = ? AND user_id = ?",
            (fund_id, user_id),
        ).fetchone()
        if not fund:
            raise FundError("Fund not found", 404)

        conn.execute(
            "DELETE FROM fund_holdings WHERE fund_id = ? AND symbol = ?",
            (fund_id, sym),
        )
        conn.commit()

        rows = conn.execute(
            "SELECT symbol FROM fund_holdings WHERE fund_id = ? ORDER BY id ASC",
            (fund_id,),
        ).fetchall()

    return [r["symbol"] for r in rows]


def upsert_fund_holding_position(fund_id, user_id, symbol, shares, avg_cost):
    """Set shares and average cost for one ticker inside a fund."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise FundError("Symbol is required")

    try:
        shares = float(shares)
        avg_cost = float(avg_cost)
    except (TypeError, ValueError):
        raise FundError("Shares and avg cost must be numbers")

    if shares <= 0:
        raise FundError("Shares must be greater than 0")
    if avg_cost <= 0:
        raise FundError("Average cost must be greater than 0")

    with get_connection() as conn:
        fund = conn.execute(
            "SELECT id FROM user_funds WHERE id = ? AND user_id = ?",
            (fund_id, user_id),
        ).fetchone()
        if not fund:
            raise FundError("Fund not found", 404)

        holding = conn.execute(
            "SELECT id FROM fund_holdings WHERE fund_id = ? AND symbol = ?",
            (fund_id, sym),
        ).fetchone()
        if not holding:
            raise FundError(f"{sym} is not in this fund")

        conn.execute(
            "UPDATE fund_holdings SET shares = ?, avg_cost = ? WHERE fund_id = ? AND symbol = ?",
            (shares, avg_cost, fund_id, sym),
        )
        conn.commit()

    return {"symbol": sym, "shares": shares, "avg_cost": avg_cost}


def clear_fund_holding_position(fund_id, user_id, symbol):
    """Remove shares/cost for one fund holding (ticker stays in the fund)."""
    sym = str(symbol or "").strip().upper()
    with get_connection() as conn:
        fund = conn.execute(
            "SELECT id FROM user_funds WHERE id = ? AND user_id = ?",
            (fund_id, user_id),
        ).fetchone()
        if not fund:
            raise FundError("Fund not found", 404)

        conn.execute(
            "UPDATE fund_holdings SET shares = NULL, avg_cost = NULL WHERE fund_id = ? AND symbol = ?",
            (fund_id, sym),
        )
        conn.commit()


def delete_fund(fund_id, user_id):
    """Permanently delete a fund and all its holdings."""
    with get_connection() as conn:
        fund = conn.execute(
            "SELECT id FROM user_funds WHERE id = ? AND user_id = ?",
            (fund_id, user_id),
        ).fetchone()
        if not fund:
            raise FundError("Fund not found", 404)
        # fund_holdings cascade deletes automatically via FK
        conn.execute("DELETE FROM user_funds WHERE id = ?", (fund_id,))
        conn.commit()


def _clean_tickers(tickers):
    """Normalize and deduplicate a list of symbols."""
    seen = set()
    result = []
    for raw in (tickers or []):
        sym = str(raw or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            result.append(sym)
    return result

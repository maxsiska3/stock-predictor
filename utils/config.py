# utils/config.py — shared app constants (imported by app, market refresh, etc.)

# Hardcoded fund definitions until Phase 1.2 (dynamic user-created funds).
FUNDS = [
    {"name": "Max's Fund", "tickers": ["ACN", "AAPL", "AMZN", "BRK-B", "NVDA", "JPM"]},
    {"name": "Excelsior Fund", "tickers": ["AMD", "ORCL", "MU", "PLTR"]},
]


def get_fund_tickers():
    """All tickers referenced by hardcoded funds."""
    return {t for f in FUNDS for t in f["tickers"]}

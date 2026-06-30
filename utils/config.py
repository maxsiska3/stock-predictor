# utils/config.py — shared app constants

# Index ETFs always fetched for fund benchmark comparisons.
BENCHMARK_TICKERS = ["SPY", "DIA", "QQQ"]

# Keys used by the vs-index column dropdown (localStorage + data attributes).
BENCHMARK_OPTIONS = [
    {"key": "spy", "label": "S&P 500", "short": "S&P", "ticker": "SPY"},
    {"key": "dow", "label": "Dow Jones", "short": "Dow", "ticker": "DIA"},
    {"key": "nasdaq", "label": "NASDAQ", "short": "NASDAQ", "ticker": "QQQ"},
]

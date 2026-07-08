import yfinance as yf

from utils.yfinance_setup import configure_yfinance, get_yf_session

configure_yfinance()


def fetch_sector(ticker: str) -> str:
    try:
        session = get_yf_session()
        stock = yf.Ticker(ticker, session=session) if session else yf.Ticker(ticker)
        info = stock.info or {}

        sector = info.get("sector")
        if isinstance(sector, str) and sector.strip():
            return sector.strip()

        industry = info.get("industry")
        if isinstance(industry, str) and industry.strip():
            return industry.strip()

        return "Unknown"
    except Exception:
        return "Unknown"

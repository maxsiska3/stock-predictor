# MaxAlpha Terminal

A live stock market dashboard with next-day direction predictions powered by a trained RandomForest model. Built as a summer 2026 learning project.

## What it does

- Displays a live watchlist of 15 tickers with real-time price, change, and volume
- Predicts whether each stock will go up or down the next trading day using a trained ML model
- Shows top gainers, losers, most active stocks, and highest-confidence predictions in a side panel
- Groups tickers into funds and shows aggregate prediction confidence per fund
- Auto-refreshes data every 60 seconds without a page reload

## Tech Stack

- Python, pandas, scikit-learn — ML pipeline and feature engineering
- Flask + Jinja2 — web server and templating
- yfinance — live and historical market data
- RandomForest — trained classifier for next-day direction prediction

## Project Structure

```
app.py                  — Flask routes, data assembly, template rendering
utils/
  market.py             — batch market data fetching and 60s cache
  predict.py            — loads trained model and runs predictions
  features.py           — feature engineering (RSI, MACD, Bollinger Bands, etc.)
model/
  trained_model.pkl     — trained RandomForest classifier
  scaler.pkl            — fitted StandardScaler for feature normalization
templates/
  landing-screen.html   — main dashboard UI
  index.html            — legacy single-ticker prediction form
```

## ML Features

The model is trained on the following technical indicators computed from daily OHLCV data:

- pct_change, volatility, volume_change, high_low_change, gap
- RSI, MACD, Bollinger Bands position

## Running Locally

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5001

## Data Notes

- Price data is fetched via yfinance in two batch calls per refresh cycle — one daily (for yesterday's close) and one 1-minute intraday (for live price and volume)
- Data is cached for 60 seconds to stay within yfinance free-tier rate limits
- Outside market hours, the dashboard falls back to the most recent daily close price

## Status

In progress — summer 2026 learning project by a CS student

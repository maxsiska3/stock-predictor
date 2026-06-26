# Kouros

**Bringing data to life**

A live stock market dashboard with next-day direction predictions powered by a trained RandomForest model. Built as a summer 2026 learning project.

## What it does

- Displays a live watchlist of 15 tickers with real-time price, change, volume, and technical indicators
- Predicts whether each stock will go up or down the next trading day using a trained ML model
- Shows top gainers, losers, most active stocks, and highest-confidence predictions in a side panel
- Aggregates holdings into funds with portfolio-level metrics and prediction outlook
- Three UI themes: **Light**, **Dark**, and **Kouros** (signature gold-on-navy brand theme)

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
  landing-screen.html   — main Kouros dashboard UI
  index.html            — legacy single-ticker prediction form
static/
  theme.css             — Kouros design system and theme variables
  theme.js              — theme switcher (Light / Dark / Kouros)
get_predictions.py      — CLI script to batch-run predictions on 50 tickers
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

## Themes

Click the **⚙** icon in the header to switch themes. Your choice is saved in `localStorage` and persists across sessions. Default theme is **Kouros**.

| Theme | Description |
|-------|-------------|
| Light | Clean off-white workspace with blue accents |
| Dark | Low-light charcoal UI |
| Kouros | Signature navy + gold brand theme |

## Data Notes

- Price data is fetched via yfinance in batch calls per refresh cycle (daily, intraday, and 1y history)
- Data is cached for 60 seconds to stay within yfinance free-tier rate limits
- Outside market hours, the dashboard falls back to the most recent daily close price

## Status

In progress — summer 2026 learning project

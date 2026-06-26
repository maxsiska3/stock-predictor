# Kouros

**Bringing data to life**

A live stock market dashboard with next-day direction predictions powered by a trained RandomForest model. Built as a summer 2026 learning project.

---

## Overview

Kouros pulls live market data for a watchlist of tickers, surfaces technical indicators and fundamentals, and runs a trained ML classifier to predict whether each stock will move up or down the next trading day. Holdings can be grouped into funds with portfolio-level metrics and an aggregated prediction outlook.

The UI is a single-page Flask dashboard with a unified 18-column grid for watchlist and funds tables, a movers & predictions sidebar, and a three-theme design system (Light, Dark, Kouros).

---

## Features

### Watchlist
- Live price, change %, dollar change, and volume for 15 tickers
- 52-week high/low, P/E, EPS, RSI, Bollinger position, volatility, MACD, beta, and sector
- Next-day prediction badge (direction + model confidence)
- Shared column grid aligned with the funds table

### Funds
- Hardcoded portfolios aggregated from watchlist holdings
- Portfolio change %, dollar change, total value, top/worst performer
- Tomorrow outlook (e.g. `4/6 up`), average technicals, dominant sector
- Aggregated prediction direction and average confidence

### Movers & Predictions sidebar
- Top 5 predicted up / predicted down (ranked by confidence)
- Top gainers, losers, and most active by volume

### Branding & themes
- **Kouros** signature theme (navy + gold) as default
- Light and Dark workspace themes via header gear menu
- Theme preference persisted in `localStorage`
- Typography: [Marcellus SC](https://fonts.google.com/specimen/Marcellus+SC) (display) + [Archivo](https://fonts.google.com/specimen/Archivo) (UI)
- Logo assets: statue mark, K monogram, SVG favicon

---

## Tech stack

| Layer | Tools |
|-------|-------|
| Backend | Python, Flask, Jinja2 |
| ML | scikit-learn, pandas, joblib |
| Data | yfinance (batch downloads, 60s cache) |
| Frontend | HTML templates, CSS custom properties, vanilla JS |

---

## ML pipeline

The RandomForest classifier is trained on daily OHLCV features:

- `pct_change`, `volatility`, `volume_change`, `high_low_change`, `gap`
- RSI, MACD, Bollinger Bands position

Trained artifacts live in `model/`:

- `trained_model.pkl` — fitted classifier
- `scaler.pkl` — `StandardScaler` for feature normalization

Feature engineering is shared between training (`explore.py`) and inference (`utils/features.py`).

---

## Project structure

```
app.py                      Flask routes, fund aggregation, Jinja filters
utils/
  market.py                 Batch yfinance fetching + 60s cache
  predict.py                Load model/scaler, run predictions
  features.py               Technical indicator computation
model/
  trained_model.pkl
  scaler.pkl
templates/
  landing-screen.html       Main dashboard
  index.html                Legacy single-ticker prediction form
static/
  styles.css                Design system + theme variables
  theme.js                  Theme switcher (Light / Dark / Kouros)
  kouros-mark.svg           Logo figure silhouette
  kouros-k.svg              K monogram
  favicon.svg
get_predictions.py          CLI — batch predictions for 50 tickers
explore.py                  Model training notebook/script (not used at runtime)
```

---

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5001**

> First load can take 15–20 seconds while yfinance fetches history and the model runs per ticker.

### CLI predictions

```bash
python get_predictions.py
```

Runs next-day predictions across a batch of tickers and prints results to the terminal.

---

## API

| Endpoint | Description |
|----------|-------------|
| `GET /` | Full dashboard (HTML) |
| `GET /api/market-data` | JSON watchlist, mover groups, prediction groups |
| `POST /predict` | Legacy form endpoint for single-ticker prediction |

---

## Themes

Click the **⚙** icon in the header to switch themes. Choice is saved under `kouros-theme` in `localStorage`.

| Theme | Background | Accent | Description |
|-------|------------|--------|-------------|
| **Kouros** | `#0a0f1e` | `#c9a84c` | Default — navy + gold brand theme |
| Light | `#f4f3ef` | `#2f6df6` | Clean off-white workspace |
| Dark | `#0f1115` | `#4d86ff` | Low-light charcoal UI |

---

## Data notes

- Prices come from yfinance batch calls (2d daily, 1d intraday, 1y history per refresh)
- Responses are cached for **60 seconds** to respect free-tier rate limits
- Outside market hours, intraday data falls back to the most recent daily close
- Fund values use equal **$10k notional** per holding for portfolio estimates

---

## Roadmap

- [ ] Live DOM updates from `/api/market-data` polling (no full page reload)
- [ ] Add / remove tickers and funds from the UI
- [ ] Day graph sparklines in watchlist rows
- [ ] Heat map view

---

## Status

In progress — summer 2026 learning project. Not financial advice.

## License

Personal learning project. Use at your own discretion.

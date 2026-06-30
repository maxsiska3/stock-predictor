# Kouros

**Bringing data to life**

A live stock market dashboard with next-day direction predictions powered by a trained RandomForest model. Built as a summer 2026 learning project.

---

## Overview

Kouros pulls live market data for a personal watchlist, surfaces technical indicators, and runs a trained ML classifier to predict whether each stock will move up or down the next trading day. Holdings can be grouped into funds with portfolio-level metrics and an aggregated prediction outlook.

The UI is a single-page Flask dashboard with a unified 18-column grid for watchlist and fund tables, a movers & predictions sidebar, and a three-theme design system (Light, Dark, Kouros). The watchlist is fully editable — add or remove tickers at any time through a live search modal without touching any code.

---

## Features

### Dynamic watchlist
- Starts empty; add any stock or ETF by searching by symbol or company name
- Live search powered by yfinance with 5-minute result caching — results appear as you type
- Click any result row (or the keyboard) to select; select multiple and add in one batch
- Remove individual tickers with the × button on row hover
- Watchlist is persisted server-side in `data/watchlist.json` with atomic writes to prevent corruption
- Up to 25 tickers; duplicate and bounds validation on every add

### Watchlist table
- Live price, change %, dollar change, and volume
- 52-week high/low, RSI, Bollinger position, volatility, and MACD
- Next-day prediction badge: direction arrow + model confidence to two decimal places
- Aligned with the funds table on a shared 18-column grid

### Funds
- Portfolios defined in code and aggregated from watchlist holdings
- Portfolio change %, dollar change, total value, top/worst performer
- Tomorrow outlook (e.g. `4/6 up`) and average technicals
- Aggregated prediction direction and average confidence

### Movers & Predictions sidebar
- Top 5 predicted up / predicted down (ranked by confidence)
- Top gainers, losers, and most active by volume

### Branding & themes
- **Kouros** signature theme (navy + gold) as default
- Light and Dark workspace themes via header gear menu
- Theme preference persisted in `localStorage`
- Typography: [Marcellus SC](https://fonts.google.com/specimen/Marcellus+SC) (display) + [Archivo](https://fonts.google.com/specimen/Archivo) (UI)
- Logo assets: Greek statue silhouette, K monogram, SVG favicon

---

## Tech stack

| Layer | Tools |
|-------|-------|
| Backend | Python, Flask, Jinja2 |
| ML | scikit-learn, pandas, joblib |
| Data | yfinance (batch downloads + in-memory caching) |
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
app.py                        Flask routes, fund aggregation, Jinja filters, watchlist & search API
utils/
  market.py                   Batch yfinance fetching with TTL cache keyed by ticker set
  predict.py                  Load model/scaler, run predictions
  features.py                 Technical indicator computation
  watchlist_store.py          Persistent watchlist — load/save/add/remove + validation
  ticker_search.py            Live ticker search via yfinance with 5-min result cache
model/
  trained_model.pkl
  scaler.pkl
data/
  watchlist.json              User's watchlist (git-ignored, created on first run)
  watchlist.example.json      Example empty watchlist for reference
templates/
  landing-screen.html         Main dashboard
  index.html                  Legacy single-ticker prediction form
static/
  styles.css                  Design system, theme variables, modal styles
  theme.js                    Theme switcher (Light / Dark / Kouros)
  dashboard.js                Watchlist modal — search, select, add, remove
  kouros-mark.svg             Logo — Greek statue silhouette
  kouros-k.svg                K monogram
  favicon.svg
get_predictions.py            CLI — batch predictions for 50 tickers
explore.py                    Model training script (not used at runtime)
```

---

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5001**

> First load takes a few seconds while yfinance fetches history and the model runs per ticker. The watchlist starts empty — use the **+ Add Ticker** button to add your first symbols.

### CLI predictions

```bash
python get_predictions.py
```

Runs next-day predictions across a batch of tickers and prints results to the terminal.

---

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | `GET` | Full dashboard (HTML) |
| `/api/market-data` | `GET` | JSON — watchlist rows, mover groups, prediction groups |
| `/api/watchlist` | `GET` | Current watchlist as JSON |
| `/api/watchlist` | `POST` | Batch add tickers — body: `{ "tickers": ["AAPL", "MSFT"] }` |
| `/api/watchlist` | `DELETE` | Remove one ticker — body: `{ "ticker": "AAPL" }` |
| `/api/tickers/search` | `GET` | Live ticker search — query: `?q=apple` |
| `/predict` | `POST` | Legacy form endpoint for single-ticker prediction |

### Watchlist API response shape

**POST `/api/watchlist`**
```json
{
  "tickers": ["AAPL", "MSFT"],
  "added":   ["MSFT"],
  "skipped": [{ "symbol": "AAPL", "reason": "Already in watchlist" }],
  "failed":  []
}
```

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
- Market data is cached for **60 seconds**, keyed by the current set of tickers
- Ticker search results are cached for **5 minutes** per query
- Outside market hours, intraday data falls back to the most recent daily close
- Fund values use equal **$10k notional** per holding for portfolio estimates
- `data/watchlist.json` is git-ignored — each user has their own local watchlist

---

## Roadmap

- [x] Dynamic watchlist — add/remove any ticker from the UI
- [x] Live ticker search with company names
- [x] Persistent watchlist with atomic file writes
- [x] Three-theme design system (Light, Dark, Kouros)
- [ ] Day graph sparklines in watchlist rows
- [ ] Live DOM updates from `/api/market-data` polling (no full page reload)
- [ ] Heat map view

---

## Status

In progress — summer 2026 learning project. Not financial advice.

## License

Personal learning project. Use at your own discretion.

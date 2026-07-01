# Kouros

**Bringing data to life**

A multi-user portfolio tracker with next-day ML direction signals, live prices, and per-account funds — built as a summer 2026 learning project. Full product plan and history lives in [ROADMAP.md](ROADMAP.md).

---

## Overview

Kouros is a hosted Flask dashboard where each account has its own watchlist, positions, and funds, all backed by SQLite. It pulls live market data, surfaces technical indicators, and runs a trained RandomForest classifier to predict whether each symbol will move up or down the next trading day. Holdings roll up into user-created funds with portfolio-level metrics and an aggregated outlook.

The UI is a single-page dashboard with a shared 22-column grid across the watchlist and funds tables, a movers & predictions sidebar, and a three-theme design system (Kouros, Light, Dark). Prices refresh in the background every 60 seconds and poll into the page live — no reload required.

---

## Features

### Accounts
- Register / login / logout (Flask-Login + bcrypt password hashing)
- All data — watchlist, positions, funds — scoped per user in SQLite

### Dynamic watchlist
- Add any stock, ETF, **or market index** (e.g. `^GSPC`, `^DJI`, `^IXIC`) by searching symbol or company name
- Live search hits a direct Yahoo endpoint first (fast path) with a `yfinance.Search` fallback; results are cached 5 minutes per query
- Rows group automatically into **Stocks**, **ETFs**, and **Indexes** sections — classification is persisted per ticker so it survives Yahoo rate limits
- Remove a ticker with the × button on row hover; edit shares/avg cost by clicking the position cell
- Up to 25 tickers per user; duplicate and bounds validation on every add

### Watchlist & funds table (shared columns)
- Live price, change %, dollar change, volume, day-graph placeholder
- 52-week high/low, RSI, Bollinger position, volatility, MACD
- Next-day prediction badge — direction arrow + model confidence
- **vs Index** column — daily performance vs. S&P 500 / Dow / NASDAQ (dropdown synced across both tables via `localStorage`)
- Position columns — Shares, Avg Cost, Market Value, Gain/Loss, Return %
- Prices poll from `/api/market-data` every 60s and patch the DOM in place — the page never needs a manual refresh

### Positions
- Per-ticker shares + average cost, independent of watchlist or fund membership
- Market value, gain/loss, and return % computed live from the current price
- Click any Shares/Avg Cost cell (hover shows an edit hint) to open the position modal

### Funds
- Create, edit (✎), and delete funds via a search modal with holding chips
- Expandable rows show each holding using the same watchlist row layout
- Fund-level aggregates: value-weighted Chg %, $ Change, Total Value, top/worst performer, tomorrow's outlook (e.g. `4/6 up`), average technicals, and aggregated prediction confidence

### Movers & Predictions sidebar
- Top 5 predicted up / predicted down (ranked by confidence)
- Top gainers, losers, and most active by volume — scoped to your watchlist

### Branding & themes
- **Kouros** signature theme (navy + gold) as default; Light and Dark also available via the header gear menu
- Theme preference persisted in `localStorage`
- Typography: [Marcellus SC](https://fonts.google.com/specimen/Marcellus+SC) (display) + [Archivo](https://fonts.google.com/specimen/Archivo) (UI)

---

## Tech stack

| Layer | Tools |
|-------|-------|
| Backend | Python, Flask, Jinja2, Gunicorn |
| Auth | Flask-Login, bcrypt |
| Database | SQLite (WAL mode, commit retry, on Render's persistent disk) |
| ML | scikit-learn, pandas, joblib |
| Data | yfinance (`curl_cffi`-impersonated session), batch downloads + per-ticker cache, background refresh thread |
| Frontend | HTML templates, CSS custom properties, vanilla JS |

---

## ML pipeline

The RandomForest classifier is trained on daily OHLCV-derived features:

- `pct_change`, `volatility`, `volume_change`, `high_low_change`, `gap`
- RSI, MACD, Bollinger Bands position

Trained artifacts live in `model/`:

- `trained_model.pkl` — fitted classifier
- `scaler.pkl` — `StandardScaler` for feature normalization

Feature engineering is shared between training (`explore.py`) and inference (`utils/features.py`). Fundamentals (P/E, EPS, beta, sector) are intentionally **not** shown in the UI — Yahoo's `.info` endpoint is rate-limited on shared hosting and returns unreliable data on Render, so only price-derived technicals (which come from bulk `yf.download`, a much more reliable call) are surfaced.

---

## Project structure

```
app.py                        Flask routes, dashboard assembly, watchlist/fund/position APIs
utils/
  auth.py                     User model, login/register helpers
  config.py                   BENCHMARK_TICKERS, BENCHMARK_OPTIONS (vs-index column)
  db.py                       SQLite schema + migrations (WAL, commit retry)
  market.py                   Batch yfinance fetch, per-ticker cache, row builder, ML call-out
  predict.py                  Load model/scaler, run predictions
  features.py                 Technical indicator computation
  symbols.py                  Recognizes market index tickers (^GSPC, ^DJI, ...)
  watchlist_store.py          Per-user watchlist CRUD, quote-type persistence/backfill
  position_store.py           Per-user position CRUD (shares, avg cost)
  fund_store.py               Per-user fund CRUD + per-holding fund positions
  ticker_search.py            Live ticker/index search (direct Yahoo + yfinance fallback)
  refresh.py                  Background thread — refreshes the cache every 60s
  yfinance_setup.py           curl_cffi session + cache setup for Render
model/
  trained_model.pkl
  scaler.pkl
templates/
  landing-screen.html         Main dashboard (watchlist, funds, sidebar, modals)
  login.html / register.html  Auth screens
  partials/auth-brand-panel.html
  index.html                  Legacy single-ticker prediction form
static/
  styles.css                  Design system, theme variables, dashboard grid, modal styles
  theme.js                    Theme switcher (Kouros / Light / Dark)
  dashboard.js                Watchlist/fund/position modals, search, live price polling
  auth.css                    Login/register page styling
  kouros-mark.svg / kouros-k.svg / favicon.svg
data/
  kouros.db                   SQLite database (git-ignored, created on first run)
render.yaml                   Render deploy config (Gunicorn, persistent disk)
get_predictions.py            CLI — batch predictions for a ticker list
explore.py                    Model training script (not used at runtime)
```

---

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5001**, register an account, then use **+ Add Ticker** to build your watchlist.

> First load takes a few seconds while yfinance fetches history and the model runs per ticker.

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
| `/login`, `/register`, `/logout` | `GET/POST` | Auth screens and session handling |
| `/api/market-data` | `GET` | JSON — watchlist rows, mover groups, prediction groups (polled every 60s) |
| `/api/watchlist` | `GET` | Current watchlist as JSON |
| `/api/watchlist` | `POST` | Batch add tickers — body: `{ "tickers": [...], "quote_types": {...} }` |
| `/api/watchlist` | `DELETE` | Remove one ticker — body: `{ "ticker": "AAPL" }` |
| `/api/tickers/search` | `GET` | Live symbol/index search — query: `?q=apple` |
| `/api/funds` | `GET/POST` | List funds / create a fund |
| `/api/funds/<id>` | `PUT/DELETE` | Edit or delete a fund |
| `/api/funds/<id>/tickers` | `POST/DELETE` | Add/remove holdings on a fund |
| `/api/funds/<id>/holdings/<symbol>/position` | `PUT/DELETE` | Set or clear a fund holding's shares/avg cost |
| `/api/positions` | `GET/PUT` | List positions / upsert shares+avg cost for a symbol |
| `/api/positions/<symbol>` | `DELETE` | Clear a position |
| `/predict` | `POST` | Legacy form endpoint for single-ticker prediction |

### Watchlist add response shape

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

- Prices come from batched `yfinance` calls (5d daily, 1d intraday, 1y history) over a `curl_cffi`-impersonated session
- Market data is cached **90 seconds** per ticker; a background thread refreshes the full union of tracked symbols every **60 seconds**
- The dashboard polls `/api/market-data` every 60 seconds and patches price/change/volume/vs-index cells in place
- Ticker search results are cached 5 minutes per query
- Watchlist rows are split into **Stocks / ETFs / Indexes**; classification is persisted in SQLite so it survives Yahoo rate limits and doesn't need `.info`
- Static assets (`dashboard.js`, `styles.css`) are served with a `?v=<mtime>` cache-buster so deploys take effect without a hard refresh
- Fundamentals (P/E, EPS, beta, sector) are hidden in the UI — see [ML pipeline](#ml-pipeline)

---

## Roadmap

Kouros follows the phased plan in [ROADMAP.md](ROADMAP.md). Highlights:

**Shipped:** multi-user accounts, SQLite persistence, live search + watchlist (Stocks/ETFs/Indexes), positions, editable funds with per-holding tracking, vs-index benchmark column, 60s live price polling, sticky panel headers, three-theme design system.

**Up next:** stock/fund detail screens, prediction accuracy improvements (confidence threshold + calibration), a dedicated Predictions screen with hit-rate/miss-severity tracking, a Daily Digest screen, sidebar scope toggle (watchlist vs funds), sparklines, price alerts, and CSV export. See [ROADMAP.md](ROADMAP.md) for the full phase-by-phase plan.

---

## Status

In progress — summer 2026 learning project. Not financial advice.

## License

Personal learning project. Use at your own discretion.

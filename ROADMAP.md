# Kouros — Product Roadmap

**Vision:** A personal portfolio tracker with ML-powered next-day direction signals. Know what you own, track what it cost you, and get the model's read on what comes next.

---

## Current State (June 2026)

Kouros is a multi-user hosted dashboard with per-account data in SQLite.

**Done today:**

| Area | What's live |
|------|-------------|
| **Auth** | Register, login, logout (Flask-Login + bcrypt). Split login/register UI with Kouros branding. |
| **Data** | SQLite (`kouros.db`): users, watchlist, positions, user_funds, fund_holdings (with shares/avg_cost). |
| **Watchlist** | Live search add/remove modal, Stocks / ETFs sections, full data table + ML prediction badge. |
| **Positions** | Per-ticker shares, avg cost, mkt value, gain/loss, return % — click Shares to edit. |
| **Funds** | User-created funds via search modal; expandable rows with per-holding watchlist columns; fund-level position aggregates; benchmark dropdown (S&P / Dow / NASDAQ / Russell) shown under Chg %. |
| **Sidebar** | Movers & predictions + sector exposure chart (labeled *from your watchlist*). |
| **Infra** | Gunicorn, background 60s cache refresh, Render deploy config, robust yfinance batch fetching. |
| **Design** | Light / Dark / Kouros themes; shared 24-column grid for watchlist & funds alignment. |

**Not yet:** detail screens, digest, market pulse, movers/predictions scope toggle (watchlist vs funds), model improvements, sparklines, live polling.

---

## Phase 0 — Multi-user Foundation ✅

**Goal:** multiple people can log in, each with their own data. The app is stable and deployable.

**Status:** Complete (deploy to Render may need env/disk verification per environment).

---

#### 0.1 — User Auth ✅
- Email + password login (Flask-Login + bcrypt)
- Register / login / logout screens
- Session management
- Password stored as bcrypt hash, never plain text
- Protected routes — redirect to login if not authenticated

**Files:** `utils/auth.py`, `templates/login.html`, `templates/register.html`, `static/auth.css`, `templates/partials/auth-brand-panel.html`

---

#### 0.2 — Per-user Data Storage ✅
- `users` — id, email, password_hash, display_name, created_at
- `watchlist` — user_id, symbol, added_at
- `positions` — user_id, symbol, shares, avg_cost, purchased_at
- `user_funds` — user_id, name, created_at
- `fund_holdings` — fund_id, symbol, shares, avg_cost

**Files:** `utils/db.py`, `utils/watchlist_store.py`, `utils/position_store.py`, `utils/fund_store.py`

---

#### 0.3 — Production Server Config ✅
- Gunicorn + `render.yaml`
- `SECRET_KEY` from environment variable
- Background thread refreshing market data every 60s (`utils/refresh.py`)

---

#### 0.4 — Deploy to Render ✅ (configured)
- GitHub repo connected
- Env vars: `SECRET_KEY`, `DATABASE_PATH`
- Persistent disk for SQLite
- ML model artifacts committed (`model/*.pkl`)

---

## Phase 1 — Portfolio Tracker ✅

**Goal:** turn a watchlist into a real portfolio. Users track what they own and at what cost.

**Status:** Complete.

---

### 1.1 — Cost Basis & Positions ✅
- `positions` table — user_id, symbol, shares, avg_cost, purchased_at
- Watchlist columns: **Shares**, **Avg Cost**, **Market Value**, **Gain/Loss**, **Return %**
- Click Shares / Avg Cost to open position edit modal
- API: `GET/PUT/DELETE /api/positions`

**Files:** `utils/position_store.py`

---

### 1.2 — Dynamic Funds ✅
- User-created funds with name + ticker search (any symbol, not watchlist-only)
- `user_funds` + `fund_holdings` tables
- "+ Add Fund" modal, delete fund on row hover
- Expandable fund rows — each holding uses the same columns as the watchlist
- Per-holding shares/avg cost in fund (`fund_holdings.shares`, `fund_holdings.avg_cost`)
- Fund summary row aggregates portfolio totals in trailing position columns
- API: `GET/POST/DELETE /api/funds`, ticker add/remove, `PUT/DELETE .../holdings/<symbol>/position`

**Files:** `utils/fund_store.py`

---

### 1.3 — Sector Exposure Chart ✅
- Horizontal bar chart in sidebar
- Grouped by sector from watchlist holdings
- Subtitle: *from your watchlist*

---

### 1.4 — Fund vs Index Benchmark ✅
- Always fetch SPY, DIA, QQQ, IWM (`utils/config.py` → `BENCHMARK_TICKERS`)
- Funds panel header dropdown: S&P 500, Dow Jones, NASDAQ, Russell 2000
- Selected benchmark shown under fund **Chg %** (e.g. `+0.42% vs`); choice persisted in `localStorage`

---

## Phase 2 — Detail Screens

**Goal:** clicking a stock or fund opens a rich detail view instead of doing nothing.

---

### 2.1 — Stock Detail Screen
Route: `/stock/<ticker>`

Clicking any ticker in the watchlist or funds table navigates here.

**Layout:**
```
┌─────────────────────────────────────────────────┐
│  AAPL  Apple Inc.                  ▲ 94.2%      │
│  $213.40  +$2.10 (+0.99%)         Predicted Up  │
├─────────────────────────────────────────────────┤
│  PRICE CHART (1D / 1W / 1M / 3M / 1Y)          │
│  [interactive line chart — Chart.js or D3]      │
├──────────────┬──────────────────────────────────┤
│  FUNDAMENTALS│  TECHNICALS                      │
│  P/E   28.4  │  RSI          62.3               │
│  EPS   $6.43 │  MACD         0.84               │
│  Beta  1.21  │  Bollinger    0.71               │
│  52W H $237  │  Volatility   0.018              │
│  52W L $164  │                                  │
├──────────────┴──────────────────────────────────┤
│  PREDICTION HISTORY (last 14 days)              │
│  [mini chart — confidence over time]            │
│  Accuracy this month: 11/14 correct (78.6%)     │
├─────────────────────────────────────────────────┤
│  YOUR POSITION                                  │
│  42 shares @ $178.50 avg cost                   │
│  Market value: $8,962.80                        │
│  Gain: +$1,470.30 (+19.6%)                      │
├─────────────────────────────────────────────────┤
│  UPCOMING EARNINGS                              │
│  Next report: Jul 24 · After close              │
├─────────────────────────────────────────────────┤
│  NOTES                                          │
│  [editable text field — your personal notes]    │
└─────────────────────────────────────────────────┘
```

**New data needed:**
- Intraday chart data (already fetched, just not rendered)
- Historical chart data (already fetched for indicators)
- Prediction history log (see Phase 3.1)
- Earnings date — `yf.Ticker(symbol).calendar` (easy)
- Per-ticker notes — `notes` DB table: user_id, symbol, content, updated_at

---

### 2.2 — Fund Detail Screen
Route: `/fund/<fund_name>`

Clicking a fund name opens its detail view.

**Layout:**
```
┌─────────────────────────────────────────────────┐
│  Max's Fund                    ▲ 4/6 predicted  │
│  $61,420  +$820 (+1.35%)       vs S&P +0.8%     │
├─────────────────────────────────────────────────┤
│  PORTFOLIO CHART (performance over time)        │
│  [line chart — notional value over 1M/3M/1Y]    │
├─────────────────────────────────────────────────┤
│  HOLDINGS                                       │
│  [mini table — ticker, shares, value, gain/loss,│
│   today's change, prediction badge]             │
├─────────────────────────────────────────────────┤
│  SECTOR EXPOSURE                                │
│  Technology      58%  ████████████             │
│  Financials      22%  ████                     │
│  Healthcare      20%  ████                     │
├─────────────────────────────────────────────────┤
│  AVG METRICS                                    │
│  Avg RSI, Avg Beta, Avg EPS, Avg Volatility     │
│  Avg confidence, Dominant sector                │
└─────────────────────────────────────────────────┘
```

**Most of this data already exists in `build_funds()` — it just needs a dedicated screen.**

---

## Phase 3 — Model Improvement

**Goal:** increase overall prediction accuracy from the current 48.5% baseline toward a consistent 55–57%, and surface honest accuracy metrics to users.

---

### Current Baseline (as of June 2026)

| Confidence | Predictions | Hits | Hit Rate | vs Random |
|------------|------------|------|----------|-----------|
| 50–55% | 40 | 15 | 37.5% | −12.5% |
| 55–60% | 37 | 21 | 56.8% | +6.8% |
| 60–65% | 29 | 16 | 55.2% | +5.2% |
| 65+% | 24 | 11 | 45.8% | −4.2% |
| **Overall** | **130** | **63** | **48.5%** | **−1.5%** |

Key observations:
- The 55–65% range is the only zone where the model beats random — and by a real margin (~56%)
- The 50–55% bucket actively hurts overall accuracy and should not be shown to users
- The 65%+ bucket being *less* accurate than 60–65% is a calibration problem — the model is overconfident on certain setups that don't generalize
- Realistic target: **54–57% overall** with proper filtering and calibration

---

### 3.1 — Confidence Threshold Filter (quick win)

Stop showing or logging predictions below 55% confidence. The 50–55% bucket is anti-correlated with actual outcomes and is the single biggest drag on overall accuracy.

Before retraining anything, this alone takes the effective hit rate from 48.5% to ~56% — just by ignoring the noise.

```python
# utils/predict.py
MIN_CONFIDENCE = 0.55

def predict_stock(ticker):
    ...
    confidence = model.predict_proba(features)[0].max()
    if confidence < MIN_CONFIDENCE:
        return None  # no prediction shown below threshold
```

On the dashboard: show a neutral `—` badge instead of a direction when confidence is below threshold.

---

### 3.2 — Probability Calibration

The 65%+ bucket performing *worse* than 60–65% means the model's raw probability outputs don't reflect true likelihood. Apply `CalibratedClassifierCV` from scikit-learn after training so that a 65% confidence score actually corresponds to ~65% accuracy.

```python
from sklearn.calibration import CalibratedClassifierCV

base_model = RandomForestClassifier(...)
calibrated_model = CalibratedClassifierCV(base_model, method='isotonic', cv=5)
calibrated_model.fit(X_train, y_train)
```

This is a wrapper around the existing model — no architectural changes needed. Retrain and replace `model/trained_model.pkl`.

---

### 3.3 — Better Features

Current features are all price/volume derived (RSI, MACD, Bollinger, volatility). These are correlated with each other and well-known — the market has largely priced in what they signal individually.

**Add to `utils/features.py` and retrain:**

| Feature | Why it helps |
|---------|-------------|
| Earnings proximity | Binary flag — earnings in next 1/3/7 days. Stocks behave differently near reports |
| Volume anomaly | Today's volume / 20-day avg volume. Unusual volume precedes moves |
| Gap from 50-day MA | % distance above/below 50-day MA — mean reversion signal |
| Gap from 200-day MA | Same for 200-day — longer term trend context |
| Relative strength vs sector | Stock % change minus sector ETF % change. Removes market noise |
| 52-week position | Where in the 52-week range is today's price? (0 = at low, 1 = at high) |

None of these require paid data — all derivable from yfinance history already being fetched.

---

### 3.4 — Try XGBoost / LightGBM

RandomForest is a solid baseline but XGBoost and LightGBM typically outperform it on tabular financial data with the same feature set. Replacing the model usually yields +2–4% accuracy with minimal code changes.

```bash
pip install xgboost lightgbm
```

Benchmark XGBoost, LightGBM, and the existing RandomForest side-by-side on the same train/test split and pick the best.

---

### 3.5 — Expand Training Data

More tickers + more years = better generalization, less overfitting.

**Target training set:**
- All S&P 500 tickers (or a large representative sample)
- Daily history from 2010–present (~15 years)
- Produces ~150,000+ training samples vs a few thousand today

A model trained on one person's watchlist will overfit to those specific stocks' patterns. A model trained on 500 stocks across 15 years generalizes to any new ticker.

---

### 3.6 — Walk-Forward Validation

Use time-based train/test splits to verify improvements are real and not artifacts of the data split.

```
Train: 2010–2020 → Test: 2021
Train: 2010–2021 → Test: 2022
Train: 2010–2022 → Test: 2023
Train: 2010–2023 → Test: 2024
```

Average test accuracy across all windows = realistic expected performance.

---

### 3.7 — Prediction History Log

Every trading day, log the model's predictions for each user's watchlist. At market close, compare to actual price movement and record correct/incorrect.

**New DB table:** `prediction_log` — user_id, symbol, date, predicted_direction, confidence, actual_direction, was_correct

**Background job (APScheduler):**
- 9:25am ET — log today's predictions before open
- 4:05pm ET — resolve yesterday's predictions against closing prices

**What this powers:**
- Live accuracy stats on the stock detail screen
- Confidence trend chart (14-day rolling confidence per ticker)
- Daily Digest "yesterday's results" section
- Honest transparency — users see exactly where the model wins and loses

---

### 3.8 — Sector-Specific Models (longer term)

Tech stocks have different volatility profiles than financials or healthcare. A single model trained on everything compromises on all sectors. Eventually train one model per sector and route each ticker to its sector model at inference time.

---

### Improvement Priority Order

```
1. Confidence threshold ≥55%       ← do today, no retraining needed
2. Probability calibration         ← fixes 65%+ overconfidence
3. Add new features                ← retrain with better inputs
4. Try XGBoost/LightGBM            ← benchmark vs RandomForest
5. Expand training data (S&P 500)  ← biggest generalization gain
6. Walk-forward validation         ← verify improvements are real
7. Prediction history log          ← powers accuracy display in app
8. Sector-specific models          ← longer term
```

**Realistic outcome after steps 1–6:** consistent 55–58% overall accuracy, well-calibrated confidence scores, and honest historical accuracy numbers to show users.

---

## Phase 4 — ML Differentiation (App Features)

**Goal:** surface the model's accuracy and history so predictions feel trustworthy, not just decorative.

---

### 4.1 — Confidence Trend (Stock Detail)
On the stock detail screen, a small 14-day line chart showing the model's daily confidence score for that ticker. Helps users see if the model is consistently strong or noisy on a specific stock. Powered by the prediction history log (Phase 3.7).

---

### 4.2 — Accuracy Card on Dashboard
A summary card showing overall model accuracy across the user's watchlist — total predictions, hit rate this month, and a streak indicator. Makes the model's performance visible and builds trust.

---

### 4.4 — Personal Notes Per Ticker
A small editable text area on each stock detail screen. Users write their own thesis, reminders, or observations. Saves to DB on blur.

```
"Bought on earnings dip. Watching for recovery above $190.
Earnings Jul 24 — model has been right 4/4 on AAPL this month."
```

No other free tracker has this tied to ML signals.

---

## Phase 5 — Daily Digest Screen

**Goal:** one screen that answers "what do I need to know today?" — the model's morning briefing for your portfolio.

Route: `/digest`

Accessible from the header nav. Updates once per day (or live from cached data during market hours).

```
┌─────────────────────────────────────────────────┐
│  GOOD MORNING, MAX                              │
│  Tuesday, Jun 30 · Market opens in 2h 14m       │
├─────────────────────────────────────────────────┤
│  TODAY'S SIGNALS                                │
│  Model's highest confidence calls on your       │
│  watchlist, ranked                              │
│                                                 │
│  ▲ NVDA  94.2%    ▲ AAPL  88.7%                 │
│  ▲ JPM   83.1%    ▼ INTC  91.3%                 │
│  ▼ AMD   79.1%                                  │
├─────────────────────────────────────────────────┤
│  YESTERDAY'S RESULTS                            │
│  How the model did on your holdings             │
│                                                 │
│  ✓ NVDA  predicted ▲  closed +2.1%             │
│  ✓ AAPL  predicted ▲  closed +0.9%             │
│  ✗ INTC  predicted ▼  closed +1.4%             │
│                                                 │
│  5 correct · 2 wrong · 71.4% today             │
│  30-day accuracy: 68.2%                         │
├─────────────────────────────────────────────────┤
│  YOUR PORTFOLIO TODAY                           │
│  Biggest movers in your watchlist               │
│                                                 │
│  ▲ NVDA  +3.2%    ▼ INTC  -1.8%                 │
│  ▲ JPM   +1.1%    ▼ AMD   -0.7%                 │
├─────────────────────────────────────────────────┤
│  EARNINGS THIS WEEK                             │
│  Tickers on your watchlist                      │
│                                                 │
│  AAPL  Tomorrow · After close                   │
│  AMD   Thu Jul 3 · Before open                  │
├─────────────────────────────────────────────────┤
│  MARKET PULSE                                   │
│  S&P 500   +0.40%   ████                        │
│  NASDAQ    +0.61%   █████                       │
│  DOW       -0.12%   ▼                           │
└─────────────────────────────────────────────────┘
```

**What's new vs what's reused:**
| Section | Source |
|---------|--------|
| Today's signals | Already computed in sidebar |
| Yesterday's results | Prediction history log (Phase 3.7) |
| Your portfolio movers | Already computed |
| Earnings this week | `yf.Ticker().calendar` — new but easy |
| Market Pulse | SPY/QQQ/DIA — 3 extra tickers in fetch |

---

## Phase 6 — Sidebar Upgrade

Replace current watchlist-only movers with a more useful layout.

```
┌──────────────────────┐
│  MARKET PULSE        │
│  S&P 500   +0.40%    │
│  NASDAQ    +0.61%    │
│  DOW       -0.12%    │
├──────────────────────┤
│  YOUR PREDICTIONS    │
│  [Watchlist ▾]       │  ← scope dropdown
│  Top signals today   │
├──────────────────────┤
│  YOUR MOVERS         │
│  [Watchlist ▾]       │  ← same scope control
│  Best/worst today    │
├──────────────────────┤
│  EARNINGS THIS WEEK  │
│  Your tickers only   │
│  AAPL  tomorrow      │
│  AMD   Thu           │
└──────────────────────┘
```

### 6.1 — Movers & Predictions scope dropdown (planned)
Today the sidebar always uses **your watchlist**. Add a dropdown on the Movers & Predictions panel:

| Option | What it shows |
|--------|----------------|
| **Watchlist** | Current behavior — gainers, losers, volume, top predictions from watchlist symbols |
| **Funds** | Same groups computed from the union of all tickers across your funds (or per-fund if a second selector is added later) |

- Persist choice in `localStorage` (same pattern as fund benchmark dropdown)
- Update subtitle from *from your watchlist* to reflect active scope
- Backend: `build_groups()` accepts a symbol list; route passes watchlist rows or fund holding rows based on selection
- Optional follow-up: third option **All** (watchlist ∪ funds deduped)

Market Pulse (3 index numbers) gives macro context without competing with Yahoo Finance on breadth. Earnings in the sidebar is immediately actionable.

**Partially done:** Sector exposure chart (watchlist only); movers/predictions still watchlist-only.

---

## Phase 7 — Polish & Alerts

Once the core is solid:

- **Price alerts** — user sets a threshold, background job checks every 60s, sends an email/push notification
- **Sparklines** — small 1D line charts in watchlist rows (Canvas or SVG, uses intraday data already fetched)
- **Live polling** — JS polls `/api/market-data` every 60s, updates cells without page reload
- **Heat map view** — alternative watchlist view, cells colored by % change
- **Export** — download your portfolio as CSV

---

## Full Build Order

```
Phase 0 — Foundation ✅
  0.1  Auth (register, login, logout)
  0.2  Per-user DB (SQLite)
  0.3  Production server config (Gunicorn, env vars, background refresh)
  0.4  Deploy to Render (configured)

Phase 1 — Portfolio Tracker ✅
  1.1  Cost basis + positions (watchlist + fund holdings)
  1.2  Dynamic funds (search modal, expandable rows, per-stock positions)
  1.3  Sector exposure chart (sidebar, watchlist)
  1.4  Fund vs index benchmark (dropdown: SPY / DIA / QQQ / IWM)

Phase 2 — Detail Screens
  2.1  Stock detail screen (chart, position, notes, earnings)
  2.2  Fund detail screen (holdings, chart, sector breakdown)

Phase 3 — Model Improvement
  3.1  Confidence threshold filter (≥55% only)
  3.2  Probability calibration
  3.3  Better features (earnings proximity, volume anomaly, MA gaps, etc.)
  3.4  Try XGBoost / LightGBM
  3.5  Expand training data (S&P 500, 2010–present)
  3.6  Walk-forward validation
  3.7  Prediction history log (daily background job)
  3.8  Sector-specific models (longer term)

Phase 4 — ML Differentiation (App Features)
  4.1  Confidence trend chart (stock detail screen)
  4.2  Accuracy card on dashboard
  4.3  Personal notes per ticker

Phase 5 — Daily Digest Screen
  Earnings calendar + prediction results + movers + market pulse

Phase 6 — Sidebar Upgrade
  6.1  Movers & predictions scope dropdown (watchlist | funds)
  6.2  Market Pulse (SPY / QQQ / DIA)
  6.3  Earnings this week (from active scope)
  (sector exposure chart — done for watchlist)

Phase 7 — Polish
  Price alerts
  Sparklines
  Live polling
  Heat map
  CSV export
```

---

## Tech Stack

| Layer | Status |
|-------|--------|
| Backend | Flask, Jinja2 |
| Auth | Flask-Login, bcrypt |
| DB | SQLite (`data/kouros.db`) → Postgres when needed |
| ML | scikit-learn RandomForest, joblib (`model/*.pkl`) |
| Data | yfinance + 60s per-ticker cache + background refresh |
| Frontend | Vanilla JS, CSS custom properties, shared dashboard grid |
| Charts | Sector bars (CSS); Chart.js planned for detail screens |
| Hosting | Render (`render.yaml`, Gunicorn, persistent disk) |
| Scheduling | Background market refresh thread; APScheduler planned for prediction log |

---

## Project Structure (current)

```
app.py
utils/
  auth.py                  User model, login helpers
  config.py                BENCHMARK_TICKERS, BENCHMARK_OPTIONS
  db.py                    SQLite schema + migrations
  market.py                yfinance batch fetch, cache, row builder
  predict.py               ML inference
  features.py              Technical indicators
  watchlist_store.py       Per-user watchlist CRUD
  position_store.py        Per-user watchlist positions
  fund_store.py            Per-user fund CRUD + holding positions
  refresh.py               Background cache warming
  ticker_search.py         Live symbol search
model/
  trained_model.pkl
  scaler.pkl
templates/
  landing-screen.html      Main dashboard
  login.html / register.html
  partials/auth-brand-panel.html
static/
  styles.css
  theme.js
  dashboard.js
  auth.css
data/
  kouros.db                SQLite (git-ignored)
render.yaml
```

---

## Disclaimer

Kouros is a personal portfolio tracker with experimental ML-powered signals. Predictions are based on historical patterns and are not financial advice. Past model accuracy does not guarantee future results.

---

*Last updated: June 30, 2026*

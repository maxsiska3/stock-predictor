# Kouros

**Next-day stock direction predictor** — a local Flask dashboard for exploring up/down signals, model confidence, price history, and walk-forward track record. The web UI is fully wired to live yfinance data and the trained RandomForest in `model/`.

This is an experimental ML project, **not financial advice**.

**Learning path:** See [docs/LEARNING_PLAN.md](docs/LEARNING_PLAN.md) for a self-paced guide to model evaluation and retraining.

---

## How this was built

The prediction terminal frontend ([`templates/predict.html`](templates/predict.html)) was built with help from **Cursor** and **Claude**, so I could spend my time on the ML and backend work.

What I implemented myself:

- **Flask backend** — real-data routes in [`app.py`](app.py) and [`utils/dashboard.py`](utils/dashboard.py): sector, OHLCV history, model predictions, features, per-ticker backtest, and watchlist-wide market stats
- **Model training** — [`train_multi.py`](train_multi.py) (pooled 50-ticker + isotonic calibration), [`explore.py`](explore.py) (AAPL-only legacy), and the saved artifacts in [`model/`](model/)
- **Feature engineering & inference** — [`utils/features.py`](utils/features.py), [`utils/predict.py`](utils/predict.py), and [`get_predictions.py`](get_predictions.py)

**One exception:** the **Model track record** section got complicated fast (walk-forward backtest shape, watchlist-wide aggregates, caching, wiring the heat strip and stats panels to real data). Cursor helped with a small slice of that — mostly the backtest helpers in `utils/dashboard.py`, the `/api/market-stats` route, and the frontend hooks in `predict.html`. The rest of the backend and all of the ML work stayed mine.

---

## What it does

**Prediction terminal (web UI)**

- Search **any ticker** and view a next-day **up / down** call with confidence from the saved model
- Live header marquee of major index/ETF predictions (SPY, QQQ, IWM, DIA, VIX, etc.)
- Feature snapshot: RSI, MACD, Bollinger position, volatility, volume change (with 7-day spark trends)
- 60-day price history with **line** or **candlestick** chart and OHLC hover tooltips
- Last 5 calls and per-stock hit rate from a walk-forward backtest on the frozen model
- **Fixed 50-stock watchlist** track record (not dynamic): 30/60/90-day hit rates, Brier score, confidence bands, sector breakdown, bull/bear read — always the same large-cap list in `utils/watchlist.py`, not your search history

**ML pipeline (offline)**

- Fetches ~6 months of daily OHLCV via `yfinance` (plus SPY for market-context features)
- Engineers 16 features: pct change, volatility, volume change, gap, RSI, MACD, Bollinger position, SPY excess return, lags, momentum, ATR, volume SMA ratio
- Runs the saved **isotonic-calibrated** RandomForest in `model/` to predict **next trading day direction**
- Also available via `get_predictions.py` CLI batch runner

---

## Quick start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5001**

The first `/api/market-stats` request backtests the full 50-ticker watchlist (~30s cold). Results are cached in memory for 30 minutes; the server also pre-warms this cache on startup.

---

## Project layout

```
app.py                      Flask server (real predictions for the dashboard)
train_multi.py              Primary training — pooled 50-ticker data + isotonic calibration
explore.py                  Legacy AAPL-only training script
eval_baseline.py            Phase 1 baseline eval (AAPL, before retraining)
get_predictions.py          CLI batch runner over the real model
docs/
  lab-notes.md              Experiment log (metrics, retrains, calibration)
  LEARNING_PLAN.md          Self-paced ML improvement guide
templates/
  predict.html              Single-page prediction terminal UI
static/
  Kouros Logo.dc.html       Brand identity reference
utils/
  dashboard.py              Real API payload builders + watchlist backtest aggregate
  features.py               Feature engineering (shared by train + predict)
  predict.py                Load model, fetch data, run inference
  watchlist.py              Fixed 50-ticker list for market-stats aggregate (not user-editable in UI)
  yfinance_setup.py         yfinance session + cache dir
model/
  scaler.pkl                Fitted StandardScaler (16 features)
  trained_model.pkl         CalibratedClassifierCV wrapping RandomForest
```

---

## API

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Prediction terminal |
| `/api/predict/<ticker>` | GET | Single ticker — direction, confidence, features, history, last 5 calls, hit rate |
| `/api/indices` | GET | Major index/ETF predictions for the header ticker (cached 15 min) |
| `/api/market-stats` | GET | Watchlist-wide backtest aggregate for the track-record section (cached 30 min) |

Example `/api/predict/AAPL` response (abbreviated):

```json
{
  "ticker": "AAPL",
  "sector": "Technology",
  "direction": "up",
  "confidence": 56.7,
  "predicted_date": "2026-07-09",
  "features": { "rsi": 59.5, "macd": 2.97, "bollinger": 0.95, "volatility": 47.4, "volume_change": -9.5 },
  "history": { "dates": ["..."], "prices": [313.39], "ohlc": [{ "o": 311.66, "h": 314.81, "l": 307.05, "c": 313.39 }] },
  "last5": [{ "date": "2026-07-07", "call": "down", "confidence": 53.2, "hit": false }],
  "stock_hit_rate": { "rate": 38.3, "calls": 60, "history": [{ "hit": false, "move": 0.49 }] }
}
```

---

## Retrain the model

**Primary path** — `train_multi.py` downloads pooled watchlist data (cached to `data/pooled_train.pkl`), grid-searches a RandomForest, fits **isotonic calibration** on a held-out slice of the train period, and writes artifacts to `model/`:

```bash
python train_multi.py          # full grid search + calibration (~30+ min)
python train_multi.py --fast   # known RF params + calibration (~2 min, uses cache)
```

**Legacy path** — `explore.py` trains on AAPL only. Requires `matplotlib` (not in `requirements.txt`):

```bash
pip install matplotlib
python explore.py
```

**Evaluate before retraining** — `eval_baseline.py` runs AAPL-only baselines (majority class, time-series CV, holdout). Copy results into `docs/lab-notes.md`.

After retraining, restart `app.py` so the new model is loaded.

### Confidence calibration

Raw RandomForest `predict_proba` scores were overconfident at 65%+ (hit rate inverted to ~35%). The shipped model wraps the RF in `CalibratedClassifierCV(FrozenEstimator(...), method="isotonic")`, fit on the last 15% of the training window. Most live scores now land in the 50–60% range, matching the model's ~50% accuracy. See `docs/lab-notes.md` for before/after metrics.

---

## CLI (real model)

Run batch predictions against the trained model without starting the server:

```bash
python get_predictions.py
```

Prints the default watchlist to the terminal.

---

## Data note

Price data comes from **yfinance** (unofficial Yahoo Finance access). Intended for **personal, local use** only. Predictions depend on historical patterns and do not guarantee future results.

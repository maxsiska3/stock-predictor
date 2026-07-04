# Kouros

**Next-day stock direction predictor** — a local Flask dashboard for exploring up/down signals, model confidence, and price history. The web UI is backed by a deterministic mock API today; a trained RandomForest pipeline lives alongside it for real inference via CLI or future wiring.

This is an experimental ML project, **not financial advice**.

**Learning path:** See [docs/LEARNING_PLAN.md](docs/LEARNING_PLAN.md) for a self-paced guide to stub data, model evaluation, and retraining.

---

## How this was built

The prediction terminal frontend ([`templates/predict.html`](templates/predict.html)) was built with help from **Cursor** and **Claude**, so I could spend my time on the ML and backend work.

What I implemented myself:

- **Flask backend** — stub-data routes in [`app.py`](app.py) that return deterministic fake JSON matching the UI contract, while the real pipeline stays separate for now
- **Model training** — [`explore.py`](explore.py) and the saved artifacts in [`model/`](model/)
- **Feature engineering & inference** — [`utils/features.py`](utils/features.py), [`utils/predict.py`](utils/predict.py), and [`get_predictions.py`](get_predictions.py)

---

## What it does

**Prediction terminal (web UI)**

- Search any ticker and view a next-day **up / down** call with confidence
- Live header marquee of major index/ETF predictions (SPY, QQQ, IWM, DIA, VIX, etc.)
- Feature snapshot: RSI, MACD, Bollinger position, volatility, volume change (with 7-day spark trends)
- 60-day price history with **line** or **candlestick** chart and OHLC hover tooltips
- Last 5 calls and per-stock hit rate

**ML pipeline (offline)**

- Fetches ~6 months of daily OHLCV via `yfinance`
- Engineers features: pct change, volatility, volume change, gap, RSI, MACD, Bollinger position
- Runs the saved model in `model/` to predict **next trading day direction**
- Available today via `get_predictions.py` and `utils/predict.py` — not yet connected to the Flask API

---

## Quick start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5001**

---

## Project layout

```
app.py                      Flask server (mock predictions for the dashboard)
explore.py                  Training script — rebuild model artifacts
get_predictions.py          CLI batch runner over the real model
templates/
  predict.html              Single-page prediction terminal UI
static/
  Kouros Logo.dc.html       Brand identity reference
utils/
  features.py               Feature engineering (shared by train + predict)
  predict.py                Load model, fetch data, run inference
  watchlist.py              Default 50-ticker batch list
  yfinance_setup.py         yfinance session + cache dir
model/
  scaler.pkl                Fitted StandardScaler
  trained_model.pkl         Trained RandomForest
```

---

## API (current mock backend)

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Prediction terminal |
| `/api/predict/<ticker>` | GET | Single ticker — direction, confidence, features, history, last 5 calls |
| `/api/indices` | GET | Major index/ETF predictions for the header ticker |

Example `/api/predict/AAPL` response (abbreviated):

```json
{
  "ticker": "AAPL",
  "sector": "Technology",
  "direction": "up",
  "confidence": 62.3,
  "predicted_date": "2026-07-06",
  "features": { "rsi": 54.2, "macd": 0.41, "bollinger": 0.62, "volatility": 28.1, "volume_change": 12.4 },
  "history": { "dates": ["..."], "prices": [123.45], "ohlc": [{ "o": 122, "h": 125, "l": 121, "c": 123.45 }] },
  "last5": [{ "date": "2026-07-01", "call": "up", "confidence": 58.1, "hit": true }]
}
```

Mock data is **seeded per ticker** — the same symbol always returns the same result in a session.

---

## Retrain the model

`explore.py` downloads history, trains a RandomForest with time-series CV, and writes artifacts to `model/`. Requires `matplotlib` (not in `requirements.txt` — install separately if training):

```bash
pip install matplotlib
python explore.py
```

---

## CLI (real model)

Run batch predictions against the trained model without starting the server:

```bash
python get_predictions.py
```

Prints the default watchlist to the terminal.

---

## Data note

Price data for the ML pipeline comes from **yfinance** (unofficial Yahoo Finance access). Intended for **personal, local use** only. Predictions depend on historical patterns and do not guarantee future results.

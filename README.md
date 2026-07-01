# Kouros

**Next-day stock direction predictor** — a local Flask app that runs a trained RandomForest classifier on OHLCV technical features and shows up/down signals with model confidence.

---

## What it does

- Fetches ~6 months of daily price history per ticker via `yfinance`
- Engineers features: pct change, volatility, volume change, gap, RSI, MACD, Bollinger position
- Runs the saved model in `model/` to predict **next trading day direction**
- Displays results in a single local web UI — batch (50 default tickers) or one-off lookup

This is an experimental ML project, **not financial advice**.

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
app.py                 Flask server + JSON API
explore.py             Training notebook-style script (rebuild model)
get_predictions.py     CLI batch runner (optional)
utils/
  features.py          Feature engineering (shared by train + predict)
  predict.py             Load model, fetch data, run inference
  watchlist.py           Default 50-ticker batch list
  yfinance_setup.py      yfinance session + cache dir
model/
  scaler.pkl             Fitted StandardScaler
  trained_model.pkl      Trained RandomForest
templates/index.html     Predictor UI
static/                  CSS + JS
```

---

## API

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Predictor page |
| `/api/predict/<ticker>` | GET | Single ticker result |
| `/api/predictions` | GET | All default watchlist tickers |
| `/api/predictions?tickers=AAPL,MSFT` | GET | Custom comma-separated list |
| `/api/predictions` | POST | Body: `{ "tickers": ["AAPL", "MSFT"] }` |

Response shape:

```json
{
  "predictions": [
    { "ticker": "AAPL", "direction": 1, "confidence": 62.5, "error": null }
  ],
  "summary": { "up": 28, "down": 22, "failed": 0, "total": 50 }
}
```

`direction`: `1` = up, `0` = down.

---

## Retrain the model

`explore.py` downloads history, trains a RandomForest with time-series CV, and writes artifacts to `model/`. Requires `matplotlib` (not in `requirements.txt` — install separately if training):

```bash
pip install matplotlib
python explore.py
```

---

## CLI alternative

```bash
python get_predictions.py
```

Prints the default watchlist predictions to the terminal (no server).

---

## Data note

Price data comes from **yfinance** (unofficial Yahoo Finance access). Intended for **personal, local use** only. Predictions depend on historical patterns and do not guarantee future results.

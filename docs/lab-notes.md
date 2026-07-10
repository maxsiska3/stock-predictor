# Lab Notes — Kouros Model Retraining

## 2026-07-10 — Phase 1 baseline (AAPL-only data, old single-ticker model era)

| Metric | Score |
|--------|-------|
| Rows | 1,365 |
| Class balance | 52.9% up |
| Majority-class baseline | 52.9% |
| CV mean (5-fold) | 51.6% |
| Holdout (last 20%) | 54.2% |

**Takeaway:** AAPL-only baseline was barely above random.

---

## 2026-07-10 — Multi-ticker retrain (`train_multi.py`)

| Metric | Score |
|--------|-------|
| Tickers downloaded | 50 / 50 |
| Pooled rows | 68,250 |
| Class balance | 51.9% up |
| Majority-class baseline | 51.9% |
| CV mean (5-fold) | 50.3% |
| Holdout (last 20%) | 50.5% |

**Params shipped:** `n_estimators=200`, `max_depth=20`, `min_samples_split=10`, `random_state=42`

**Artifacts:** `model/scaler.pkl`, `model/trained_model.pkl` (restart `app.py` to load)

**Takeaway:** Multi-ticker pooled model is ~50% on holdout — essentially coin-flip on this feature set. Generalizes across tickers but does not beat majority baseline on pooled data. Next levers: market context features (SPY), lagged features, or longer history — one change at a time.

---

## 2026-07-10 — Retrain #3 (16 features, 2018 data, grid search)

| Metric | Score |
|--------|-------|
| Tickers | 50 / 50 |
| Pooled rows | 105,309 |
| Features | 16 (SPY context, lagged, momentum, volume/ATR) |
| Class balance | 52.3% up |
| Majority-class baseline | 52.3% |
| CV mean (5-fold) | 51.3% |
| Holdout (date-based, last 20%) | 51.3% |

**Model:** RandomForest (`n_estimators=300`, `max_depth=12`, `min_samples_leaf=20`, `class_weight=None`)

**Artifacts:** `model/scaler.pkl` (16 features), `model/trained_model.pkl` — train/serve parity fixed.

**Takeaway:** Extra features and tuning did not materially beat ~51%. Still near random for next-day direction prediction.

---

## 2026-07-10 — Isotonic calibration (overconfidence fix)

| Metric | Before | After |
|--------|--------|-------|
| 65+ hit rate (90d watchlist backtest) | 35.3% (n=34) | 79.2% (n=24) |
| 60-65 hit rate | 63.3% (n=49) | n/a (scores compressed) |
| Brier score (90d watchlist) | 0.252 | 0.252 |
| Holdout accuracy | 51.3% | 51.8% |

**Method:** `CalibratedClassifierCV(FrozenEstimator(RF), method="isotonic")` fit on last 15% of train period.

**Artifacts:** `model/trained_model.pkl` (now `CalibratedClassifierCV`), `model/scaler.pkl`

**Takeaway:** Raw RF probabilities were overconfident at 65%+ (inverted hit rate). Isotonic calibration pulls scores toward empirical frequencies — most live calls now land in 50–60% where they belong for a ~50% model.

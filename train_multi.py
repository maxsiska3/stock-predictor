"""Train best model on pooled 50-ticker watchlist data.

Caches downloaded dataset to data/pooled_train.pkl for fast re-runs.
Run: python train_multi.py          # full grid search + calibration
     python train_multi.py --fast   # known RF params + calibration
"""

import time
from datetime import date
from pathlib import Path

import joblib as jl
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import accuracy_score, brier_score_loss
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from utils.features import FEATURE_COLS, compute_features
from utils.watchlist import DEFAULT_WATCHLIST
from utils.yfinance_setup import configure_yfinance, get_yf_session, reset_yf_session

START = "2018-01-01"
TRAIN_FRACTION = 0.8
CAL_FRACTION = 0.15  # tail of train period used to calibrate probabilities
CV_SPLITS = 5
_MODEL_DIR = "model"
_CACHE = Path("data/pooled_train.pkl")
_CONFIDENCE_BANDS = [(50, 55), (55, 60), (60, 65), (65, 1000)]

RF_GRID = {
    "model__max_depth": [12, 20, 28],
    "model__min_samples_leaf": [10, 20],
    "model__class_weight": [None, "balanced_subsample"],
}
FAST_RF_PARAMS = {
    "n_estimators": 300,
    "max_depth": 12,
    "min_samples_leaf": 20,
    "class_weight": None,
    "random_state": 42,
    "n_jobs": 2,
}


def _flatten(df):
    out = pd.DataFrame(df)
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    return out


def download_spy(start: str) -> pd.DataFrame:
    session = get_yf_session()
    spy = _flatten(yf.download("SPY", start=start, progress=False, session=session, threads=False))
    if spy.empty:
        raise RuntimeError("SPY download failed")
    return spy


def download_ticker_rows(ticker: str, start: str, spy_df: pd.DataFrame, _retry=True) -> pd.DataFrame | None:
    try:
        session = get_yf_session()
        raw = yf.download(ticker, start=start, progress=False, session=session, threads=False)
        if raw is None or raw.empty:
            raise ValueError("empty download")
        df = _flatten(raw)
        df = compute_features(df, spy_df=spy_df)
        df["target"] = (df["Close"].shift(-1) > df["Close"]).astype(int)
        df["ticker"] = ticker
        df = df.iloc[:-1].dropna(subset=FEATURE_COLS + ["target"])
        if df.empty:
            raise ValueError("no valid rows")
        return df
    except Exception as exc:
        if _retry:
            reset_yf_session()
            return download_ticker_rows(ticker, start, spy_df, _retry=False)
        print(f"  SKIP {ticker}: {exc}")
        return None


def build_pooled_dataset(tickers: list[str], start: str) -> tuple[pd.DataFrame, list[str], list[str]]:
    configure_yfinance()
    print("Downloading SPY...")
    spy_df = download_spy(start)
    frames, ok, failed = [], [], []
    for i, ticker in enumerate(tickers):
        if i > 0:
            time.sleep(0.2)
        print(f"Downloading {ticker} ({i + 1}/{len(tickers)})...")
        df = download_ticker_rows(ticker, start, spy_df)
        if df is None:
            failed.append(ticker)
            continue
        frames.append(df)
        ok.append(ticker)
    if not frames:
        raise RuntimeError("no ticker data downloaded")
    return pd.concat(frames).sort_index(), ok, failed


def load_or_build_dataset() -> tuple[pd.DataFrame, list[str], list[str]]:
    meta_path = _CACHE.with_suffix(".meta.txt")
    if _CACHE.exists() and meta_path.exists() and meta_path.read_text().strip() == START:
        print(f"Loading cached dataset from {_CACHE}")
        pooled = pd.read_pickle(_CACHE)
        ok = pooled["ticker"].unique().tolist()
        return pooled, ok, []
    pooled, ok, failed = build_pooled_dataset(DEFAULT_WATCHLIST, START)
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    pooled.to_pickle(_CACHE)
    meta_path.write_text(START)
    print(f"Cached dataset to {_CACHE}")
    return pooled, ok, failed


def date_based_split(df: pd.DataFrame, train_fraction: float):
    dates = pd.Series(df.index.normalize().unique()).sort_values()
    split_date = dates.iloc[int(len(dates) * train_fraction)]
    train = df[df.index.normalize() < split_date]
    test = df[df.index.normalize() >= split_date]
    return train, test


def date_based_cal_split(train_df: pd.DataFrame, cal_fraction: float):
    """Hold out the latest slice of the train period for probability calibration."""
    dates = pd.Series(train_df.index.normalize().unique()).sort_values()
    split_date = dates.iloc[int(len(dates) * (1 - cal_fraction))]
    fit = train_df[train_df.index.normalize() < split_date]
    cal = train_df[train_df.index.normalize() >= split_date]
    return fit, cal


def _up_class_idx(model) -> int:
    return list(model.classes_).index(1)


def confidence_band_report(y_true, y_pred, proba, label: str):
    """Print hit rate by displayed confidence bucket (max class probability)."""
    conf = np.round(proba.max(axis=1) * 100, 1)
    y_arr = np.asarray(y_true)
    pred_arr = np.asarray(y_pred)
    print(f"\nConfidence bands ({label}):")
    for lo, hi in _CONFIDENCE_BANDS:
        mask = (conf >= lo) & (conf < hi)
        count = int(mask.sum())
        band = f"{lo}-{hi}" if hi < 1000 else f"{lo}+"
        if count == 0:
            print(f"  {band:8} n/a (0)")
            continue
        rate = pred_arr[mask] == y_arr[mask]
        print(f"  {band:8} {rate.mean():.1%} hit rate ({count} rows)")


def fit_calibrated_model(base_model, fit_df, cal_df, test_df):
    """Fit scaler + base model on fit slice, isotonic-calibrate on cal slice."""
    scaler = StandardScaler()
    X_fit = scaler.fit_transform(fit_df[FEATURE_COLS])
    X_cal = scaler.transform(cal_df[FEATURE_COLS])
    X_test = scaler.transform(test_df[FEATURE_COLS])

    y_fit = fit_df["target"]
    y_cal = cal_df["target"]
    y_test = test_df["target"]

    base_model.fit(X_fit, y_fit)
    up_idx = _up_class_idx(base_model)
    raw_cal_proba = base_model.predict_proba(X_cal)
    raw_test_proba = base_model.predict_proba(X_test)
    raw_test_pred = base_model.predict(X_test)

    calibrated = CalibratedClassifierCV(FrozenEstimator(base_model), method="isotonic")
    calibrated.fit(X_cal, y_cal)

    cal_proba = calibrated.predict_proba(X_cal)
    test_proba = calibrated.predict_proba(X_test)
    test_pred = calibrated.predict(X_test)

    print(f"\nBrier score (cal set):  raw {brier_score_loss(y_cal, raw_cal_proba[:, up_idx]):.3f}"
          f" -> calibrated {brier_score_loss(y_cal, cal_proba[:, up_idx]):.3f}")
    print(f"Brier score (test set): raw {brier_score_loss(y_test, raw_test_proba[:, up_idx]):.3f}"
          f" -> calibrated {brier_score_loss(y_test, test_proba[:, up_idx]):.3f}")

    confidence_band_report(y_test, raw_test_pred, raw_test_proba, "uncalibrated test")
    confidence_band_report(y_test, test_pred, test_proba, "calibrated test")

    holdout_acc = accuracy_score(y_test, test_pred)
    return scaler, calibrated, holdout_acc


def majority_class_accuracy(y: pd.Series) -> float:
    majority = int(y.mode().iloc[0])
    return float((y == majority).mean())


def search_best_model(X, y):
    cv = TimeSeriesSplit(n_splits=CV_SPLITS)
    candidates = []

    rf_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model", RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=2)),
    ])
    print("\nGrid-searching RandomForest (12 combos)...")
    rf_search = GridSearchCV(
        rf_pipe, RF_GRID, cv=cv, scoring="accuracy", n_jobs=1, verbose=1,
    )
    rf_search.fit(X, y)
    candidates.append((rf_search.best_score_, rf_search.best_estimator_, "RandomForest", rf_search.best_params_))
    print(f"  RF best CV: {rf_search.best_score_:.1%}  {rf_search.best_params_}")

    et_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model", ExtraTreesClassifier(
            n_estimators=400, max_depth=20, min_samples_leaf=12,
            class_weight="balanced_subsample", random_state=42, n_jobs=2,
        )),
    ])
    et_scores = cross_val_score(et_pipe, X, y, cv=cv, n_jobs=1)
    et_cv = float(et_scores.mean())
    print(f"  ExtraTrees CV: {et_cv:.1%}")
    candidates.append((et_cv, et_pipe, "ExtraTrees", et_pipe.named_steps["model"].get_params()))

    best = max(candidates, key=lambda c: c[0])
    print(f"\n  -> Winner: {best[2]} (CV {best[0]:.1%})")
    return best[1], best[0], best[2], best[3]


def pick_model(fast: bool, X, y):
    if fast:
        print("\nFast mode: skipping grid search, using known RF params + isotonic calibration")
        model = RandomForestClassifier(**FAST_RF_PARAMS)
        cv = TimeSeriesSplit(n_splits=CV_SPLITS)
        pipe = Pipeline([("scaler", StandardScaler()), ("model", model)])
        scores = cross_val_score(pipe, X, y, cv=cv, n_jobs=1)
        cv_score = float(scores.mean())
        print(f"  RF CV (fixed params): {cv_score:.1%}")
        return model, cv_score, "RandomForest", FAST_RF_PARAMS

    best_pipe, cv_score, model_name, best_params = search_best_model(X, y)
    fitted = best_pipe.named_steps["model"]
    base_model = fitted.__class__(**{
        k: v for k, v in fitted.get_params().items() if not k.startswith("_")
    })
    return base_model, cv_score, model_name, best_params


def main():
    import sys
    fast = "--fast" in sys.argv
    print(f"\n=== Multi-ticker training ({len(DEFAULT_WATCHLIST)} symbols, from {START}) ===")
    pooled, ok, failed = load_or_build_dataset()
    X, y = pooled[FEATURE_COLS], pooled["target"]

    print(f"\nPooled: {len(pooled):,} rows, {len(FEATURE_COLS)} features, {len(ok)} tickers")
    print(f"Class balance: {y.mean():.1%} up | Majority baseline: {majority_class_accuracy(y):.1%}")

    base_model, cv_score, model_name, best_params = pick_model(fast, X, y)

    train_df, test_df = date_based_split(pooled, TRAIN_FRACTION)
    fit_df, cal_df = date_based_cal_split(train_df, CAL_FRACTION)
    print(f"\nSplit: fit {len(fit_df):,} | cal {len(cal_df):,} | test {len(test_df):,} rows")

    scaler, calibrated_model, holdout_acc = fit_calibrated_model(
        base_model, fit_df, cal_df, test_df,
    )
    print(f"\nHoldout accuracy (calibrated, date-based last 20%): {holdout_acc:.1%}")

    jl.dump(calibrated_model, f"{_MODEL_DIR}/trained_model.pkl")
    jl.dump(scaler, f"{_MODEL_DIR}/scaler.pkl")
    print(f"Saved calibrated {model_name} -> model/*.pkl (restart app.py)")

    print("\n--- lab log summary ---")
    print(f"date: {date.today().isoformat()}")
    print(f"model: {model_name} + isotonic calibration")
    print(f"features: {FEATURE_COLS}")
    print(f"rows: {len(pooled)}")
    print(f"cv_mean: {cv_score:.1%}")
    print(f"holdout: {holdout_acc:.1%}")
    print(f"params: {best_params}")
    print(f"cal_fraction: {CAL_FRACTION}")


if __name__ == "__main__":
    main()

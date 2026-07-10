"""Phase 1 baseline evaluation for AAPL next-day direction.

Compares the current feature set against simple baselines before retraining.
Run: python eval_baseline.py
"""

import yfinance as yf
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from utils.features import FEATURE_COLS, compute_features

TICKER = "AAPL"
START = "2021-01-01"
TRAIN_FRACTION = 0.8
CV_SPLITS = 5
RF_PARAMS = {
    "n_estimators": 200,
    "max_depth": 20,
    "min_samples_split": 10,
    "random_state": 42,
}


def load_labeled_data(ticker: str, start: str) -> pd.DataFrame:
    """Download OHLCV, build features + target, return cleaned rows."""
    raw = yf.download(ticker, start=start, progress=False)
    df = pd.DataFrame(raw)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    spy = yf.download("SPY", start=start, progress=False)
    spy_df = pd.DataFrame(spy)
    if isinstance(spy_df.columns, pd.MultiIndex):
        spy_df.columns = spy_df.columns.get_level_values(0)

    df = compute_features(df, spy_df=spy_df)
    df["target"] = (df["Close"].shift(-1) > df["Close"]).astype(int)
    df = df.iloc[:-1]
    return df.dropna(subset=FEATURE_COLS + ["target"])


def majority_class_accuracy(y: pd.Series) -> tuple[float, int]:
    """Always predict whichever direction appears more often."""
    majority_class = int(y.mode().iloc[0])
    accuracy = float((y == majority_class).mean())
    return accuracy, majority_class


def temporal_train_test_split(df: pd.DataFrame, train_fraction: float):
    """Split by time: first train_fraction for train, rest for test."""
    split_idx = int(len(df) * train_fraction)
    train = df.iloc[:split_idx]
    test = df.iloc[split_idx:]
    return (
        train[FEATURE_COLS],
        test[FEATURE_COLS],
        train["target"],
        test["target"],
    )


def make_pipeline() -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("model", RandomForestClassifier(**RF_PARAMS)),
    ])


def run_time_series_cv(X: pd.DataFrame, y: pd.Series) -> tuple[list[float], float]:
    """TimeSeriesSplit CV with scaler + RF pipeline."""
    pipe = make_pipeline()
    cv = TimeSeriesSplit(n_splits=CV_SPLITS)
    fold_scores = cross_val_score(pipe, X, y, cv=cv).tolist()
    mean_score = float(sum(fold_scores) / len(fold_scores))
    return fold_scores, mean_score


def run_holdout_test(df: pd.DataFrame) -> float:
    """Train on first 80% by time, evaluate on last 20%."""
    X_train, X_test, y_train, y_test = temporal_train_test_split(df, TRAIN_FRACTION)
    pipe = make_pipeline()
    pipe.fit(X_train, y_train)
    y_pred = pipe.predict(X_test)
    return float(accuracy_score(y_test, y_pred))


def main():
    df = load_labeled_data(TICKER, START)
    y = df["target"]
    X = df[FEATURE_COLS]

    print(f"\n=== {TICKER} baseline eval ({len(df)} rows) ===")
    print(f"Class balance: {y.mean():.1%} up, {1 - y.mean():.1%} down")

    maj_acc, maj_class = majority_class_accuracy(y)
    direction = "up" if maj_class == 1 else "down"
    print(f"\nMajority-class baseline: {maj_acc:.1%} (always predict {direction})")

    fold_scores, cv_mean = run_time_series_cv(X, y)
    print(f"\nTimeSeriesSplit CV ({CV_SPLITS} folds):")
    print(f"  Each fold: {[round(s, 4) for s in fold_scores]}")
    print(f"  Mean:      {cv_mean:.1%}")

    holdout_acc = run_holdout_test(df)
    print(f"\nHoldout accuracy (last {100 - int(TRAIN_FRACTION * 100)}%): {holdout_acc:.1%}")

    print("\nCopy these numbers into docs/lab-notes.md before retraining.")


if __name__ == "__main__":
    main()

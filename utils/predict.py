import joblib as jl
import yfinance as yf
import pandas as pd
from utils.features import compute_features, FEATURE_COLS

# Load Model
scaler = jl.load("model/scaler.pkl")
trained_model = jl.load("model/trained_model.pkl")

def predict_stock(ticker) -> tuple:

    # Load 6 Months of Data
    start = pd.Timestamp.now() - pd.DateOffset(months=6)
    raw_df = yf.download(ticker, start=start)
    raw_df = pd.DataFrame(raw_df)
    raw_df.columns = raw_df.columns.get_level_values(0)
    df_features = compute_features(raw_df)

    # Grab Last Row
    last_row = df_features[FEATURE_COLS].iloc[[-1]]

    # Scale Data
    scaled_features = scaler.transform(last_row)

    # Predict Up or Down and Confidence
    prediction = trained_model.predict(scaled_features)
    confidence = trained_model.predict_proba(scaled_features)

    return prediction, confidence

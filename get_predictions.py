from utils.predict import predict_stock
from utils.watchlist import DEFAULT_WATCHLIST

predictions = []

for ticker in DEFAULT_WATCHLIST:
    prediction, confidence = predict_stock(ticker)
    direction = "Up" if int(prediction[0]) == 1 else "Down"
    confidence_pct = round(float(confidence[0].max()) * 100, 2)
    predictions.append({
        "ticker": ticker,
        "direction": direction,
        "confidence": confidence_pct,
    })

for row in predictions:
    print(f"{row['ticker']:6}  {row['direction']:4}  {row['confidence']}%")

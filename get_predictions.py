from utils.predict import predict_stock
from utils.watchlist import DEFAULT_WATCHLIST
from utils.yfinance_setup import configure_yfinance

configure_yfinance()

predictions = []

for ticker in DEFAULT_WATCHLIST:
    try:
        prediction, confidence = predict_stock(ticker)
        direction = "Up" if int(prediction[0]) == 1 else "Down"
        confidence_pct = round(float(confidence[0].max()) * 100, 2)
        predictions.append({
            "ticker": ticker,
            "direction": direction,
            "confidence": confidence_pct,
        })
    except Exception as exc:
        predictions.append({
            "ticker": ticker,
            "direction": "ERR",
            "confidence": str(exc),
        })

for row in predictions:
    if row["direction"] == "ERR":
        print(f"{row['ticker']:6}  ERR   {row['confidence']}")
    else:
        print(f"{row['ticker']:6}  {row['direction']:4}  {row['confidence']}%")

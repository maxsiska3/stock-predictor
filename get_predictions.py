from utils.predict import predict_stock

WATCHLIST = [
    "ACN", "AAPL", "META", "GOOG", "AMZN",
    "TSM", "NVDA", "TSLA", "AMD", "BRK-B",
    "ORCL", "PLTR", "MU", "JPM", "AVGO",
    "MSFT", "NFLX", "COST", "WMT", "UNH",
    "LLY", "JNJ", "XOM", "CVX", "BAC",
    "GS", "V", "MA", "DIS", "INTC",
    "QCOM", "CRM", "ADBE", "IBM", "CAT",
    "BA", "NKE", "PEP", "KO", "MRK",
    "PFE", "ABBV", "HD", "CSCO", "TXN",
    "UNP", "SBUX", "MCD", "LIN", "AMAT",
]

predictions = []

for ticker in WATCHLIST:
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

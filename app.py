from utils.predict import predict_stock 
from flask import Flask, render_template, request


app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/predict", methods=["POST"])
def predict():
    ticker = request.form.get("ticker")
    prediction, confidence = predict_stock(ticker)
    direction = "Up" if prediction[0] == 1 else "Down"
    confidence_pct = round(float(confidence[0].max()) * 100, 2)
    return render_template("index.html", ticker=ticker, direction=direction, confidence=confidence_pct)


if __name__ == "__main__":
    app.run(debug=True)

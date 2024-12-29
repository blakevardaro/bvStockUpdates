from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Flask setup
app = Flask(__name__, static_folder="static")
CORS(app)

# File to store requested stocks
REQUESTED_STOCKS_FILE = "requested_stocks.json"


# Utility functions
def load_requested_stocks():
    """Load the requested stocks data from a file."""
    try:
        with open(REQUESTED_STOCKS_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Error loading requested stocks file: {e}")
        return {}


def save_requested_stocks(data):
    """Save the requested stocks data to a file."""
    try:
        with open(REQUESTED_STOCKS_FILE, "w") as file:
            json.dump(data, file, indent=4)
    except Exception as e:
        print(f"Error saving requested stocks file: {e}")


# Routes
@app.route("/")
def serve_index():
    """Serve the main index HTML file."""
    return send_from_directory(".", "index.html")


@app.route("/yfinance-guide")
def serve_yfinance_guide():
    """Serve the YFinance guide HTML file."""
    return send_from_directory(".", "yfinance-guide.html")


@app.route("/monitored-stocks")
def serve_monitored_stocks():
    """Serve the Monitored Stocks HTML file."""
    return send_from_directory(".", "monitored-stocks.html")


@app.route("/monitored-stocks-api", methods=["GET"])
def get_monitored_stocks():
    """Return a list of monitored stocks."""
    try:
        with open("stock_data.json", "r") as file:
            stocks = json.load(file)  # Assuming stock_data.json contains monitored stocks
        return jsonify(stocks)
    except Exception as e:
        print(f"Error reading stock data: {e}")
        return jsonify([])  # Return an empty list if there's an error



@app.route("/request-stock", methods=["POST"])
def request_stock():
    """Handle requests to add a new stock to monitoring."""
    data = request.get_json()
    symbol = data.get("symbol")
    if not symbol:
        return jsonify({"success": False, "message": "No stock symbol provided."}), 400

    # Load existing requested stocks
    requested_stocks = load_requested_stocks()

    # Update the count for the requested stock
    symbol = symbol.upper()  # Standardize to uppercase
    if symbol in requested_stocks:
        requested_stocks[symbol] += 1
    else:
        requested_stocks[symbol] = 1

    # Save the updated data back to the file
    save_requested_stocks(requested_stocks)

    # Return success message
    return jsonify({"success": True, "message": f"Requested monitoring for stock {symbol}."})


@app.route("/stock-alerts", methods=["GET"])
def get_stock_alerts():
    """Return the latest stock alerts."""
    try:
        with open("stock_data.json", "r") as file:
            alerts = json.load(file)
        return jsonify(alerts)
    except Exception as e:
        print(f"Error reading stock data file: {e}")
        return jsonify({"success": False, "message": "Error reading stock data."}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

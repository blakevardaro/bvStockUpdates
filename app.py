from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os
from dotenv import load_dotenv
import time
import json

# Load environment variables
load_dotenv()

# Flask setup
app = Flask(__name__, static_folder="static")
CORS(app)

# Global variables to store notification flag
app.config['NEW_DATA'] = False

# File to store requested stocks
REQUESTED_STOCKS_FILE = "requested_stocks.json"

def add_email_to_sheet(email):
    """Add a subscriber email to Google Sheets if it doesn't already exist."""
    creds = Credentials.from_service_account_file(
        os.getenv("CREDENTIALS_FILE"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    # Fetch existing emails
    result = sheet.values().get(
        spreadsheetId=os.getenv("SubscriberList_SHEET_ID"),
        range="A:A"
    ).execute()
    existing_emails = [row[0].strip().lower() for row in result.get("values", [])]

    normalized_email = email.strip().lower()
    if normalized_email in existing_emails:
        return False, f"{email} is already subscribed."

    sheet.values().append(
        spreadsheetId=os.getenv("SubscriberList_SHEET_ID"),
        range="A:A",
        valueInputOption="USER_ENTERED",
        body={"values": [[email]]}
    ).execute()

    return True, f"Thank you for subscribing! {email} subscribed successfully."

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
@app.route("/subscribe", methods=["POST"])
def subscribe():
    """Handle subscription requests."""
    data = request.get_json()
    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "No email provided."}), 200

    success, message = add_email_to_sheet(email)
    return jsonify({"success": success, "message": message}), 200

@app.route("/unsubscribe", methods=["POST"])
def unsubscribe():
    """Handle unsubscription requests."""
    data = request.get_json()
    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "No email provided."}), 400

    creds = Credentials.from_service_account_file(
        os.getenv("CREDENTIALS_FILE"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=os.getenv("SubscriberList_SHEET_ID"),
        range="A:A"
    ).execute()
    values = result.get("values", [])
    normalized_email = email.strip().lower()

    for i, row in enumerate(values, start=1):
        if row and row[0].strip().lower() == normalized_email:
            for j in range(i + 1, len(values) + 1):
                next_row = sheet.values().get(
                    spreadsheetId=os.getenv("SubscriberList_SHEET_ID"),
                    range=f"A{j}"
                ).execute().get("values", [])
                sheet.values().update(
                    spreadsheetId=os.getenv("SubscriberList_SHEET_ID"),
                    range=f"A{j-1}",
                    valueInputOption="RAW",
                    body={"values": next_row}
                ).execute()

            sheet.values().clear(
                spreadsheetId=os.getenv("SubscriberList_SHEET_ID"),
                range=f"A{len(values)}"
            ).execute()

            return jsonify({"success": True, "message": f"We're sad to see you go :( Unsubscribed {email} successfully."})

    return jsonify({"success": False, "message": f"{email} not found."}), 404

@app.route("/")
def serve_index():
    """Serve the main index HTML file."""
    return send_from_directory(".", "index.html")


@app.route("/yfinance-guide")
def serve_yfinance_guide():
    """Serve the YFinance guide HTML file."""
    return send_from_directory(".", "yfinance-guide.html")

@app.route("/notify", methods=["POST"])
def notify():
    """Handle notification from stockUpdates.py."""
    app.config["NEW_DATA"] = True
    return jsonify({"success": True})

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

@app.route("/events")
def events():
    """Stream updates to the client."""
    def generate():
        while True:
            if app.config.get("NEW_DATA", False):
                app.config["NEW_DATA"] = False  # Reset flag
                yield f"data: update\n\n"
            time.sleep(1)  # Check for updates every second
    return Response(generate(), content_type="text/event-stream")

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

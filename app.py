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

def add_email_to_sheet(email):
    """Add a subscriber email to Google Sheets."""
    try:
        creds = Credentials.from_service_account_file(
            os.getenv("CREDENTIALS_FILE"),
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        values = [[email]]
        body = {"values": values}
        sheet.values().append(
            spreadsheetId=os.getenv("GOOGLE_SHEET_ID"),
            range="A:A",
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        return True
    except Exception as e:
        print(f"Error adding email to Google Sheets: {e}")
        return False

@app.route("/subscribe", methods=["POST"])
def subscribe():
    """Handle subscription requests."""
    data = request.get_json()
    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "No email provided."}), 400

    success = add_email_to_sheet(email)
    if success:
        return jsonify({"success": True, "message": f"Subscribed {email} successfully."})
    return jsonify({"success": False, "message": "Failed to subscribe email."})

@app.route("/unsubscribe", methods=["POST"])
def unsubscribe():
    """Handle unsubscription requests."""
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"success": False, "message": "No email provided."}), 400

    try:
        # Authenticate with Google Sheets
        creds = Credentials.from_service_account_file(
            os.getenv("CREDENTIALS_FILE"),
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        # Get all emails from the sheet
        result = sheet.values().get(
            spreadsheetId=os.getenv("GOOGLE_SHEET_ID"),
            range="A:A"
        ).execute()
        values = result.get("values", [])

        # Find the email and delete the corresponding row
        for i, row in enumerate(values, start=1):  # Google Sheets rows are 1-indexed
            if row and row[0].strip().lower() == email.strip().lower():
                # Shift rows up
                for j in range(i + 1, len(values) + 1):
                    next_row = sheet.values().get(
                        spreadsheetId=os.getenv("GOOGLE_SHEET_ID"),
                        range=f"A{j}"
                    ).execute().get("values", [])
                    sheet.values().update(
                        spreadsheetId=os.getenv("GOOGLE_SHEET_ID"),
                        range=f"A{j-1}",
                        valueInputOption="RAW",
                        body={"values": next_row}
                    ).execute()
                # Clear the last row
                sheet.values().clear(
                    spreadsheetId=os.getenv("GOOGLE_SHEET_ID"),
                    range=f"A{len(values)}"
                ).execute()

                print(f"Email {email} unsubscribed successfully.")
                return jsonify({"success": True, "message": f"Unsubscribed {email}."})

        return jsonify({"success": False, "message": "Email not found."}), 404
    except Exception as e:
        print(f"Error unsubscribing email: {e}")
        return jsonify({"success": False, "message": "Internal server error."}), 500

@app.route("/yfinance-guide")
def serve_yfinance_guide():
    """Serve the YFinance guide HTML file."""
    return send_from_directory(".", "yfinance-guide.html")

@app.route("/notify", methods=["POST"])
def notify():
    """Handle notification from stockUpdates.py."""
    app.config["NEW_DATA"] = True
    return jsonify({"success": True})

@app.route("/stock-alerts", methods=["GET"])
def get_stock_alerts():
    """Return the latest stock alerts from the file."""
    try:
        with open("stock_data.json", "r") as file:
            alerts = json.load(file)
        return jsonify(alerts)
    except Exception as e:
        print(f"Error reading stock data file: {e}")
        return jsonify({"success": False, "message": "Error reading stock data."}), 500

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

@app.route("/")
def serve_index():
    """Serve the main index HTML file."""
    return send_from_directory(".", "index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

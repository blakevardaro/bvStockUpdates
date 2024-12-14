import csv
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
from dotenv import load_dotenv
from collections import defaultdict
import requests
import json

# Load environment variables
load_dotenv()

# Email Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# Google Sheets Configuration
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")

# CSV File Path
CSV_FILE = "fortune500_all.csv"
DATA_FILE = "stock_data.json"  # File to store fetched stock data
SITE_URL = "http://localhost:5000/notify"  # Endpoint to notify site of new data


def read_stock_symbols(csv_file):
    """Read stock symbols from a CSV file."""
    try:
        with open(csv_file, mode='r') as file:
            reader = csv.DictReader(file)
            return [row['Symbol'] for row in reader]
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return []


def fetch_stock_data(symbols, period="1y"):
    """Fetch data for multiple stocks."""
    try:
        return yf.download(tickers=" ".join(symbols), period=period, group_by="ticker", threads=True, progress=False)
    except Exception as e:
        print(f"Error fetching stock data: {e}")
        return None


def calculate_moving_averages(data, periods):
    """Calculate moving averages for a single stock."""
    moving_averages = {}
    try:
        for period in periods:
            if len(data) >= period:
                moving_averages[period] = data['Close'].rolling(window=period).mean().iloc[-1]
    except Exception as e:
        print(f"Error calculating moving averages: {e}")
    return moving_averages


def process_stock_data(symbol, data, periods):
    """Process stock data to generate alerts."""
    alerts = []
    try:
        current_price = data['Close'].iloc[-1]
        moving_averages = calculate_moving_averages(data, periods)
        for period, avg in moving_averages.items():
            if avg and current_price < avg:
                percentage_change = (avg - current_price) / avg * 100
                difference = avg - current_price
                alerts.append({
                    "symbol": symbol,
                    "period": f"{period}-day",
                    "current_price": current_price,
                    "average": avg,
                    "difference": difference,
                    "percentage_change": percentage_change
                })
    except Exception as e:
        print(f"Error processing stock data for {symbol}: {e}")
    return alerts


def format_alert_email(alerts):
    """Format the email body with alerts."""
    alerts_by_symbol = defaultdict(list)
    for alert in alerts:
        alerts_by_symbol[alert["symbol"]].append(alert)

    sorted_symbols = sorted(alerts_by_symbol.keys())

    body = "<html><body>"
    body += "<h2><a href='http://34.23.138.210:5000/#stock-alerts-section'>Stock Price Alerts</a></h2><ul>"

    for symbol in sorted_symbols:
        current_price = alerts_by_symbol[symbol][0]["current_price"]
        yahoo_link = f"https://finance.yahoo.com/quote/{symbol}"
        body += f"<li><strong><a href='{yahoo_link}' style='text-decoration:none; color:blue;'>{symbol}</a> <span style='color:red; font-weight:bold;'>${current_price:.2f}</span></strong></li>"

        body += "<ul>"
        for alert in alerts_by_symbol[symbol]:
            body += (
                f"<li>{alert['period']} Moving Average: "
                f"<span style='color:green; font-weight:bold;'>${alert['average']:.2f}</span>, "
                f"Difference: <span style='color:red; font-weight:bold;'>${alert['difference']:.2f}</span> "
                f"(<span style='color:blue; font-weight:bold;'>{alert['percentage_change']:.2f}%</span>)</li>"
            )
        body += "</ul><br>"  # Add a line break to separate stocks
    body += "</ul></body></html>"
    return body


def get_subscriber_emails():
    """Fetch subscriber emails from Google Sheets."""
    try:
        creds = Credentials.from_service_account_file(
            CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        result = sheet.values().get(
            spreadsheetId=GOOGLE_SHEET_ID,
            range="A:A"
        ).execute()
        values = result.get("values", [])
        return [row[0] for row in values if row]
    except Exception as e:
        print(f"Error fetching emails from Google Sheets: {e}")
        return []


def send_alerts(alerts):
    """Send email alerts."""
    recipients = get_subscriber_emails()
    if not recipients:
        print("No subscribers found. Exiting.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"Stock Price Alerts - {timestamp}"
    body = format_alert_email(alerts)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL, PASSWORD)
            for recipient in recipients:
                msg = MIMEText(body, 'html')
                msg['Subject'] = subject
                msg['From'] = EMAIL
                msg['To'] = recipient
                server.sendmail(EMAIL, recipient, msg.as_string())
        print(f"Alerts sent successfully to {len(recipients)} recipients.")
    except Exception as e:
        print(f"Error sending email alerts: {e}")


def save_to_file(data, file_path):
    """Save data to a JSON file."""
    try:
        with open(file_path, "w") as file:
            json.dump(data, file, indent=4)
        print(f"Stock data saved to {file_path}")
    except Exception as e:
        print(f"Error saving stock data to file: {e}")


def notify_site():
    """Notify the website that new data is available."""
    try:
        response = requests.post(SITE_URL)
        if response.status_code == 200:
            print("Website notified of new data.")
        else:
            print(f"Failed to notify website: {response.status_code}")
    except Exception as e:
        print(f"Error notifying website: {e}")


if __name__ == "__main__":
    stock_symbols = read_stock_symbols(CSV_FILE)
    if not stock_symbols:
        print("No stock symbols found. Exiting.")
        exit()

    stock_data = fetch_stock_data(stock_symbols)
    if stock_data is None:
        print("Failed to fetch stock data. Exiting.")
        exit()

    alerts = []
    for symbol in stock_symbols:
        if symbol in stock_data.columns.levels[0]:
            stock_alerts = process_stock_data(symbol, stock_data[symbol], [200, 50, 8])
            alerts.extend(stock_alerts)

    # Save data to file and notify site
    save_to_file(alerts, DATA_FILE)
    notify_site()

    # Send email alerts
    if alerts:
        send_alerts(alerts)
    else:
        print("No alerts generated.")

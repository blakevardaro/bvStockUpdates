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
import warnings
import pandas as pd

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

def calculate_macd(data):
    """Calculate MACD and Signal Line."""
    try:
        # Suppress SettingWithCopyWarning
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=pd.errors.SettingWithCopyWarning)

            data['EMA12'] = data['Close'].ewm(span=12, adjust=False).mean()
            data['EMA26'] = data['Close'].ewm(span=26, adjust=False).mean()
            data['MACD'] = data['EMA12'] - data['EMA26']
            data['Signal_Line'] = data['MACD'].ewm(span=9, adjust=False).mean()

        return data['MACD'].iloc[-1], data['Signal_Line'].iloc[-1]
    except Exception as e:
        print(f"Error calculating MACD: {e}")
        return None, None

def calculate_rsi(data, period=14):
    """Calculate Relative Strength Index (RSI) using Wilder's method."""
    try:
        delta = data['Close'].diff(1)
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]
    except Exception as e:
        print(f"Error calculating RSI: {e}")
        return None

def process_stock_data(symbol, data, periods):
    """Process stock data to generate alerts."""
    try:
        current_price = data['Close'].iloc[-1]
        moving_averages = calculate_moving_averages(data, periods)
        macd, signal = calculate_macd(data)
        rsi = calculate_rsi(data)

        alert = {
            "symbol": symbol,
            "current_price": current_price,
            "moving_averages": moving_averages,
            "macd": macd,
            "signal": signal,
            "rsi": rsi,
            "percent_differences": {period: ((current_price - avg) / avg) * 100 for period, avg in moving_averages.items()}
        }

        if (
            current_price > moving_averages.get(200, 0)
            and current_price > moving_averages.get(50, 0)
            and current_price > moving_averages.get(8, 0)
            and macd > signal
            and 50 <= rsi < 70
        ):
            alert["highlighted"] = True
        else:
            alert["highlighted"] = False

        return alert
    except Exception as e:
        print(f"Error processing stock data for {symbol}: {e}")
        return None

def format_alert_email(alerts):
    """Format the email body with alerts."""
    alerts_by_symbol = defaultdict(list)
    for alert in alerts:
        if alert["highlighted"]:
            alerts_by_symbol[alert["symbol"].upper()].append(alert)

    sorted_symbols = sorted(alerts_by_symbol.keys())

    body = "<html><body>"
    body += "<h2><a href='http://34.23.138.210:5000/#stock-alerts-section'>Highlighted Stocks</a></h2><ul>"

    for symbol in sorted_symbols:
        alert = alerts_by_symbol[symbol][0]
        current_price = alert["current_price"]
        yahoo_link = f"https://finance.yahoo.com/quote/{symbol}"

        body += f"<li><strong><a href='{yahoo_link}' style='text-decoration:underline; color:blue;'>{symbol}</a> <span style='color:green; font-weight:bold;'>${current_price:.2f}</span></strong></li>"
        body += "<ul>"

        for period, avg in alert["moving_averages"].items():
            percent_diff = alert["percent_differences"][period]
            body += f"<li>{period}-day Moving Average: <span style='color:blue; font-weight:bold;'>${avg:.2f}</span> (<span style='font-weight:bold;'>{percent_diff:.2f}%</span>)</li>"

        macd_color = "green" if alert["macd"] > alert["signal"] else "red"
        body += f"<li>MACD: <span style='color:{macd_color}; font-weight:bold;'>{alert['macd']:.2f}</span> (<span style='font-weight:bold;'>Signal: {alert['signal']:.2f}</span>)</li>"

        rsi_color = "green" if 50 <= alert["rsi"] < 70 else "yellow" if alert["rsi"] >= 70 else "red"
        body += f"<li>RSI: <span style='color:{rsi_color}; font-weight:bold;'>{alert['rsi']:.2f}</span></li>"

        body += "</ul><br>"

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

    all_stock_data = []
    alerts = []

    for symbol in stock_symbols:
        if symbol in stock_data.columns.levels[0]:
            alert = process_stock_data(symbol, stock_data[symbol], [200, 50, 8])
            stock_entry = {
                "symbol": symbol,
                "current_price": stock_data[symbol]['Close'].iloc[-1],
                "macd": alert['macd'] if alert else None,
                "signal": alert['signal'] if alert else None,
                "rsi": alert['rsi'] if alert else None,
                "moving_averages": alert['moving_averages'] if alert else {},
                "highlighted": alert['highlighted'] if alert else False
            }
            all_stock_data.append(stock_entry)
            if alert and alert['highlighted']:
                alerts.append(alert)

    save_to_file(all_stock_data, DATA_FILE)
    notify_site()

    if alerts:
        send_alerts(alerts)
    else:
        print("No alerts generated.")
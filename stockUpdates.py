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
import numpy as np

# Load environment variables
load_dotenv()

# Email Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# Google Sheets Configuration
Subscriber_SHEET_ID = os.getenv("SubscriberList_SHEET_ID")
Stocks_Sheet_ID = os.getenv("StocksList_SHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")

DATA_FILE = "stock_data.json"  # File to store fetched stock data
SITE_URL = "http://localhost:5000/notify"  # Endpoint to notify site on port 5000 of new data

# Read stock symbols and company names from a Google Sheet
def read_stock_symbols_from_sheet():
    try:
        creds = Credentials.from_service_account_file(
            CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        # Fetch stock symbols and company names
        result = sheet.values().get(
            spreadsheetId=os.getenv("StocksList_SHEET_ID"),
            range="A:B"  # Adjust the range to include both columns A and B
        ).execute()
        values = result.get("values", [])
        
        # Skip the first row (headers) and process the rest
        return {row[0]: row[1] for row in values[1:] if len(row) > 1}
    except Exception as e:
        print(f"Error fetching stock symbols from Google Sheets: {e}")
        return {}

# Fetch data for multiple stocks
def fetch_stock_data(symbols, period="1y"):
        try:
            return yf.download(tickers=" ".join(symbols), period=period, group_by="ticker", threads=True, progress=False)
        except Exception as e:
            print(f"Error fetching stock data: {e}")
            return None

# Calculate moving averages for a single stock
def calculate_moving_averages(data, periods):
    moving_averages = {}
    try:
        for period in periods:
            if len(data) >= period:
                moving_averages[period] = data['Close'].rolling(window=period).mean().iloc[-1]
    except Exception as e:
        print(f"Error calculating moving averages: {e}")
    return moving_averages

# Calculate MACD and Signal Line
def calculate_macd(data):
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

# Calculate Relative Strength Index (RSI) using Wilder's Smoothing method
def calculate_rsi(data, period=14):
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

# Calculate Average Directional Movement Index 
def ADX(df, n=14, n_ADX=14):
    UpI = []
    DoI = []

    for i in range(len(df) - 1):
        UpMove = df['High'].iloc[i + 1] - df['High'].iloc[i]
        DoMove = df['Low'].iloc[i] - df['Low'].iloc[i + 1]

        UpD = UpMove if (UpMove > DoMove and UpMove > 0) else 0
        DoD = DoMove if (DoMove > UpMove and DoMove > 0) else 0

        UpI.append(UpD)
        DoI.append(DoD)

    TR_l = [0]
    for i in range(len(df) - 1):
        TR = max(df['High'].iloc[i + 1], df['Close'].iloc[i]) - min(df['Low'].iloc[i + 1], df['Close'].iloc[i])
        TR_l.append(TR)

    TR_s = pd.Series(TR_l, index=df.index)
    ATR = TR_s.ewm(alpha=1/n, adjust=False).mean()

    UpI = pd.Series(UpI, index=df.index[1:]).reindex(df.index).fillna(0)
    DoI = pd.Series(DoI, index=df.index[1:]).reindex(df.index).fillna(0)

    PosDI = (UpI.ewm(alpha=1/n, adjust=False).mean() / ATR) * 100
    NegDI = (DoI.ewm(alpha=1/n, adjust=False).mean() / ATR) * 100

    denominator = PosDI + NegDI
    denominator = denominator.replace(0, np.nan)
    DX = (abs(PosDI - NegDI) / denominator) * 100

    ADX = DX.ewm(alpha=1/n_ADX, adjust=False).mean()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=pd.errors.SettingWithCopyWarning)
        df['+DI'] = PosDI
        df['-DI'] = NegDI
        df['ADX'] = ADX

    return df

# Analyze stock data for each symbol and generate alert if criteria are met
def process_stock_data(symbol, data, periods):
    try:
        data = ADX(data)
        current_price = data['Close'].iloc[-1]
        moving_averages = calculate_moving_averages(data, periods)
        macd, signal = calculate_macd(data)
        rsi = calculate_rsi(data)

        # Check for NaN values
        if any(np.isnan(value) for value in [current_price, macd, signal, rsi]):
            print(f"Skipping {symbol} due to NaN values.")
            return None

        alert = {
            "symbol": symbol,
            "current_price": current_price,
            "moving_averages": moving_averages,
            "macd": macd,
            "signal": signal,
            "rsi": rsi,
            "adx": data['ADX'].iloc[-1],
            "+di": data['+DI'].iloc[-1],
            "-di": data['-DI'].iloc[-1],
            "percent_differences": {
                period: ((current_price - avg) / avg) * 100 for period, avg in moving_averages.items()
            },
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

# Format the email alert using html
def format_alert_email(alerts, stock_data_dict):
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
        company_name = stock_data_dict[symbol]  # Get the company name
        yahoo_link = f"https://finance.yahoo.com/chart/{symbol}"

        body += f"<li><strong><a href='{yahoo_link}' style='text-decoration:underline; color:blue;'>{symbol} ({company_name})</a> <span style='color:green; font-weight:bold;'>${current_price:.2f}</span></strong></li>"
        body += "<ul>"

        for period, avg in alert["moving_averages"].items():
            percent_diff = alert["percent_differences"][period]
            body += f"<li>{period}-day Moving Average: <span style='color:blue; font-weight:bold;'>${avg:.2f}</span> (<span style='font-weight:bold;'>{percent_diff:.2f}%</span>)</li>"

        macd_color = "green" if alert["macd"] > alert["signal"] else "red"
        body += f"<li>MACD: <span style='color:{macd_color}; font-weight:bold;'>{alert['macd']:.2f}</span> (<span style='font-weight:bold;'>Signal: {alert['signal']:.2f}</span>)</li>"

        rsi_color = "green" if 50 <= alert["rsi"] < 70 else "yellow" if alert["rsi"] >= 70 else "red"
        body += f"<li>RSI: <span style='color:{rsi_color}; font-weight:bold;'>{alert['rsi']:.2f}</span></li>"

        body += f"<li>ADX: <span style='color:black; font-weight:bold;'>{alert['adx']:.2f}</span></li>"
        body += f"<li>+DI: <span style='color:green; font-weight:bold;'>{alert['+di']:.2f}</span></li>"
        body += f"<li>-DI: <span style='color:red; font-weight:bold;'>{alert['-di']:.2f}</span></li>"

        body += "</ul><br>"

    body += "</ul></body></html>"
    return body

# Fetch subscriber emails from Google Sheets
def get_subscriber_emails():
    try:
        creds = Credentials.from_service_account_file(
            CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        subscriber_sheet_id = os.getenv("SubscriberList_SHEET_ID")
        result = sheet.values().get(
            spreadsheetId=subscriber_sheet_id,
            range="A:A"  # Adjust the range to include subscriber column only
        ).execute()
        values = result.get("values", [])
        return [row[0] for row in values if row]
    except Exception as e:
        print(f"Error fetching emails from Google Sheets: {e}")
        return []

# Send email alerts with stock information and company names
def send_alerts(alerts, stock_data_dict):
    recipients = get_subscriber_emails()
    if not recipients:
        print("No subscribers found. Exiting.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"Stock Price Alerts - {timestamp}"
    body = format_alert_email(alerts, stock_data_dict)  # Pass stock_data_dict to format_alert_email for formatting

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

# Save data to a JSON file, skipping entries with NaN values
def save_to_file(data, file_path):
    try:
        # Filter out entries with NaN values, else nothing will display on the frontend
        cleaned_data = [
            entry for entry in data
            if not any(np.isnan(value) for key, value in entry.items() if isinstance(value, (float, int)))
        ]
        
        with open(file_path, "w") as file:
            json.dump(cleaned_data, file, indent=4)
        print(f"Cleaned stock data saved to {file_path}")
    except Exception as e:
        print(f"Error saving stock data to file: {e}")

# Notify the website that new data is available
def notify_site():
    try:
        response = requests.post(SITE_URL)
        if response.status_code == 200:
            print("Website notified of new data.")
        else:
            print(f"Failed to notify website: {response.status_code}")
    except Exception as e:
        print(f"Error notifying website: {e}")

if __name__ == "__main__":
    stock_data_dict = read_stock_symbols_from_sheet()  # Fetch symbols and names as a dictionary
    if not stock_data_dict:
        print("No stock symbols found in Google Sheet. Exiting.")
        exit()

    stock_symbols = list(stock_data_dict.keys())  # Extract symbols
    stock_data = fetch_stock_data(stock_symbols)
    if stock_data is None:
        print("Failed to fetch stock data. Exiting.")
        exit()

    all_stock_data = []
    alerts = []

    for symbol in stock_symbols:
        if symbol in stock_data.columns.levels[0]:
            alert = process_stock_data(symbol, stock_data[symbol], [200, 50, 20, 8])
            stock_entry = {
                "symbol": symbol,
                "company_name": stock_data_dict[symbol],
                "current_price": stock_data[symbol]['Close'].iloc[-1],
                "macd": alert['macd'] if alert else None,
                "signal": alert['signal'] if alert else None,
                "rsi": alert['rsi'] if alert else None,
                "adx": alert['adx'] if alert else None,
                "+di": alert['+di'] if alert else None,
                "-di": alert['-di'] if alert else None,
                "moving_averages": alert['moving_averages'] if alert else {},
                "highlighted": alert['highlighted'] if alert else False
            }
            all_stock_data.append(stock_entry)
            if alert and alert['highlighted']:
                alerts.append(alert)

    save_to_file(all_stock_data, DATA_FILE)

    if alerts:
        send_alerts(alerts, stock_data_dict)
    else:
        print("No alerts generated.")
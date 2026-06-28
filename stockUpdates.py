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
from concurrent.futures import ThreadPoolExecutor, as_completed
from retrying import retry
import argparse
import multiprocessing

parser = argparse.ArgumentParser(description="Stock Analysis Script")
args = parser.parse_args()

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
Subscriber_SHEET_ID = os.getenv("SubscriberList_SHEET_ID")
Stocks_Sheet_ID = os.getenv("StocksList_SHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")
DATA_FILE = "stock_data.json"
SITE_URL = "http://localhost:5000/notify"

def read_stock_symbols_from_sheet():
    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=Stocks_Sheet_ID, range="A:B").execute()
        values = result.get("values", [])
        result = {row[0]: row[1] for row in values[1:] if len(row) > 1}
        print(f"Fetched {len(result)} stock symbols from Google Sheet")
        return result
    except Exception as e:
        print(f"Error fetching stock symbols from Google Sheets: {e}")
        return {}

@retry(stop_max_attempt_number=1, wait_fixed=500)
def fetch_stock_data_batch(symbols, period="1y"):
    try:
        return yf.download(tickers=" ".join(symbols), period=period, interval="1d", group_by="ticker", threads=True, progress=False, auto_adjust=False)
    except Exception as e:
        print(f"Error fetching stock data for batch {symbols[:5]}...: {e}")
        raise

def fetch_stock_data(symbols, period="1y", batch_size=100):
    all_data = {}
    print(f"Fetching data for {len(symbols)} stocks")
    failed_symbols = []
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        try:
            data = fetch_stock_data_batch(batch, period)
            if isinstance(data, pd.DataFrame):
                if len(batch) == 1:
                    all_data[batch[0]] = data
                else:
                    for symbol in batch:
                        if symbol in data.columns.levels[0]:
                            all_data[symbol] = data[symbol]
                        else:
                            all_data[symbol] = pd.DataFrame()
                            failed_symbols.append(symbol)
        except Exception as e:
            print(f"Failed to fetch batch {batch[:5]}...: {e}")
            failed_symbols.extend(batch)
    if failed_symbols:
        print(f"Failed to fetch data for {len(failed_symbols)} symbols: {failed_symbols[:10]}{'...' if len(failed_symbols) > 10 else ''}")
    return all_data

def calculate_moving_averages(data, periods):
    moving_averages = {}
    try:
        for period in periods:
            if len(data) >= period:
                moving_averages[period] = data['Close'].rolling(window=period).mean().iloc[-1]
            else:
                print(f"Insufficient data for {period}-day MA: only {len(data)} days available")
    except Exception as e:
        print(f"Error calculating moving averages: {e}")
    return moving_averages

def calculate_macd(data):
    try:
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

def rma(x, n):
    y = x.ewm(alpha=1/n, adjust=False).mean()
    return y

def calculate_adx(df, n=14):
    try:
        df = df.copy()
        df['TR'] = pd.concat([
            (df['High'] - df['Low']),
            (df['High'] - df['Close'].shift()).abs(),
            (df['Low'] - df['Close'].shift()).abs()
        ], axis=1).max(axis=1)

        df['+DM'] = df['High'].diff().clip(lower=0)
        df['-DM'] = (-df['Low'].diff()).clip(lower=0)
        df.loc[df['+DM'] < df['-DM'], '+DM'] = 0
        df.loc[df['-DM'] < df['+DM'], '-DM'] = 0

        df['TR_rma'] = rma(df['TR'], n)
        df['+DM_rma'] = rma(df['+DM'], n)
        df['-DM_rma'] = rma(df['-DM'], n)

        df['+DI'] = 100 * df['+DM_rma'] / df['TR_rma']
        df['-DI'] = 100 * df['-DM_rma'] / df['TR_rma']
        df['DX'] = (100 * (df['+DI'] - df['-DI']).abs() /
                    (df['+DI'] + df['-DI']))

        df['ADX'] = rma(df['DX'], n)
        df['+DI'] = df['+DI'].fillna(0)
        df['-DI'] = df['-DI'].fillna(0)
        df['ADX'] = df['ADX'].fillna(0)
        if np.isnan(df['ADX'].iloc[-1]) or np.isnan(df['+DI'].iloc[-1]) or np.isnan(df['-DI'].iloc[-1]):
            print("Warning: NaN values detected in ADX calculation")
        return df
    except Exception as e:
        print(f"Error calculating ADX: {e}")
        return df

def process_stock_data(args):
    symbol, data, periods = args
    try:
        if data.empty or len(data) < 26:
            print(f"Skipping {symbol} due to insufficient data")
            return None
        data = calculate_adx(data)
        current_price = data['Close'].iloc[-1]
        moving_averages = calculate_moving_averages(data, periods)
        macd, signal = calculate_macd(data)
        rsi = calculate_rsi(data)
        if np.isnan(current_price):
            print(f"Skipping {symbol} due to NaN current price")
            return None
        alert = {
            "symbol": symbol,
            "current_price": current_price,
            "moving_averages": moving_averages,
            "macd": macd if macd is not None else 0,
            "signal": signal if signal is not None else 0,
            "rsi": rsi if rsi is not None else 0,
            "adx": data['ADX'].iloc[-1] if not np.isnan(data['ADX'].iloc[-1]) else 0,
            "+di": data['+DI'].iloc[-1] if not np.isnan(data['+DI'].iloc[-1]) else 0,
            "-di": data['-DI'].iloc[-1] if not np.isnan(data['-DI'].iloc[-1]) else 0,
            "percent_differences": {
                period: ((current_price - avg) / avg) * 100 for period, avg in moving_averages.items()
            },
        }
        if (
            current_price > moving_averages.get(200, 0)
            and current_price > moving_averages.get(50, 0)
            and current_price > moving_averages.get(8, 0)
            and macd is not None and signal is not None and macd > signal
            and rsi is not None and 50 <= rsi < 70
        ):
            alert["highlighted"] = True
        else:
            alert["highlighted"] = False
        return alert
    except Exception as e:
        print(f"Error processing stock data for {symbol}: {e}")
        return None

def format_alert_email(alerts, stock_data_dict):
    alerts_by_symbol = defaultdict(list)
    for alert in alerts:
        if alert and alert["highlighted"]:
            alerts_by_symbol[alert["symbol"].upper()].append(alert)
    sorted_symbols = sorted(alerts_by_symbol.keys())
    
    body = "<html><body><h2><a href='http://34.24.10.62:5000/#stock-alerts-section'>Highlighted Stocks</a></h2><table cellpadding='0' cellspacing='0' style='border-collapse:collapse; width:100%; font-family: Arial, sans-serif; margin-bottom:20px;'><tr style='background-color:#f2f2f2;'><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>Stock</th><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>Current Price</th><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>20-day MA</th><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>8-day MA</th><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>50-day MA</th><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>200-day MA</th><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>MACD</th><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>Signal</th><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>RSI</th><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>ADX</th><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>+DI</th><th style='border:1px solid #cccccc; border-bottom:3px solid #000000; padding:8px 12px;'>-DI</th></tr>"
    
    for i, symbol in enumerate(sorted_symbols):
        alert = alerts_by_symbol[symbol][0]
        current_price = alert["current_price"]
        company_name = stock_data_dict.get(symbol, "Unknown")
        yahoo_link = f"https://finance.yahoo.com/chart/{symbol}"
        row_bg = "#fafafa" if i % 2 == 0 else "#ffffff"
        macd_color = "green" if alert["macd"] > alert["signal"] else "red"
        rsi_color = "green" if 50 <= alert["rsi"] < 70 else "yellow" if alert["rsi"] >= 70 else "red"
        
        def format_ma(period):
            value = alert["moving_averages"].get(str(period), alert["moving_averages"].get(period, 0))
            return f"<span style='color:blue; font-weight:bold;'>${value:.2f}</span>"
        
        body += f"<tr style='background-color:{row_bg}; border-bottom:3px solid #000000;'><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'><a href='{yahoo_link}' style='text-decoration:underline; color:blue;'><strong>{symbol} ({company_name})</strong></a></td><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'><span style='color:green; font-weight:bold;'>${current_price:.2f}</span></td><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'>{format_ma(20)}</td><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'>{format_ma(8)}</td><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'>{format_ma(50)}</td><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'>{format_ma(200)}</td><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'><span style='color:{macd_color}; font-weight:bold;'>{alert['macd']:.2f}</span></td><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'><span style='color:black; font-weight:bold;'>{alert['signal']:.2f}</span></td><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'><span style='color:{rsi_color}; font-weight:bold;'>{alert['rsi']:.2f}</span></td><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'><span style='color:black; font-weight:bold;'>{alert['adx']:.2f}</span></td><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'><span style='color:green; font-weight:bold;'>{alert['+di']:.2f}</span></td><td style='border:1px solid #cccccc; padding:8px 12px; text-align:center;'><span style='color:red; font-weight:bold;'>{alert['-di']:.2f}</span></td></tr>"
    
    body += "</table></body></html>"
    print(f"Generated email content for {len(sorted_symbols)} highlighted stocks")
    return body

def get_subscriber_emails():
    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=Subscriber_SHEET_ID, range="A:A").execute()
        values = result.get("values", [])
        result = [row[0] for row in values if row]
        print(f"Fetched {len(result)} subscriber emails")
        return result
    except Exception as e:
        print(f"Error fetching emails from Google Sheets: {e}")
        return []

def send_alerts(alerts, stock_data_dict):
    recipients = get_subscriber_emails()
    if not recipients:
        print("No subscribers found. Exiting.")
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"Stock Price Alerts - {timestamp}"
    body = format_alert_email(alerts, stock_data_dict)
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL, PASSWORD)
            msg = MIMEText(body, 'html')
            msg['Subject'] = subject
            msg['From'] = EMAIL
            msg['To'] = 'undisclosed-recipients:;'
            server.sendmail(EMAIL, recipients, msg.as_string())
        print(f"Sent alerts to {len(recipients)} recipients using BCC")
    except Exception as e:
        print(f"Error sending email alerts: {e}")

def save_to_file(data, file_path):
    try:
        def is_invalid(value):
            """Returns True if the value is a math NaN, None, or a nested dict with invalid values."""
            if value is None:
                return True
            if isinstance(value, float) and np.isnan(value):
                return True
            if isinstance(value, dict):
                return any(is_invalid(v) for v in value.values())
            return False

        fully_validated_data = []
        for entry in data:
            if not entry:
                continue
            
            if any(is_invalid(val) for val in entry.values()):
                print(f"Skipping storage for symbol: {entry.get('symbol', 'UNKNOWN')} due to missing/NaN data.")
                continue
                
            fully_validated_data.append(entry)

        with open(file_path, "w") as file:
            json.dump(fully_validated_data, file, indent=4)
            
        print(f"Saved {len(fully_validated_data)} fully completed stock entries to {file_path}")
    except Exception as e:
        print(f"Error saving stock data to file: {e}")

def notify_site():
    try:
        response = requests.post(SITE_URL)
        if response.status_code == 200:
            print("Website notified of new data")
        else:
            print(f"Failed to notify website: {response.status_code}")
    except Exception as e:
        print(f"Error notifying website: {e}")

if __name__ == "__main__":
    print("Starting stock analysis...")
    stock_data_dict = read_stock_symbols_from_sheet()
    if not stock_data_dict:
        print("No stock symbols found in Google Sheet. Exiting.")
        exit()
    stock_symbols = list(stock_data_dict.keys())
    stock_data = fetch_stock_data(stock_symbols)
    all_stock_data = []
    alerts = []
    processed_count = 0
    skipped_count = 0
    max_workers = min(multiprocessing.cpu_count(), 8)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_stock_data, (symbol, stock_data.get(symbol, pd.DataFrame()), [20, 8, 50, 200])) for symbol in stock_symbols]
        for future in as_completed(futures):
            alert = future.result()
            if alert:
                stock_entry = {
                    "symbol": alert["symbol"],
                    "company_name": stock_data_dict.get(alert["symbol"], "Unknown"),
                    "current_price": alert["current_price"],
                    "macd": alert["macd"],
                    "signal": alert["signal"],
                    "rsi": alert["rsi"],
                    "adx": alert["adx"],
                    "+di": alert["+di"],
                    "-di": alert["-di"],
                    "moving_averages": alert["moving_averages"],
                    "highlighted": alert["highlighted"]
                }
                all_stock_data.append(stock_entry)
                if alert["highlighted"]:
                    alerts.append(alert)
                processed_count += 1
            else:
                skipped_count += 1
    print(f"Processed {processed_count}/{len(stock_symbols)} stocks, skipped {skipped_count}")
    print(f"Generated {len(alerts)} alerts")
    save_to_file(all_stock_data, DATA_FILE)
    if alerts:
        send_alerts(alerts, stock_data_dict)
        notify_site()
    else:
        print("No alerts generated")
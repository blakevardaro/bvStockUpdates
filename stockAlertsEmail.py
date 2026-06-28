import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from dotenv import load_dotenv
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
import matplotlib.dates as mdates

# Load environment variables
load_dotenv()
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# Hardcoded recipients
RECIPIENTS = ["blake.vardaro@gmail.com", "mark.vardaro@yahoo.com"]

# Ensure charts directory exists for debugging
if not os.path.exists("charts"):
    os.makedirs("charts")

# Load stock data from JSON
with open("stock_data.json", "r") as f:
    stock_data = json.load(f)

def passes_criteria(stock):
    """Check stock against alert criteria with new ADX and +DI/-DI rules."""
    ma8 = stock["moving_averages"].get("8", 0)
    ma20 = stock["moving_averages"].get("20", 0)
    adx = stock.get("adx", 0)
    plus_di = stock.get("+di", 0)
    minus_di = stock.get("-di", 0)
    rsi = stock.get("rsi", 0)
    macd = stock.get("macd", 0)
    signal = stock.get("signal", 0)
    failures = []
    if not (ma8 < ma20):
        failures.append("8-day MA not < 20-day MA")
    if not (plus_di > minus_di):
        failures.append("+DI not > -DI")
    if not (adx < plus_di and adx < minus_di):
        failures.append("ADX not < +DI and -DI")
    if not (rsi <= 70):
        failures.append("RSI > 70")
    if not (macd <= signal):
        failures.append("MACD > Signal")
    return failures

def rma(x, n):
    """Calculate exponential moving average for ADX."""
    return x.ewm(alpha=1/n, adjust=False).mean()

def calculate_adx(df, n=14):
    """Calculate ADX, +DI, -DI using historical OHLC data from stockUpdates.py."""
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
                    (df['+DI'] + df['-DI']).replace(0, np.nan))
        df['ADX'] = rma(df['DX'], n)
        df['+DI'] = df['+DI'].fillna(0)
        df['-DI'] = df['-DI'].fillna(0)
        df['ADX'] = df['ADX'].fillna(0)
        return df
    except Exception as e:
        print(f"Error calculating ADX for {df.index[0] if not df.empty else 'unknown'}: {e}")
        return df

def calculate_moving_averages_series(df, periods):
    """Calculate moving averages for specified periods."""
    moving_averages = {}
    for period in periods:
        moving_averages[period] = df['Close'].rolling(window=period).mean()
    return moving_averages

def calculate_macd_series(df):
    """Calculate MACD and Signal line."""
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def calculate_rsi_series(df, period=14):
    """Calculate RSI series."""
    delta = df['Close'].diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def generate_chart(symbol, stock_metrics):
    """Generate a 6-month stock chart with properly spaced labels and full 200-day MA."""
    try:
        # Fetch 1.5 years of daily data to ensure enough for MA200
        data = yf.download(symbol, period='18mo', interval='1d', progress=False, auto_adjust=False)
        if data.empty or len(data) < 200:
            print(f"No or insufficient data for {symbol} (len={len(data)})")
            return None
        df = data[['High', 'Low', 'Close']].copy()
        # Compute MAs, MACD, RSI, ADX on the full dataframe
        periods = [8, 20, 50, 200]
        mas = calculate_moving_averages_series(df, periods)
        for period in periods:
            df[f'MA{period}'] = mas[period]
        macd_series, signal_series = calculate_macd_series(df)
        df['MACD'] = macd_series
        df['Signal'] = signal_series
        df['Histogram'] = df['MACD'] - df['Signal']
        df['RSI'] = calculate_rsi_series(df)
        df = calculate_adx(df)
        # Slice last 6 months for plotting (~126 trading days)
        df_plot = df.iloc[-126:] if len(df) > 126 else df
        # Debug: Check MA200 data points and NaN count
        print(f"MA200 data points for {symbol}: {len(df_plot['MA200'])}")
        nan_count = df_plot['MA200'].isna().sum()
        if nan_count > 0:
            print(f"Warning: MA200 contains {nan_count} NaN values for {symbol}")
        # Verify data integrity
        required_columns = ['Close', 'MA8', 'MA20', 'MA50', 'MA200', 'MACD', 'Signal', 'Histogram', 'RSI', 'ADX', '+DI', '-DI']
        missing_columns = [col for col in required_columns if col not in df_plot.columns]
        if missing_columns:
            print(f"Missing columns for {symbol}: {missing_columns}")
            return None
        if df_plot[required_columns].isnull().all().any():
            print(f"Invalid data for {symbol}: contains all NaN for some indicators")
            return None
        # Skip MA200 plotting if too few valid points
        ma200_valid = df_plot['MA200'].dropna()
        if len(ma200_valid) < len(df_plot) * 0.5:
            print(f"Warning: Insufficient valid MA200 data for {symbol} ({len(ma200_valid)} points)")
            ma200_valid = pd.Series(dtype=float)  # Empty series to skip plotting
        # Extract latest metrics safely
        current_price = float(stock_metrics["current_price"] if isinstance(stock_metrics["current_price"], (int, float)) else stock_metrics["current_price"].item())
        ma8 = float(stock_metrics["moving_averages"].get("8", 0))
        ma20 = float(stock_metrics["moving_averages"].get("20", 0))
        ma50 = float(stock_metrics["moving_averages"].get("50", 0))
        ma200 = float(stock_metrics["moving_averages"].get("200", 0))
        macd = float(stock_metrics["macd"] if isinstance(stock_metrics["macd"], (int, float)) else stock_metrics["macd"].item())
        signal = float(stock_metrics["signal"] if isinstance(stock_metrics["signal"], (int, float)) else stock_metrics["signal"].item())
        rsi = float(stock_metrics["rsi"] if isinstance(stock_metrics["rsi"], (int, float)) else stock_metrics["rsi"].item())
        adx = float(stock_metrics["adx"] if isinstance(stock_metrics["adx"], (int, float)) else stock_metrics["adx"].item())
        plus_di = float(stock_metrics["+di"] if isinstance(stock_metrics["+di"], (int, float)) else stock_metrics["+di"].item())
        minus_di = float(stock_metrics["-di"] if isinstance(stock_metrics["-di"], (int, float)) else stock_metrics["-di"].item())
        # Create figure
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), sharex=True, gridspec_kw={'height_ratios': [3, 1, 1, 1]})
        fig.suptitle(f"{symbol} Stock Chart (6 Months)", fontsize=14, weight='bold', y=0.98)
        x_right = df_plot.index[-1] + pd.Timedelta(days=0.5)  # Tighter horizontal spacing
        # ----- Panel 1: Price and MAs -----
        axs[0].plot(df_plot.index, df_plot['Close'], label='Close', color='blue')
        axs[0].plot(df_plot.index, df_plot['MA8'], label='8-day MA', color='red')
        axs[0].plot(df_plot.index, df_plot['MA20'], label='20-day MA', color='green')
        axs[0].plot(df_plot.index, df_plot['MA50'], label='50-day MA', color='orange')
        if len(ma200_valid) > 0:
            axs[0].plot(ma200_valid.index, ma200_valid, label='200-day MA', color='purple')
        axs[0].set_ylabel('Price ($)', fontsize=10)
        axs[0].legend(loc='upper left', fontsize=8)
        axs[0].grid(True, linestyle='--', alpha=0.7)
        # Custom y-offsets for price panel
        price_values = [
            ('Close', df_plot['Close'].iloc[-1].item(), current_price, 'blue'),
            ('MA8', df_plot['MA8'].iloc[-1].item(), ma8, 'red'),
            ('MA20', df_plot['MA20'].iloc[-1].item(), ma20, 'green'),
            ('MA50', df_plot['MA50'].iloc[-1].item(), ma50, 'orange')
        ]
        if len(ma200_valid) > 0 and not pd.isna(df_plot['MA200'].iloc[-1]):
            price_values.append(('MA200', df_plot['MA200'].iloc[-1].item(), ma200, 'purple'))
        price_values.sort(key=lambda x: x[1], reverse=True)
        price_range = df_plot['Close'].max() - df_plot['Close'].min()
        offsets = [0.02, -0.02, 0.05, -0.05, 0.08][:len(price_values)]  # Tighter offsets
        offsets = [o * price_range for o in offsets]
        for i, (name, y_val, value, color) in enumerate(price_values):
            text = f"{float(value):.2f}" if isinstance(value, (int, float)) else "N/A"
            axs[0].text(x_right, y_val + offsets[i], text, color=color, fontsize=8, va='center', ha='left', weight='bold')
        # ----- Panel 2: MACD -----
        hist_diff = df_plot['Histogram'].diff()
        colors = ['green' if h > 0 else 'red' for h in hist_diff]
        colors[0] = 'green' if df_plot['Histogram'].iloc[0] > 0 else 'red'
        axs[1].plot(df_plot.index, df_plot['MACD'], label='MACD', color='blue')
        axs[1].plot(df_plot.index, df_plot['Signal'], label='Signal', color='red')
        axs[1].bar(df_plot.index, df_plot['Histogram'], label='Histogram', color=colors, alpha=0.5)
        axs[1].set_ylabel('MACD', fontsize=10)
        axs[1].legend(loc='upper left', fontsize=8)
        axs[1].grid(True, linestyle='--', alpha=0.7)
        macd_values = [
            ('MACD', df_plot['MACD'].iloc[-1].item(), macd, 'blue'),
            ('Signal', df_plot['Signal'].iloc[-1].item(), signal, 'red')
        ]
        macd_values.sort(key=lambda x: x[1], reverse=True)
        macd_range = df_plot['MACD'].max() - df_plot['MACD'].min()
        macd_offsets = [0.01 * macd_range, -0.01 * macd_range]  # Tighter offsets
        for i, (name, y_val, value, color) in enumerate(macd_values):
            axs[1].text(x_right, y_val + macd_offsets[i], f"{float(value):.2f}",
                        color=color, fontsize=8, va='center', ha='left', weight='bold')
        # ----- Panel 3: RSI -----
        last_rsi = df_plot['RSI'].iloc[-1].item()
        axs[2].plot(df_plot.index, df_plot['RSI'], label='RSI', color='blue')
        axs[2].axhline(70, color='red', linestyle='--', label='Overbought (70)')
        axs[2].axhline(30, color='green', linestyle='--', label='Oversold (30)')
        axs[2].set_ylabel('RSI', fontsize=10)
        axs[2].legend(loc='upper left', fontsize=8)
        axs[2].grid(True, linestyle='--', alpha=0.7)
        axs[2].text(x_right, last_rsi, f"{float(rsi):.2f}",
                    color='blue', fontsize=8, va='center', ha='left', weight='bold')
        # ----- Panel 4: ADX / +DI / -DI -----
        last_adx = df_plot['ADX'].iloc[-1].item()
        last_plus_di = df_plot['+DI'].iloc[-1].item()
        last_minus_di = df_plot['-DI'].iloc[-1].item()
        axs[3].plot(df_plot.index, df_plot['ADX'], label='ADX', color='black')
        axs[3].plot(df_plot.index, df_plot['+DI'], label='+DI', color='green')
        axs[3].plot(df_plot.index, df_plot['-DI'], label='-DI', color='red')
        for i in range(1, len(df_plot)):
            x = [df_plot.index[i-1], df_plot.index[i]]
            y1 = [df_plot['+DI'].iloc[i-1].item(), df_plot['+DI'].iloc[i].item()]
            y2 = [df_plot['-DI'].iloc[i-1].item(), df_plot['-DI'].iloc[i].item()]
            fill_color = 'green' if y1[-1] > y2[-1] else 'red'
            axs[3].fill_between(x, y1, y2, color=fill_color, alpha=0.2)
        axs[3].set_ylabel('ADX / DI', fontsize=10)
        axs[3].legend(loc='upper left', fontsize=8)
        axs[3].grid(True, linestyle='--', alpha=0.7)
        adx_values = [
            ('ADX', last_adx, adx, 'black'),
            ('+DI', last_plus_di, plus_di, 'green'),
            ('-DI', last_minus_di, minus_di, 'red')
        ]
        adx_values.sort(key=lambda x: x[1], reverse=True)
        adx_range = df_plot['ADX'].max() - df_plot['ADX'].min()
        adx_offsets = [0.015 * adx_range, -0.015 * adx_range, 0]  # Tighter offsets
        for i, (name, y_val, value, color) in enumerate(adx_values):
            axs[3].text(x_right, y_val + adx_offsets[i], f"{float(value):.2f}",
                        color=color, fontsize=8, va='center', ha='left', weight='bold')
        # X-axis formatting
        axs[3].xaxis.set_major_locator(mdates.MonthLocator())
        axs[3].xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        plt.setp(axs[3].get_xticklabels(), rotation=45, ha='right')
        plt.xlabel('Date', fontsize=10)
        plt.tight_layout(rect=[0, 0, 0.85, 0.95])
        # Save chart
        chart_path = f"charts/{symbol}.png"
        fig.savefig(chart_path, format='png', bbox_inches='tight', dpi=100)
        print(f"Saved chart for {symbol} to {chart_path}")
        buffer = BytesIO()
        fig.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
        buffer.seek(0)
        plt.close(fig)
        print(f"Generated chart for {symbol}")
        return buffer
    except Exception as e:
        print(f"Error generating chart for {symbol}: {e}")
        return None

def format_alert_email(alerts):
    """Format the alerts as an HTML email with charts and metrics on chart lines."""
    body = """
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; max-width: 800px; margin: 0 auto; padding: 20px;">
    <h2 style="text-align: center; color: #1a73e8;">Stock Alerts</h2>
    <p style="text-align: center; font-size: 14px; margin-bottom: 20px;">
        <a href="http://34.24.10.62:5000/#stock-alerts-section" style="color: #1a73e8; text-decoration: none;">
            View Alerts Dashboard
        </a>
    </p>
    """
    for i, stock in enumerate(alerts):
        yahoo_link = f"https://finance.yahoo.com/chart/{stock['symbol']}"
        row_color = "#f5f7fa" if i % 2 == 0 else "#ffffff"
        body += f"""
        <div style="margin-bottom: 30px; border: 1px solid #ddd; border-radius: 8px; padding: 15px; background-color: {row_color};">
            <h3 style="margin: 0 0 10px; color: #333; text-align: center;">
                <a href="{yahoo_link}" style="color: #1a73e8; text-decoration: none;">
                    {stock['symbol']} ({stock['company_name']})
                </a>
            </h3>
            <div style="text-align: center;">
                <img src="cid:{stock['symbol']}_chart" alt="{stock['symbol']} Chart" style="width: 500px; border: 1px solid #ddd; border-radius: 4px;" />
            </div>
        </div>
        """
    body += """
    </body>
    </html>
    """
    return body

# Collect alerts
alerts = []
for stock in stock_data:
    if not passes_criteria(stock):
        alerts.append(stock)

# Send email if there are alerts
if alerts:
    body = format_alert_email(alerts)
    msg = MIMEMultipart('related')
    msg["Subject"] = "Stock Alerts - " + pd.Timestamp.now().strftime('%Y-%m-%d')
    msg["From"] = EMAIL
    msg["To"] = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(body, "html"))
    # Generate and attach charts for each alerted stock
    for stock in alerts:
        buffer = generate_chart(stock['symbol'], stock)
        if buffer:
            img = MIMEImage(buffer.getvalue())
            img.add_header('Content-ID', f"<{stock['symbol']}_chart>")
            img.add_header('Content-Disposition', 'inline', filename=f"{stock['symbol']}_chart.png")
            msg.attach(img)
        else:
            print(f"Skipping chart attachment for {stock['symbol']} due to generation failure")
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL, PASSWORD)
            server.sendmail(EMAIL, RECIPIENTS, msg.as_string())
        print(f"📧 Alerts sent to {', '.join(RECIPIENTS)}")
    except Exception as e:
        print(f"Error sending email: {e}")
else:
    print("ℹ️ No alerts triggered.")
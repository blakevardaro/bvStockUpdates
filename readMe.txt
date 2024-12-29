bvStockUpdates.com

******************
*****Overview*****
******************
bvStockUpdates.com is a web-based application designed to provide real-time stock monitoring and alerts. Users can monitor stocks, request additional stocks to track, and subscribe to alerts for highlighted stocks based on specific technical analysis criteria.

******************
*****Features*****
******************
- Stock Monitoring: Tracks the current prices, MACD, RSI, ADX, and moving averages (8, 50, 200 days) for a list of monitored stocks.
- Subscription Management: Users can subscribe and unsubscribe to stock alerts via email.
- Stock Requests: Allows users to request new stocks for monitoring.
- Stock Alerts: Highlights stocks that meet specific criteria and emails them to subscribers.
- Integration with Yahoo Finance: Provides a guide for setting up advanced charts in Yahoo Finance.

************************
*****File Structure*****
************************
# Backend #
- app.py: Main Flask application that serves the API and HTML pages.
- stockUpdates.py: Script for fetching stock data and performing technical analysis using yfinance.

# Frontend #
- index.html: Homepage that introduces the service and provides navigation options.
- monitored-stocks.html: Page for viewing monitored stocks and requesting new ones.
- yfinance-guide.html: Instructions for setting up advanced stock charts in Yahoo Finance.

# Static Files #
- style.css: Defines the styles for the website.
- script.js: Contains JavaScript code for dynamic features such as search and form submission.

# Data #
- stock_data.json: Stores data for monitored stocks.
- requested_stocks.json: Tracks user-requested stocks.

********************************
*****Setup and Installation*****
********************************
- Clone the repository:
  git clone <repository_url>
  cd <repository_name>

- Install the required Python packages:
  pip install -r requirements.txt

- Set up environment variables:
  Create a .env file with the following variables:
    SMTP_SERVER=<your_smtp_server>
    SMTP_PORT=<your_smtp_port>
    EMAIL=<your_email>
    PASSWORD=<your_email_password>
    SubscriberList_SHEET_ID=<your_google_sheet_id>
    StocksList_SHEET_ID=<your_google_sheet_id>
    CREDENTIALS_FILE=<path_to_google_service_account_credentials>

- Run the Flask application:
  python app.py

- Open your browser and navigate to http://localhost:5000.

**********************
*****How It Works*****
**********************
# Technical Indicators #
- Current Price:
  Highlighted in green if it is above all three moving averages (8, 50, and 200-day).
  Highlighted in red if it is below all three moving averages.

- MACD:
  Used to identify momentum.
  Highlighted in green if the MACD is above the Signal Line, indicating bullish momentum.
  Highlighted in red if the MACD is below the Signal Line, indicating bearish momentum.

- RSI:
  Indicates whether a stock is overbought or oversold.
  Highlighted in green if RSI is between 50 and 70, signaling positive but stable momentum.
  Highlighted in yellow if RSI is ≥70, signaling overbought conditions.
  Highlighted in red if RSI is <50, signaling oversold conditions.

- ADX (Average Directional Index):
  Measures the strength of a trend.
  Highlighted in green if ADX > 25, indicating a strong trend.
  Highlighted in yellow if ADX is between 20 and 25, suggesting a potential trend development.
  Highlighted in red if ADX < 20, indicating a weak or no trend.

# Stock Alerts #
Highlighted stocks meet all criteria for bullish signals and are emailed to subscribers.

# Subscription #
Users can manage subscriptions directly from the homepage.

**********************
*****Contributing*****
**********************
- Navigate to the project directory root:
  git add .
  git commit -m "Comment for new commit"
  git push -u origin main

- Provide your username and password when prompted.

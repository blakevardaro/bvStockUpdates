document.addEventListener("DOMContentLoaded", () => {
  // Initialize functionality based on the current page
  const pathname = window.location.pathname;

  if (pathname === "/") {
    setupIndexPage();
  } else if (pathname === "/monitored-stocks") {
    setupMonitoredStocksPage();
  }
});

// Functionality for the index page
function setupIndexPage() {
  // Subscription form submission
  document.getElementById("subscribe-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.getElementById("email").value;

    const messageElement = document.getElementById("message");
    if (!email) {
        messageElement.style.color = "red";
        messageElement.textContent = "Please enter a valid email address.";
        return;
    }

    try {
        const response = await fetch("/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email }),
        });

        if (!response.ok) {
            throw new Error("Server returned an error");
        }

        const result = await response.json();
        messageElement.style.color = result.success ? "green" : "red";
        messageElement.textContent = result.message;
    } catch (error) {
        console.error("Error:", error);
        messageElement.style.color = "red";
        messageElement.textContent = "Error connecting to server.";
    }
});


  // Unsubscribe form submission
  document.getElementById("unsubscribe-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.getElementById("unsubscribe-email").value;

    try {
      const response = await fetch("/unsubscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const result = await response.json();
      const messageElement = document.getElementById("unsubscribe-message");

      messageElement.style.color = result.success ? "green" : "red";
      messageElement.textContent = result.message;
    } catch (error) {
      console.error("Error:", error);
      document.getElementById("unsubscribe-message").textContent = "Error connecting to server.";
    }
  });

  // Fetch and display stock alerts
  fetchStockAlerts();

  document.getElementById("search-bar").addEventListener("input", (event) => {
    const query = event.target.value.toLowerCase();

    const filteredAlerts = window.stockAlerts.filter((alert) => {
      const symbolMatch = alert.symbol.toLowerCase().includes(query);
      const companyNameMatch = alert.company_name && alert.company_name.toLowerCase().includes(query);
      return symbolMatch || companyNameMatch;
    });

    renderStockAlerts(filteredAlerts);
  });
}

async function fetchStockAlerts() {
  try {
    const response = await fetch("/stock-alerts");
    const alerts = await response.json();

    window.stockAlerts = alerts;
    renderStockAlerts(alerts);
  } catch (error) {
    console.error("Error fetching stock alerts:", error);
  }
}

function renderStockAlerts(alerts) {
  const highlightedContainer = document.getElementById("highlighted-stocks");
  const otherContainer = document.getElementById("other-stocks");

  highlightedContainer.innerHTML = "";
  otherContainer.innerHTML = "";

  const sortedAlerts = alerts
    .filter((alert) => alert.current_price !== null && !isNaN(alert.current_price))
    .sort((a, b) => a.symbol.localeCompare(b.symbol));

  sortedAlerts.forEach((alert) => {
    const card = document.createElement("div");
    card.className = "card";

    const priceStyle = Object.values(alert.moving_averages).every((avg) => alert.current_price > avg)
      ? "color:green; font-weight:bold;"
      : Object.values(alert.moving_averages).every((avg) => alert.current_price < avg)
      ? "color:red; font-weight:bold;"
      : "";

    const macdColor = alert.macd > alert.signal ? "green" : "red";
    const rsiColor =
      alert.rsi >= 70 ? "yellow" : alert.rsi >= 50 ? "green" : "red";

    const adxStyle = "color:white; font-weight:bold;";
    const plusDIStyle = "color:green; font-weight:bold;";
    const minusDIStyle = "color:red; font-weight:bold;";

    const movingAverages = Object.entries(alert.moving_averages)
      .map(([period, value]) => `<p>${period}-Day Moving Average: $${value.toFixed(2)}</p>`)
      .join("");

    card.innerHTML = `
      <h3>${alert.symbol} (${alert.company_name})</h3>
      <p>Current Price: ${
        priceStyle
          ? `<span style="${priceStyle}">$${alert.current_price.toFixed(2)}</span>`
          : `$${alert.current_price.toFixed(2)}`
      }</p>
      ${movingAverages}
      <p>MACD: <span style="color:${macdColor};">${alert.macd?.toFixed(2) || "N/A"}</span> (Signal: ${alert.signal?.toFixed(2) || "N/A"})</p>
      <p>ADX: <span style="${adxStyle}">${alert.adx?.toFixed(2) || "N/A"}</span>, 
      +DI: <span style="${plusDIStyle}">${alert["+di"]?.toFixed(2) || "N/A"}</span>, 
      -DI: <span style="${minusDIStyle}">${alert["-di"]?.toFixed(2) || "N/A"}</span></p>
      <p>RSI: <span style="color:${rsiColor};">${alert.rsi?.toFixed(2) || "N/A"}</span></p>
    `;
    card.onclick = () => window.open(`https://finance.yahoo.com/chart/${alert.symbol}`, "_blank");

    (alert.highlighted ? highlightedContainer : otherContainer).appendChild(card);
  });
}

// Functionality for the monitored stocks page
function setupMonitoredStocksPage() {
  const stocksContainer = document.getElementById("stocks-container");
  const requestForm = document.getElementById("request-stock-form");
  const requestMessage = document.getElementById("request-message");
  const requestButton = requestForm.querySelector("button[type='submit']");
  const searchBar = document.getElementById("search-bar");
  let monitoredStocks = [];

  // Fetch monitored stocks from the API
  async function fetchMonitoredStocks() {
    try {
      const response = await fetch("/monitored-stocks-api");
      const stocks = await response.json();

      if (!Array.isArray(stocks)) {
        throw new Error("Invalid data format received from API");
      }

      monitoredStocks = stocks; // Save for search functionality
      renderMonitoredStocks(stocks); // Render the full list
    } catch (error) {
      console.error("Error fetching stocks:", error);
      stocksContainer.textContent = "Failed to load monitored stocks.";
    }
  }

  // Render stocks into a three-column grid
  function renderMonitoredStocks(stocks) {
  const stocksContainer = document.getElementById("stocks-container");
  stocksContainer.innerHTML = "";

  const grid = document.createElement("div");
  grid.style.display = "grid";
  grid.style.gridTemplateColumns = "1fr 1fr 1fr";
  grid.style.gap = "10px";

  stocks.forEach((stock) => {
    const stockItem = document.createElement("div");
    stockItem.style.padding = "5px";
    stockItem.style.textAlign = "center";

    stockItem.innerHTML = `
      <a href="https://finance.yahoo.com/chart/${stock.symbol}" 
         target="_blank" 
         style="text-decoration: none; color: #ADD8E6;">
         ${stock.symbol} (${stock.company_name || "N/A"})
      </a>
    `;

    grid.appendChild(stockItem);
  });

  stocksContainer.appendChild(grid);
}


  // Handle search functionality
  searchBar.addEventListener("input", (event) => {
    const query = event.target.value.toLowerCase();

    const filteredStocks = monitoredStocks.filter((stock) => {
      const symbolMatch = stock.symbol.toLowerCase().includes(query);
      const companyNameMatch =
        stock.company_name && stock.company_name.toLowerCase().includes(query);
      return symbolMatch || companyNameMatch;
    });

    renderMonitoredStocks(filteredStocks);
  });

  // Handle stock request form submission
  requestForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const stockSymbol = document.getElementById("stock-symbol").value;

    try {
      const response = await fetch("/request-stock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: stockSymbol }),
      });
      const result = await response.json();

      requestMessage.style.color = result.success ? "green" : "red";
      requestMessage.textContent = result.message;

      if (result.success) {
        // Disable the request button and input field
        requestButton.disabled = true;
        requestForm.querySelector("input").disabled = true;

        // Refresh the stock list
        fetchMonitoredStocks();
      }
    } catch (error) {
      console.error("Error requesting stock:", error);
      requestMessage.textContent = "Error submitting request.";
    }
  });

  // Fetch the monitored stocks initially
  fetchMonitoredStocks();
}

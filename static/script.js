document.getElementById("subscribe-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = document.getElementById("email").value;

  try {
    const response = await fetch("/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const result = await response.json();
    const messageElement = document.getElementById("message");

    if (result.success) {
      messageElement.style.color = "green";
      messageElement.textContent = result.message;
    } else {
      messageElement.style.color = "red";
      messageElement.textContent = result.message;
    }
  } catch (error) {
    console.error("Error:", error);
    document.getElementById("message").textContent = "Error connecting to server.";
  }
});

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

    if (result.success) {
      messageElement.style.color = "green";
      messageElement.textContent = result.message;
    } else {
      messageElement.style.color = "red";
      messageElement.textContent = result.message;
    }
  } catch (error) {
    console.error("Error:", error);
    document.getElementById("unsubscribe-message").textContent = "Error connecting to server.";
  }
});

async function fetchStockAlerts() {
  try {
    const response = await fetch("/stock-alerts");
    const alerts = await response.json();

    console.log("Fetched alerts:", alerts); // Add this line for debugging

    // Store fetched alerts for search filtering
    window.stockAlerts = alerts;

    renderStockAlerts(alerts);
  } catch (error) {
    console.error("Error fetching stock alerts:", error);
  }
}

function renderStockAlerts(alerts) {
    const highlightedContainer = document.getElementById("highlighted-stocks");
    const otherContainer = document.getElementById("other-stocks");

    // Clear previous contents
    highlightedContainer.innerHTML = "";
    otherContainer.innerHTML = "";

    // Sort alerts alphabetically by symbol
    const sortedAlerts = alerts.sort((a, b) => a.symbol.localeCompare(b.symbol));

    sortedAlerts.forEach((alert) => {
        const card = document.createElement("div");
        card.className = "card";

        // Determine the style for the current price
        const priceAboveAll = Object.values(alert.moving_averages).every(
            (avg) => alert.current_price > avg
        );
        const priceBelowAll = Object.values(alert.moving_averages).every(
            (avg) => alert.current_price < avg
        );
        let priceStyle = "";
        if (priceAboveAll) {
            priceStyle = "color:green; font-weight:bold;";
        } else if (priceBelowAll) {
            priceStyle = "color:red; font-weight:bold;";
        }

        // Set styles for macd
        const macdColor = alert.macd > alert.signal ? "green" : "red";

        // Set styles for rsi
        let rsiColor;
        if (alert.rsi >= 70) {
            rsiColor = "yellow";
        } else if (alert.rsi >= 50) {
            rsiColor = "green";
        } else {
            rsiColor = "red";
        }

        // Generate moving averages list
        const movingAverages = Object.entries(alert.moving_averages)
            .map(([period, value]) => `<p>${period}-Day Moving Average: $${value.toFixed(2)}</p>`)
            .join("");

        card.innerHTML = `
            <h3>${alert.symbol}</h3>
            <p>Current Price: ${
                priceStyle
                    ? `<span style="${priceStyle}">$${alert.current_price.toFixed(2)}</span>`
                    : `$${alert.current_price.toFixed(2)}`
            }</p>
            ${movingAverages}
            <p>MACD: <span style="color:${macdColor};">${alert.macd !== null ? alert.macd.toFixed(2) : "N/A"}</span>
                (Signal: ${alert.signal !== null ? alert.signal.toFixed(2) : "N/A"})</p>
            <p>RSI: <span style="color:${rsiColor};">${alert.rsi !== null ? alert.rsi.toFixed(2) : "N/A"}</span></p>
        `;
        card.onclick = () =>
            window.open(`https://finance.yahoo.com/quote/${alert.symbol}`, "_blank");

        // Add card to the appropriate section
        if (alert.highlighted) {
            highlightedContainer.appendChild(card);
        } else {
            otherContainer.appendChild(card);
        }
    });
}



// Search bar functionality
document.getElementById("search-bar").addEventListener("input", (event) => {
  const query = event.target.value.toUpperCase();
  const filteredAlerts = window.stockAlerts.filter((alert) =>
    alert.symbol.includes(query)
  );
  renderStockAlerts(filteredAlerts);
});

// Initial fetch when the page loads
fetchStockAlerts();

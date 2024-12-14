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

    // Store fetched alerts for search filtering
    window.stockAlerts = alerts;

    renderStockAlerts(alerts);
  } catch (error) {
    console.error("Error fetching stock alerts:", error);
  }
}

function renderStockAlerts(alerts) {
  const stockAlertsContainer = document.getElementById("stock-alerts");
  stockAlertsContainer.innerHTML = "";
  const groupedAlerts = alerts.reduce((groups, alert) => {
    groups[alert.symbol] = groups[alert.symbol] || [];
    groups[alert.symbol].push(alert);
    return groups;
  }, {});
  const sortedSymbols = Object.keys(groupedAlerts).sort();

  sortedSymbols.forEach((symbol) => {
    const card = document.createElement("div");
    card.className = "card";
    const currentPrice = groupedAlerts[symbol][0].current_price.toFixed(2);
    card.innerHTML = `
      <h3><strong>${symbol} <span style="color:red; font-weight:bold;">$${currentPrice}</span></strong></h3>
      <ul>
        ${groupedAlerts[symbol]
          .map(
            (alert) => `
          <li>${alert.period} Moving Average: 
            <span style="color:green; font-weight:bold;">$${alert.average.toFixed(2)}</span>, 
            Difference: <span style="color:red; font-weight:bold;">$${alert.difference.toFixed(2)}</span>
            (<span style="color:blue; font-weight:bold;">${alert.percentage_change.toFixed(2)}%</span>)
          </li>`
          )
          .join("")}
      </ul>
    `;
    card.onclick = () =>
      window.open(`https://finance.yahoo.com/quote/${symbol}`, "_blank");
    stockAlertsContainer.appendChild(card);
  });
}

// Search bar functionality
const searchBar = document.getElementById("search-bar");
searchBar.addEventListener("input", (event) => {
  const query = event.target.value.toUpperCase();
  const filteredAlerts = window.stockAlerts.filter((alert) =>
    alert.symbol.includes(query)
  );
  renderStockAlerts(filteredAlerts);
});

// Set up Server-Sent Events to listen for updates
const eventSource = new EventSource("/events");
eventSource.onmessage = (event) => {
  if (event.data === "update") {
    fetchStockAlerts(); // Refresh alerts when an update is received
  }
};

// Initial fetch when the page loads
fetchStockAlerts();

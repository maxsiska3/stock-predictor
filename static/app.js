(function () {
  var form = document.getElementById("single-form");
  var input = document.getElementById("ticker-input");
  var refreshBtn = document.getElementById("refresh-btn");
  var statusEl = document.getElementById("status");
  var bodyEl = document.getElementById("pred-body");
  var metaEl = document.getElementById("table-meta");
  var summaryEl = document.getElementById("summary");
  var statUp = document.getElementById("stat-up");
  var statDown = document.getElementById("stat-down");
  var statFailed = document.getElementById("stat-failed");

  function setBusy(busy, message) {
    refreshBtn.disabled = busy;
    form.querySelector("button").disabled = busy;
    statusEl.textContent = message || "";
  }

  function directionBadge(row) {
    if (row.error) {
      return '<span class="badge badge-err" title="' + escapeHtml(row.error) + '">Error</span>';
    }
    if (row.direction === 1) {
      return '<span class="badge badge-up">▲ Up</span>';
    }
    return '<span class="badge badge-down">▼ Down</span>';
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderRows(rows) {
    if (!rows.length) {
      bodyEl.innerHTML = '<tr><td colspan="3" class="empty">No predictions yet.</td></tr>';
      return;
    }

    var sorted = rows.slice().sort(function (a, b) {
      if (a.error && !b.error) return 1;
      if (!a.error && b.error) return -1;
      return (b.confidence || 0) - (a.confidence || 0);
    });

    bodyEl.innerHTML = sorted.map(function (row, i) {
      var conf = row.error ? "N/A" : row.confidence.toFixed(2) + "%";
      return (
        "<tr class=\"pred-row\" style=\"animation-delay:" + (i < 12 ? i * 20 : 0) + "ms\">" +
        "<td><strong>" + escapeHtml(row.ticker) + "</strong></td>" +
        "<td>" + directionBadge(row) + "</td>" +
        "<td>" + conf + "</td>" +
        "</tr>"
      );
    }).join("");
  }

  function renderSummary(summary, countLabel) {
    summaryEl.hidden = false;
    statUp.textContent = summary.up;
    statDown.textContent = summary.down;
    statFailed.textContent = summary.failed;
    metaEl.textContent = countLabel;
  }

  function fetchPredictions(url, single) {
    setBusy(true, "Running model…");
    return fetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error("Request failed");
        return res.json();
      })
      .then(function (data) {
        var rows = single ? [data] : (data.predictions || []);
        var summary = single
          ? { up: data.direction === 1 ? 1 : 0, down: data.direction === 0 ? 1 : 0, failed: data.error ? 1 : 0, total: 1 }
          : (data.summary || {});
        renderRows(rows);
        renderSummary(summary, rows.length + (rows.length === 1 ? " ticker" : " tickers"));
      })
      .catch(function (err) {
        bodyEl.innerHTML = '<tr><td colspan="3" class="error-cell">' + escapeHtml(err.message) + "</td></tr>";
        statusEl.textContent = "Something went wrong.";
      })
      .finally(function () {
        setBusy(false, "");
      });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var ticker = (input.value || "").trim().toUpperCase();
    if (!ticker) return;
    fetchPredictions("/api/predict/" + encodeURIComponent(ticker), true);
  });

  refreshBtn.addEventListener("click", function () {
    fetchPredictions("/api/predictions");
  });

  fetchPredictions("/api/predictions");
})();

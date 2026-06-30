/**
 * dashboard.js — Kouros interactive dashboard
 *
 * Features:
 *   - Add/remove watchlist tickers (search modal)
 *   - Create/delete funds (fund modal with watchlist picker)
 *   - Edit/delete positions per ticker (position modal)
 *   - Profile menu toggle
 */
(function () {
  var DEBOUNCE_MS = 300;

  function $(id) { return document.getElementById(id); }

  /* ══════════════════════════════════════════════════════════
     ADD-TICKER MODAL
  ══════════════════════════════════════════════════════════ */
  (function initAddTicker() {
    var addBtn         = $("add-ticker-btn");
    var modal          = $("add-ticker-modal");
    var searchInput    = $("ticker-search-input");
    var resultsEl      = $("ticker-search-results");
    var messageEl      = $("add-ticker-message");
    var confirmBtn     = $("add-ticker-confirm");
    var cancelBtn      = $("add-ticker-cancel");
    var cancelCloseBtn = $("add-ticker-cancel-btn");
    var countEl        = $("add-ticker-selected-count");

    if (!addBtn || !modal) return;

    var selected = new Set();
    var searchTimer = null;
    var adding = false;

    function openModal() {
      modal.hidden = false;
      selected.clear();
      messageEl.textContent = "";
      searchInput.value = "";
      searchInput.disabled = false;
      confirmBtn.textContent = "Add to Watchlist";
      confirmBtn.disabled = true;
      adding = false;
      renderPlaceholder(resultsEl, "Start typing to search symbols");
      updateCount();
      setTimeout(function () { searchInput.focus(); }, 50);
    }

    function closeModal() {
      modal.hidden = true;
      selected.clear();
      if (searchTimer) { clearTimeout(searchTimer); searchTimer = null; }
    }

    function updateCount() {
      var n = selected.size;
      countEl.textContent = n + " selected";
      confirmBtn.disabled = n === 0 || adding;
    }

    function onSearchInput() {
      var q = searchInput.value.trim();
      messageEl.textContent = "";
      if (searchTimer) clearTimeout(searchTimer);
      if (!q) { renderPlaceholder(resultsEl, "Start typing to search symbols"); return; }

      searchTimer = setTimeout(function () {
        fetch("/api/tickers/search?q=" + encodeURIComponent(q))
          .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
          .then(function (res) {
            if (!res.ok || res.data.error) {
              renderPlaceholder(resultsEl, res.data.error || "Search failed — try again");
              return;
            }
            renderSearchResults(resultsEl, res.data.results || [], selected, updateCount);
          })
          .catch(function () { renderPlaceholder(resultsEl, "Search failed — try again"); });
      }, DEBOUNCE_MS);
    }

    function onConfirmAdd() {
      if (selected.size === 0 || adding) return;
      adding = true;
      confirmBtn.textContent = "Adding…";
      confirmBtn.disabled = true;
      searchInput.disabled = true;

      fetch("/api/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tickers: Array.from(selected) }),
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (res) {
          if (!res.ok) { messageEl.textContent = res.data.error || "Could not add tickers"; resetAdding(); return; }
          if (res.data.added && res.data.added.length > 0) { window.location.reload(); return; }
          var parts = [];
          if (res.data.skipped && res.data.skipped.length) {
            parts.push(res.data.skipped.map(function (s) { return s.symbol + ": " + s.reason; }).join("; "));
          }
          if (res.data.failed && res.data.failed.length) {
            parts.push(res.data.failed.map(function (f) { return f.symbol + ": " + f.reason; }).join("; "));
          }
          messageEl.textContent = parts.join(" · ") || "Nothing was added";
          resetAdding();
        })
        .catch(function () { messageEl.textContent = "Request failed — try again"; resetAdding(); });
    }

    function resetAdding() {
      adding = false;
      confirmBtn.textContent = "Add to Watchlist";
      searchInput.disabled = false;
      updateCount();
    }

    addBtn.addEventListener("click", openModal);
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);
    if (cancelCloseBtn) cancelCloseBtn.addEventListener("click", closeModal);
    modal.addEventListener("click", function (e) { if (e.target === modal) closeModal(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !modal.hidden) closeModal(); });
    searchInput.addEventListener("input", onSearchInput);
    searchInput.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
    confirmBtn.addEventListener("click", onConfirmAdd);

    /* Remove buttons on watchlist rows */
    document.querySelectorAll(".remove-ticker-btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var ticker = btn.getAttribute("data-ticker");
        if (!confirm("Remove " + ticker + " from watchlist?")) return;
        fetch("/api/watchlist", {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ticker: ticker }),
        })
          .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
          .then(function (res) {
            if (res.ok) window.location.reload();
            else alert(res.data.error || "Could not remove ticker");
          })
          .catch(function () { alert("Request failed — try again"); });
      });
    });
  })();


  /* ══════════════════════════════════════════════════════════
     ADD-FUND MODAL
  ══════════════════════════════════════════════════════════ */
  (function initAddFund() {
    var addBtn       = $("add-fund-btn");
    var modal        = $("add-fund-modal");
    var nameInput    = $("fund-name-input");
    var searchInput  = $("fund-ticker-search");
    var resultsEl    = $("fund-ticker-results");
    var messageEl    = $("add-fund-message");
    var confirmBtn   = $("add-fund-confirm");
    var cancelBtn    = $("add-fund-cancel");
    var cancelClose  = $("add-fund-cancel-btn");
    var countEl      = $("add-fund-selected-count");

    if (!addBtn || !modal) return;

    var selected = new Set();
    var searchTimer = null;

    function openModal() {
      modal.hidden = false;
      selected.clear();
      nameInput.value = "";
      searchInput.value = "";
      messageEl.textContent = "";
      renderPlaceholder(resultsEl, "Search a symbol to add it to this fund");
      updateCount();
      setTimeout(function () { nameInput.focus(); }, 50);
    }

    function closeModal() {
      modal.hidden = true;
      selected.clear();
      if (searchTimer) { clearTimeout(searchTimer); searchTimer = null; }
    }

    function updateCount() {
      var n = selected.size;
      countEl.textContent = n + " selected";
    }

    function onSearchInput() {
      var q = searchInput.value.trim();
      messageEl.textContent = "";
      if (searchTimer) clearTimeout(searchTimer);
      if (!q) { renderPlaceholder(resultsEl, "Search a symbol to add it to this fund"); return; }

      searchTimer = setTimeout(function () {
        // context=fund so nothing is pre-marked as "already added"
        fetch("/api/tickers/search?q=" + encodeURIComponent(q) + "&context=fund")
          .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
          .then(function (res) {
            if (!res.ok || res.data.error) {
              renderPlaceholder(resultsEl, res.data.error || "Search failed — try again");
              return;
            }
            renderSearchResults(resultsEl, res.data.results || [], selected, updateCount);
          })
          .catch(function () { renderPlaceholder(resultsEl, "Search failed — try again"); });
      }, DEBOUNCE_MS);
    }

    function onConfirmCreate() {
      var name = (nameInput.value || "").trim();
      if (!name) { messageEl.textContent = "Please enter a fund name"; nameInput.focus(); return; }
      confirmBtn.textContent = "Creating…";
      confirmBtn.disabled = true;
      messageEl.textContent = "";

      fetch("/api/funds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name, tickers: Array.from(selected) }),
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (res) {
          if (!res.ok) {
            messageEl.textContent = res.data.error || "Could not create fund";
            confirmBtn.textContent = "Create Fund";
            confirmBtn.disabled = false;
          } else {
            window.location.reload();
          }
        })
        .catch(function () {
          messageEl.textContent = "Request failed — try again";
          confirmBtn.textContent = "Create Fund";
          confirmBtn.disabled = false;
        });
    }

    addBtn.addEventListener("click", openModal);
    if (cancelBtn)  cancelBtn.addEventListener("click", closeModal);
    if (cancelClose) cancelClose.addEventListener("click", closeModal);
    modal.addEventListener("click", function (e) { if (e.target === modal) closeModal(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !modal.hidden) closeModal(); });
    searchInput.addEventListener("input", onSearchInput);
    searchInput.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
    confirmBtn.addEventListener("click", onConfirmCreate);
    nameInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); searchInput.focus(); }
    });

    /* Delete fund buttons */
    document.querySelectorAll(".remove-fund-btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var fundId = btn.getAttribute("data-fund-id");
        var fundRow = btn.closest("[data-fund-id]");
        var fundNameEl = fundRow ? fundRow.querySelector(".fund-name-text") : null;
        var fundName = fundNameEl ? fundNameEl.textContent : "this fund";
        if (!confirm("Delete fund \"" + fundName + "\"? This cannot be undone.")) return;
        fetch("/api/funds/" + fundId, { method: "DELETE" })
          .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
          .then(function (res) {
            if (res.ok) window.location.reload();
            else alert(res.data.error || "Could not delete fund");
          })
          .catch(function () { alert("Request failed — try again"); });
      });
    });
  })();


  /* ══════════════════════════════════════════════════════════
     POSITION EDIT MODAL
  ══════════════════════════════════════════════════════════ */
  (function initPositionModal() {
    var modal       = $("position-modal");
    var titleEl     = $("position-modal-title");
    var tickerInput = $("position-ticker");
    var fundIdInput = $("position-fund-id");
    var sharesInput = $("position-shares");
    var costInput   = $("position-avgcost");
    var messageEl   = $("position-modal-message");
    var saveBtn     = $("position-save-btn");
    var deleteBtn   = $("position-delete-btn");
    var cancelBtn   = $("position-cancel-btn");
    var closeBtn    = $("position-modal-close");
    var FUND_EXPAND_KEY = "kouros-expanded-funds";

    if (!modal) return;

    function rememberExpandedFunds() {
      var ids = [];
      document.querySelectorAll(".fund-holdings-block:not([hidden])").forEach(function (block) {
        var id = block.id.replace("fund-holdings-", "");
        if (id) ids.push(id);
      });
      if (ids.length) {
        sessionStorage.setItem(FUND_EXPAND_KEY, JSON.stringify(ids));
      }
    }

    function openModal(ticker, existingShares, existingCost, fundId) {
      modal.hidden = false;
      fundIdInput.value = fundId || "";
      titleEl.textContent = fundId ? ("Fund position — " + ticker) : ("Position — " + ticker);
      tickerInput.value = ticker;
      sharesInput.value = existingShares || "";
      costInput.value   = existingCost || "";
      messageEl.textContent = "";
      deleteBtn.style.visibility = existingShares ? "visible" : "hidden";
      saveBtn.textContent = "Save";
      saveBtn.disabled = false;
      setTimeout(function () { sharesInput.focus(); }, 50);
    }

    function closeModal() { modal.hidden = true; }

    function onSave() {
      var ticker  = tickerInput.value;
      var fundId  = fundIdInput.value;
      var shares  = parseFloat(sharesInput.value);
      var avgCost = parseFloat(costInput.value);

      if (!ticker || isNaN(shares) || isNaN(avgCost)) {
        messageEl.textContent = "Please fill in shares and average cost";
        return;
      }
      if (shares <= 0 || avgCost <= 0) {
        messageEl.textContent = "Shares and average cost must be positive";
        return;
      }

      saveBtn.textContent = "Saving…";
      saveBtn.disabled = true;
      messageEl.textContent = "";

      var url = fundId
        ? ("/api/funds/" + fundId + "/holdings/" + encodeURIComponent(ticker) + "/position")
        : "/api/positions";
      var body = fundId
        ? { shares: shares, avg_cost: avgCost }
        : { symbol: ticker, shares: shares, avg_cost: avgCost };

      fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (res) {
          if (!res.ok) {
            messageEl.textContent = res.data.error || "Could not save position";
            saveBtn.textContent = "Save";
            saveBtn.disabled = false;
          } else {
            if (fundId) rememberExpandedFunds();
            window.location.reload();
          }
        })
        .catch(function () {
          messageEl.textContent = "Request failed — try again";
          saveBtn.textContent = "Save";
          saveBtn.disabled = false;
        });
    }

    function onDelete() {
      var ticker = tickerInput.value;
      var fundId = fundIdInput.value;
      if (!ticker || !confirm("Remove position for " + ticker + "?")) return;

      var url = fundId
        ? ("/api/funds/" + fundId + "/holdings/" + encodeURIComponent(ticker) + "/position")
        : ("/api/positions/" + encodeURIComponent(ticker));

      fetch(url, { method: "DELETE" })
        .then(function (r) {
          if (r.ok) {
            if (fundId) rememberExpandedFunds();
            window.location.reload();
          } else alert("Could not remove position");
        })
        .catch(function () { alert("Request failed — try again"); });
    }

    function readPositionFromRow(row) {
      var sharesCell = row.querySelector(".pos-shares");
      var costCell   = row.querySelector(".pos-avgcost");
      var existingShares = null;
      var existingCost   = null;
      if (sharesCell) {
        var sharesText = sharesCell.textContent.replace(/[^0-9.]/g, "");
        existingShares = sharesText || null;
      }
      if (costCell) {
        var costText = costCell.textContent.replace(/[^0-9.]/g, "");
        existingCost = costText || null;
      }
      return { existingShares: existingShares, existingCost: existingCost };
    }

    saveBtn.addEventListener("click", onSave);
    deleteBtn.addEventListener("click", onDelete);
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);
    if (closeBtn)  closeBtn.addEventListener("click", closeModal);
    modal.addEventListener("click", function (e) { if (e.target === modal) closeModal(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !modal.hidden) closeModal(); });

    document.querySelectorAll(".pos-cell").forEach(function (cell) {
      cell.addEventListener("click", function (e) {
        e.stopPropagation();
        var ticker = cell.getAttribute("data-ticker");
        var fundId = cell.getAttribute("data-fund-id") || null;
        var row    = cell.closest(".table-row");
        if (!row || !ticker) return;
        var pos = readPositionFromRow(row);
        openModal(ticker, pos.existingShares, pos.existingCost, fundId);
      });
    });
  })();


  /* ══════════════════════════════════════════════════════════
     BENCHMARK COLUMN (watchlist + funds — shared selection)
  ══════════════════════════════════════════════════════════ */
  (function initBenchmarkColumn() {
    var BENCHMARK_KEY = "kouros-benchmark";

    function getSelects() {
      return document.querySelectorAll(".benchmark-select");
    }

    function formatVs(val) {
      if (val === "" || val === null || val === undefined) return "—";
      var n = parseFloat(val);
      if (isNaN(n)) return "—";
      return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
    }

    function applyCells(key) {
      document.querySelectorAll(".vs-index-cell").forEach(function (cell) {
        var raw = cell.getAttribute("data-vs-" + key);
        var text = formatVs(raw);
        cell.textContent = text;
        cell.classList.remove("cell-up", "cell-down", "na");
        if (raw === "" || raw === null) {
          cell.classList.add("na");
        } else if (parseFloat(raw) >= 0) {
          cell.classList.add("cell-up");
        } else {
          cell.classList.add("cell-down");
        }
      });
    }

    function setBenchmark(key) {
      getSelects().forEach(function (sel) {
        if (sel.value !== key) sel.value = key;
      });
      applyCells(key);
      localStorage.setItem(BENCHMARK_KEY, key);
    }

    var saved = localStorage.getItem(BENCHMARK_KEY) || localStorage.getItem("kouros-fund-benchmark") || "spy";
    if (saved === "russell") saved = "spy";
    setBenchmark(saved);

    document.addEventListener("change", function (e) {
      if (!e.target || !e.target.classList.contains("benchmark-select")) return;
      setBenchmark(e.target.value);
    });

    window.applyDashboardBenchmark = setBenchmark;
  })();


  /* ══════════════════════════════════════════════════════════
     FUND EXPAND
  ══════════════════════════════════════════════════════════ */
  (function initFundUI() {
    var FUND_EXPAND_KEY = "kouros-expanded-funds";

    function expandFund(fundId) {
      var block = $("fund-holdings-" + fundId);
      var row = document.querySelector('.fund-summary-row[data-fund-id="' + fundId + '"]');
      var btn = row && row.querySelector(".fund-expand-btn");
      if (!block) return;
      block.hidden = false;
      if (btn) {
        btn.setAttribute("aria-expanded", "true");
        btn.textContent = "▾";
      }
    }

    try {
      var saved = sessionStorage.getItem(FUND_EXPAND_KEY);
      if (saved) {
        JSON.parse(saved).forEach(expandFund);
        sessionStorage.removeItem(FUND_EXPAND_KEY);
      }
    } catch (e) { /* ignore */ }

    document.querySelectorAll(".fund-expand-btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var row = btn.closest(".fund-summary-row");
        if (!row) return;
        var fundId = row.getAttribute("data-fund-id");
        var block = $("fund-holdings-" + fundId);
        if (!block) return;
        var open = block.hidden;
        block.hidden = !open;
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        btn.textContent = open ? "▾" : "▸";
      });
    });
  })();


  /* ══════════════════════════════════════════════════════════
     SHARED HELPERS
  ══════════════════════════════════════════════════════════ */

  function renderPlaceholder(container, text) {
    container.innerHTML = "";
    var p = document.createElement("p");
    p.className = "ticker-search-empty";
    p.textContent = text;
    container.appendChild(p);
  }

  function renderSearchResults(container, results, selectedSet, onToggle) {
    container.innerHTML = "";
    if (!results.length) { renderPlaceholder(container, "No symbols match your search"); return; }

    results.forEach(function (row) {
      var disabled = row.in_watchlist;
      var isSelected = selectedSet.has(row.symbol);

      var el = document.createElement("div");
      el.className = "ticker-result-row"
        + (disabled   ? " is-disabled" : "")
        + (isSelected ? " is-selected" : "");
      el.setAttribute("data-symbol", row.symbol);
      el.setAttribute("role", "button");
      el.setAttribute("tabindex", disabled ? "-1" : "0");

      var check = document.createElement("span");
      check.className = "ticker-result-check";
      check.textContent = isSelected ? "✓" : "";

      var sym = document.createElement("span");
      sym.className = "ticker-result-symbol";
      sym.textContent = row.symbol;

      var sep = document.createElement("span");
      sep.className = "ticker-result-sep";
      sep.textContent = "·";

      var name = document.createElement("span");
      name.className = "ticker-result-name";
      name.textContent = row.name || row.symbol;

      el.appendChild(check); el.appendChild(sym); el.appendChild(sep); el.appendChild(name);

      if (disabled) {
        var tag = document.createElement("span");
        tag.className = "ticker-result-tag";
        tag.textContent = "added";
        el.appendChild(tag);
      }

      function toggle() {
        if (disabled) return;
        if (selectedSet.has(row.symbol)) {
          selectedSet.delete(row.symbol);
          el.classList.remove("is-selected");
          check.textContent = "";
        } else {
          selectedSet.add(row.symbol);
          el.classList.add("is-selected");
          check.textContent = "✓";
        }
        onToggle();
      }

      el.addEventListener("click", toggle);
      el.addEventListener("keydown", function (e) {
        if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggle(); }
      });
      container.appendChild(el);
    });
  }


  /* ══════════════════════════════════════════════════════════
     PROFILE MENU
  ══════════════════════════════════════════════════════════ */
  (function initProfileMenu() {
    var profileBtn  = $("profile-menu-btn");
    var profileMenu = $("profile-menu");
    if (!profileBtn || !profileMenu) return;

    profileBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = profileMenu.hidden;
      profileMenu.hidden = !open;
      profileBtn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function () {
      profileMenu.hidden = true;
      profileBtn.setAttribute("aria-expanded", "false");
    });
  })();

})();

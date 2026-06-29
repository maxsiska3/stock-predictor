/**
 * dashboard.js — dynamic watchlist UI
 *
 * Add:    + Add Ticker → modal → type to filter → click rows to select → Add to Watchlist
 * Remove: × button on row hover → confirm → DELETE
 *
 * Clicking the whole row toggles selection — typed text is never sent to the API.
 */
(function () {
  var DEBOUNCE_MS = 300;

  /* ── DOM refs (assigned in init) ── */
  var addBtn, modal, searchInput, resultsEl, messageEl, confirmBtn, cancelBtn, cancelCloseBtn, countEl;

  /* selected: Set of symbol strings chosen by clicking rows */
  var selected = new Set();
  var searchTimer = null;
  var adding = false;

  function $(id) {
    return document.getElementById(id);
  }

  /* ── Modal open / close ───────────────────────────────────── */

  function openModal() {
    modal.hidden = false;
    selected.clear();
    messageEl.textContent = "";
    searchInput.value = "";
    searchInput.disabled = false;
    confirmBtn.textContent = "Add to Watchlist";
    confirmBtn.disabled = true;
    adding = false;
    renderPlaceholder("Start typing to search symbols");
    updateSelectedCount();
    setTimeout(function () { searchInput.focus(); }, 50);
  }

  function closeModal() {
    modal.hidden = true;
    selected.clear();
    if (searchTimer) { clearTimeout(searchTimer); searchTimer = null; }
  }

  /* ── Selection state ─────────────────────────────────────── */

  function updateSelectedCount() {
    var n = selected.size;
    countEl.textContent = n === 0 ? "0 selected" : n + (n === 1 ? " selected" : " selected");
    confirmBtn.disabled = n === 0 || adding;
  }

  /* ── Render helpers ──────────────────────────────────────── */

  function renderPlaceholder(text) {
    resultsEl.innerHTML = "";
    var p = document.createElement("p");
    p.className = "ticker-search-empty";
    p.textContent = text;
    resultsEl.appendChild(p);
  }

  function renderResults(results) {
    resultsEl.innerHTML = "";

    if (!results.length) {
      renderPlaceholder("No symbols match your search");
      return;
    }

    results.forEach(function (row) {
      var disabled = row.in_watchlist;
      var isSelected = selected.has(row.symbol);

      /* Wrapper div — clicking anywhere on it toggles selection */
      var el = document.createElement("div");
      el.className = "ticker-result-row"
        + (disabled ? " is-disabled" : "")
        + (isSelected ? " is-selected" : "");
      el.setAttribute("data-symbol", row.symbol);
      el.setAttribute("role", "button");
      el.setAttribute("tabindex", disabled ? "-1" : "0");

      /* Visual checkmark box (hidden native checkbox is in renderResults for a11y) */
      var check = document.createElement("span");
      check.className = "ticker-result-check";
      check.setAttribute("aria-hidden", "true");
      check.textContent = isSelected ? "✓" : "";

      /* Symbol — e.g. "AAPL" */
      var sym = document.createElement("span");
      sym.className = "ticker-result-symbol";
      sym.textContent = row.symbol;

      /* Separator dot */
      var sep = document.createElement("span");
      sep.className = "ticker-result-sep";
      sep.textContent = "·";

      /* Company name — e.g. "Apple Inc." */
      var name = document.createElement("span");
      name.className = "ticker-result-name";
      name.textContent = row.name || row.symbol;

      el.appendChild(check);
      el.appendChild(sym);
      el.appendChild(sep);
      el.appendChild(name);

      /* "Already added" badge */
      if (disabled) {
        var tag = document.createElement("span");
        tag.className = "ticker-result-tag";
        tag.textContent = "added";
        el.appendChild(tag);
      }

      /* Click or Enter = toggle selection (disabled rows do nothing) */
      function toggleRow() {
        if (disabled) return;
        if (selected.has(row.symbol)) {
          selected.delete(row.symbol);
          el.classList.remove("is-selected");
          check.textContent = "";
        } else {
          selected.add(row.symbol);
          el.classList.add("is-selected");
          check.textContent = "✓";
        }
        updateSelectedCount();
      }

      el.addEventListener("click", toggleRow);
      el.addEventListener("keydown", function (e) {
        if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggleRow(); }
      });

      resultsEl.appendChild(el);
    });
  }

  /* ── Search ──────────────────────────────────────────────── */

  function onSearchInput() {
    var q = searchInput.value.trim();
    messageEl.textContent = "";

    if (searchTimer) { clearTimeout(searchTimer); }

    if (!q) {
      renderPlaceholder("Start typing to search symbols");
      return;
    }

    /* Small spinner hint while waiting */
    searchTimer = setTimeout(function () {
      fetch("/api/tickers/search?q=" + encodeURIComponent(q))
        .then(function (res) { return res.json(); })
        .then(function (data) { renderResults(data.results || []); })
        .catch(function () { renderPlaceholder("Search failed — try again"); });
    }, DEBOUNCE_MS);
  }

  /* ── Add ─────────────────────────────────────────────────── */

  function formatSummary(data) {
    var parts = [];
    if (data.added && data.added.length)   parts.push(data.added.length + " added");
    if (data.skipped && data.skipped.length) parts.push(data.skipped.length + " already on list");
    if (data.failed && data.failed.length) parts.push(data.failed.length + " failed");
    return parts.join(", ");
  }

  function onConfirmAdd() {
    if (selected.size === 0 || adding) return;

    adding = true;
    confirmBtn.textContent = "Adding…";
    confirmBtn.disabled = true;
    searchInput.disabled = true;
    messageEl.textContent = "";

    fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers: Array.from(selected) }),
    })
      .then(function (res) {
        return res.json().then(function (data) { return { ok: res.ok, data: data }; });
      })
      .then(function (result) {
        if (!result.ok) {
          messageEl.textContent = result.data.error || "Could not add tickers";
          resetAddingState();
          return;
        }
        if (result.data.added && result.data.added.length > 0) {
          /* At least one ticker added — reload to show the new row */
          window.location.reload();
          return;
        }
        /* All skipped / failed — show summary without reloading */
        messageEl.textContent = formatSummary(result.data) || "Nothing was added";
        resetAddingState();
      })
      .catch(function () {
        messageEl.textContent = "Request failed — try again";
        resetAddingState();
      });
  }

  function resetAddingState() {
    adding = false;
    confirmBtn.textContent = "Add to Watchlist";
    searchInput.disabled = false;
    updateSelectedCount();
  }

  /* ── Remove ──────────────────────────────────────────────── */

  function onRemoveTicker(ticker) {
    if (!confirm("Remove " + ticker + " from watchlist?")) return;

    fetch("/api/watchlist", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker: ticker }),
    })
      .then(function (res) {
        return res.json().then(function (data) { return { ok: res.ok, data: data }; });
      })
      .then(function (result) {
        if (result.ok) {
          window.location.reload();
        } else {
          alert(result.data.error || "Could not remove ticker");
        }
      })
      .catch(function () { alert("Request failed — try again"); });
  }

  /* ── Init ────────────────────────────────────────────────── */

  function init() {
    addBtn        = $("add-ticker-btn");
    modal         = $("add-ticker-modal");
    searchInput   = $("ticker-search-input");
    resultsEl     = $("ticker-search-results");
    messageEl     = $("add-ticker-message");
    confirmBtn    = $("add-ticker-confirm");
    cancelBtn     = $("add-ticker-cancel");      /* ✕ in header */
    cancelCloseBtn = $("add-ticker-cancel-btn"); /* Cancel in footer */
    countEl       = $("add-ticker-selected-count");

    if (!addBtn || !modal) return;

    /* Open */
    addBtn.addEventListener("click", openModal);

    /* Close — header ✕ button */
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);
    /* Close — footer Cancel button */
    if (cancelCloseBtn) cancelCloseBtn.addEventListener("click", closeModal);

    /* Click on dimmed backdrop (not the panel) closes modal */
    modal.addEventListener("click", function (e) {
      if (e.target === modal) closeModal();
    });

    /* Escape key */
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !modal.hidden) closeModal();
    });

    /* Search input — debounced, Enter does NOT add */
    searchInput.addEventListener("input", onSearchInput);
    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") e.preventDefault(); /* block accidental submit */
    });

    /* Confirm add */
    confirmBtn.addEventListener("click", onConfirmAdd);

    /* Remove buttons on each watchlist row */
    document.querySelectorAll(".remove-ticker-btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        onRemoveTicker(btn.getAttribute("data-ticker"));
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

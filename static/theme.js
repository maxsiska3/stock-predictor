(function () {
  var STORAGE_KEY = "kouros-theme";
  var THEMES = ["light", "dark", "kouros"];
  var DEFAULT_THEME = "kouros";

  var BG = { light: "#f4f3ef", dark: "#0f1115", kouros: "#0a0f1e" };

  function normalize(theme) {
    return THEMES.indexOf(theme) !== -1 ? theme : DEFAULT_THEME;
  }

  function getStoredTheme() {
    return normalize(localStorage.getItem(STORAGE_KEY));
  }

  function applyTheme(theme) {
    var root = document.getElementById("app-root");
    if (!root) return;

    theme = normalize(theme);
    root.setAttribute("data-theme", theme);
    localStorage.setItem(STORAGE_KEY, theme);
    document.body.style.background = BG[theme];

    document.querySelectorAll(".theme-option").forEach(function (btn) {
      var active = btn.getAttribute("data-theme") === theme;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-checked", active ? "true" : "false");
    });
  }

  function closeMenu() {
    var menu = document.getElementById("theme-menu");
    var btn = document.getElementById("theme-menu-btn");
    if (menu) menu.classList.remove("is-open");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  function openMenu() {
    var menu = document.getElementById("theme-menu");
    var btn = document.getElementById("theme-menu-btn");
    if (menu) menu.classList.add("is-open");
    if (btn) btn.setAttribute("aria-expanded", "true");
  }

  function toggleMenu() {
    var menu = document.getElementById("theme-menu");
    if (menu && menu.classList.contains("is-open")) closeMenu();
    else openMenu();
  }

  function init() {
    var btn = document.getElementById("theme-menu-btn");
    var menu = document.getElementById("theme-menu");
    if (!btn || !menu) return;

    applyTheme(getStoredTheme());

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      toggleMenu();
    });

    menu.querySelectorAll(".theme-option").forEach(function (option) {
      option.addEventListener("click", function (e) {
        e.stopPropagation();
        applyTheme(option.getAttribute("data-theme"));
        closeMenu();
      });
    });

    document.addEventListener("click", function () {
      closeMenu();
    });

    menu.addEventListener("click", function (e) {
      e.stopPropagation();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

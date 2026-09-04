import { STATIC_DEMO, demoRequest } from "./demo-data.js";

const API = "/api";
const PRODUCT_VERSION = "v0.6-Beta";
const TERMINAL_ROUTES = Object.freeze(["home", "market", "research", "news", "portfolio", "academy"]);
const LANDING_SCENES = Object.freeze(["hero", "signal", "validation", "committee", "portfolio", "gateway"]);
const DEMO_POSITIONS = Object.freeze([
  { ticker: "AAPL", quantity: 12 },
  { ticker: "MSFT", quantity: 8 },
  { ticker: "SPY", quantity: 10 },
  { ticker: "NVDA", quantity: 6 },
]);

const state = {
  ticker: "AAPL",
  hasSelection: false,
  assetClass: "equity",
  researchProfile: null,
  period: "6mo",
  route: "home",
  analysisTab: "chart",
  researchTab: "models",
  chartType: "line",
  chartScale: "linear",
  overview: null,
  snapshot: null,
  assetNews: null,
  marketNews: null,
  events: null,
  options: new Map(),
  positions: loadPositions(),
  portfolioIsDemo: localStorage.getItem("hermes-positions-v2") === null,
  aboutExpanded: false,
  backtestRunId: 0,
  analysisRunId: 0,
  portfolioAnalyzed: false,
};

let tapeMotionFrame = 0;
let tapeLastFrame = 0;
let tapePaused = false;
let tapeScrollPosition = 0;
let terminalInitialization = null;
let landingScrollFrame = 0;
let landingTransitionTimer = 0;
let activeLandingScene = "hero";

const byId = (id) => document.getElementById(id);
const finite = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));
const number = (value, digits = 2) =>
  finite(value) ? Number(value).toLocaleString("en-US", { maximumFractionDigits: digits }) : "—";
const fixedNumber = (value, digits = 2) =>
  finite(value) ? Number(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits }) : "—";
const signedNumber = (value, digits = 2) =>
  finite(value) ? `${Number(value) > 0 ? "+" : ""}${fixedNumber(value, digits)}` : "—";
const compact = (value) =>
  finite(value) ? new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(Number(value)) : "—";
const money = (value, currency = "USD") => {
  if (!finite(value)) return "—";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: Math.abs(Number(value)) < 10 ? 3 : 2,
    }).format(Number(value));
  } catch {
    return `${number(value)} ${currency}`;
  }
};
const percent = (value, digits = 2, signed = true) =>
  finite(value) ? `${signed && Number(value) > 0 ? "+" : ""}${number(value, digits)}%` : "—";
const ratioPercent = (value, digits = 1) => (finite(value) ? `${number(Number(value) * 100, digits)}%` : "—");
const dateLabel = (value, includeTime = false) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "—";
  return date.toLocaleString(undefined, includeTime
    ? { dateStyle: "medium", timeStyle: "short" }
    : { year: "numeric", month: "short", day: "numeric" });
};
const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
const directionClass = (value) => Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : "neutral";

async function request(path, options = {}) {
  if (STATIC_DEMO) return demoRequest(path, options);
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail ?? payload;
    const message = typeof detail === "string" ? detail : detail.message;
    throw new Error(message || `Request failed with status ${response.status}`);
  }
  return payload;
}

function setHeaderState(kind, text) {
  const node = byId("header-state");
  node.className = kind === "ok" ? "state-ok" : kind === "error" ? "state-error" : "state-warn";
  node.textContent = STATIC_DEMO && kind === "ok" ? "Frozen demo" : text;
}

function setMarketState(kind, text) {
  const node = byId("market-state");
  node.className = `inline-state is-${kind}`;
  node.textContent = text;
}

function showTerminalShell() {
  byId("landing-shell").hidden = true;
  document.querySelector(".app-shell").hidden = false;
  byId("landing-skip").hidden = true;
  byId("terminal-skip").hidden = false;
  document.body.classList.add("terminal-mode");
}

function showLanding() {
  clearTimeout(landingTransitionTimer);
  const landing = byId("landing-shell");
  landing.classList.remove("is-departing");
  landing.hidden = false;
  document.querySelector(".app-shell").hidden = true;
  byId("landing-skip").hidden = false;
  byId("terminal-skip").hidden = true;
  document.body.classList.remove("terminal-mode");
  requestAnimationFrame(updateLandingFromScroll);
}

function returnToLanding(event) {
  event.preventDefault();
  const landing = byId("landing-shell");
  landing.scrollTop = 0;
  commitLandingScene("hero");
  history.pushState(null, "", `${location.pathname}${location.search}`);
  showLanding();
}

function enterTerminal() {
  clearTimeout(landingTransitionTimer);
  const landing = byId("landing-shell");
  const commit = () => {
    history.pushState(null, "", "#home");
    setRoute("home", false);
  };
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    commit();
    return;
  }
  landing.classList.add("is-departing");
  landingTransitionTimer = window.setTimeout(commit, 500);
}

function commitLandingScene(scene) {
  activeLandingScene = scene;
  const landing = byId("landing-shell");
  landing.dataset.activeScene = scene;
  document.querySelectorAll("[data-landing-scene]").forEach((node) => node.classList.toggle("is-active", node.dataset.landingScene === scene));
  document.querySelectorAll("[data-landing-target]").forEach((node) => node.classList.toggle("is-current", node.dataset.landingTarget === scene));
  document.querySelectorAll(".landing-progress [data-landing-jump]").forEach((button) => {
    const current = button.dataset.landingJump === scene;
    button.classList.toggle("is-active", current);
    if (current) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  });
}

function setLandingScene(scene) {
  if (!LANDING_SCENES.includes(scene) || scene === activeLandingScene) return;
  const target = document.querySelector(`[data-landing-scene="${scene}"]`);
  const image = target?.querySelector("img");
  if (!target || !image || target.classList.contains("is-unavailable")) return;
  const commit = () => commitLandingScene(scene);
  if (image.complete && image.naturalWidth > 0) commit();
  else image.addEventListener("load", commit, { once: true });
}

function updateLandingFromScroll() {
  landingScrollFrame = 0;
  const landing = byId("landing-shell");
  if (landing.hidden) return;
  const shellRect = landing.getBoundingClientRect();
  const focusLine = shellRect.top + landing.clientHeight * 0.52;
  let closestScene = "hero";
  let closestDistance = Number.POSITIVE_INFINITY;
  document.querySelectorAll("[data-landing-target]").forEach((chapter) => {
    const rect = chapter.getBoundingClientRect();
    const distance = Math.abs((rect.top + rect.bottom) / 2 - focusLine);
    if (distance < closestDistance) {
      closestDistance = distance;
      closestScene = chapter.dataset.landingTarget;
    }
  });
  setLandingScene(closestScene);
  const maximum = Math.max(1, landing.scrollHeight - landing.clientHeight);
  landing.style.setProperty("--landing-progress", String(Math.min(1, Math.max(0, landing.scrollTop / maximum))));
}

function initializeLanding() {
  const landing = byId("landing-shell");
  landing.dataset.activeScene = "hero";
  landing.addEventListener("scroll", () => {
    if (!landingScrollFrame) landingScrollFrame = requestAnimationFrame(updateLandingFromScroll);
  }, { passive: true });
  document.querySelectorAll("[data-enter-terminal]").forEach((button) => button.addEventListener("click", enterTerminal));
  document.querySelectorAll("[data-landing-jump]").forEach((button) => button.addEventListener("click", () => {
    const chapter = document.querySelector(`[data-landing-target="${button.dataset.landingJump}"]`);
    chapter?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  }));
  document.querySelectorAll("[data-landing-scene] img").forEach((image) => image.addEventListener("error", () => {
    const scene = image.closest("[data-landing-scene]");
    scene?.classList.add("is-unavailable");
    if (scene?.dataset.landingScene === activeLandingScene) {
      const fallback = LANDING_SCENES.find((name) => !document.querySelector(`[data-landing-scene="${name}"]`)?.classList.contains("is-unavailable"));
      if (fallback) commitLandingScene(fallback);
    }
  }));
  commitLandingScene("hero");
}

function syncExperienceFromLocation() {
  const requested = location.hash.slice(1);
  if (TERMINAL_ROUTES.includes(requested)) setRoute(requested, false);
  else showLanding();
}

function configureStaticDemo() {
  if (!STATIC_DEMO) return;
  document.body.classList.add("static-demo");
  byId("static-demo-strip").hidden = false;
  byId("backtest-engine").value = "sma";
  document.querySelectorAll(".model-only").forEach((node) => { node.hidden = true; });
  document.querySelectorAll(".sma-only").forEach((node) => { node.hidden = false; });
  document.querySelectorAll("#backtest-form input, #backtest-form select").forEach((control) => { control.disabled = true; });
  byId("run-backtest").textContent = "Load frozen SMA result";
  byId("run-analysis").disabled = true;
  byId("run-analysis").textContent = "Local model required";
  byId("load-options").disabled = true;
  byId("load-options").textContent = "Live backend required";
  document.querySelectorAll("#position-form input, #position-form button").forEach((control) => { control.disabled = true; });
  byId("reset-demo-portfolio").disabled = true;
}

function setRoute(route, updateHash = true) {
  const next = TERMINAL_ROUTES.includes(route) ? route : "home";
  showTerminalShell();
  ensureTerminalInitialized();
  if (["market", "research", "news"].includes(next) && !state.hasSelection) {
    state.hasSelection = true;
    state.ticker = state.researchProfile?.default_ticker || (state.assetClass === "crypto" ? "BTC-USD" : "AAPL");
    byId("ticker-input").value = state.ticker;
    loadMarket();
  }
  state.route = next;
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("is-active", view.id === `${next}-view`));
  document.querySelectorAll(".nav-button").forEach((button) => button.classList.toggle("is-active", button.dataset.route === next));
  if (updateHash && location.hash !== `#${next}`) history.replaceState(null, "", `#${next}`);
  if (next === "portfolio") {
    renderPositions();
    if (!state.portfolioAnalyzed) {
      state.portfolioAnalyzed = true;
      requestAnimationFrame(() => analyzePortfolio());
    }
  }
  if (next === "news") loadNewsHub();
  if (next === "research") updateResearchContext();
  byId("workspace").focus({ preventScroll: true });
}

function setResearchTab(tab) {
  state.researchTab = tab;
  document.querySelectorAll("[data-research-tab]").forEach((button) => {
    const selected = button.dataset.researchTab === tab;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-selected", String(selected));
  });
  document.querySelectorAll(".research-panel").forEach((panel) => panel.classList.toggle("is-active", panel.id === `${tab}-research-panel`));
}

function setAnalysisTab(tab) {
  state.analysisTab = tab;
  document.querySelectorAll(".subtab").forEach((button) => {
    const selected = button.dataset.analysisTab === tab;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-selected", String(selected));
  });
  document.querySelectorAll(".analysis-panel").forEach((panel) => panel.classList.toggle("is-active", panel.id === `${tab}-panel`));
}

async function setTicker(ticker) {
  const normalized = String(ticker || "").trim().toUpperCase();
  if (!normalized) return;
  const inferredClass = normalized.endsWith("-USD") ? "crypto" : "equity";
  if (inferredClass !== state.assetClass) {
    state.assetClass = inferredClass;
    updateAssetClassControls();
    state.overview = null;
    await loadResearchProfile();
    loadOverview(true);
  }
  state.ticker = normalized;
  state.hasSelection = true;
  resetResearchOutputs();
  state.aboutExpanded = false;
  byId("ticker-input").value = normalized;
  setRoute("market");
  loadMarket();
}

function updateAssetClassControls() {
  document.querySelectorAll("[data-asset-class]").forEach((button) => button.classList.toggle("is-active", button.dataset.assetClass === state.assetClass));
  byId("ticker-input").placeholder = state.assetClass === "crypto" ? "Search crypto pair (BTC-USD)" : "Search equity or ETF (AAPL, SPY)";
}

async function loadResearchProfile() {
  try {
    state.researchProfile = await request(`/v1/research-profile/${state.assetClass}`);
    updateResearchContext();
  } catch {
    state.researchProfile = null;
    updateResearchContext();
  }
}

function updateResearchContext() {
  byId("research-ticker").textContent = state.ticker;
  const label = state.researchProfile?.label || (state.assetClass === "crypto" ? "Crypto" : "Equities");
  const factor = state.researchProfile?.annualization_factor || (state.assetClass === "crypto" ? 365 : 252);
  const calendar = state.researchProfile?.calendar || "Research calendar unavailable";
  byId("research-class").textContent = label;
  byId("research-calendar").textContent = `${calendar} · ${factor}-day annualization`;
  byId("regime-filter-label").textContent = `Block long exposure below ${state.researchProfile?.regime_reference || "reference 200-day trend"}`;
}

function resetResearchOutputs() {
  state.backtestRunId += 1;
  state.analysisRunId += 1;
  byId("backtest-result").innerHTML = '<div class="empty-state"><strong>No simulation run</strong><p>Start with validation-selected mode. Results include probability quality, costs, exposure, turnover, drawdown, and fold evidence.</p></div>';
  byId("analysis-output").innerHTML = '<div class="empty-state compact-empty"><strong>Committee has not run</strong><p>Run it after reviewing the model and market evidence. An unavailable local model will remain an explicit unavailable state.</p></div>';
  byId("run-backtest").disabled = false;
  byId("run-backtest").textContent = "Run purged walk-forward test";
  byId("run-analysis").disabled = false;
  byId("run-analysis").textContent = "Run committee";
}

function applyResearchPreset() {
  const defaults = state.researchProfile?.backtest_defaults;
  if (!defaults) return;
  byId("train-window").value = defaults.train_window;
  byId("test-window").value = defaults.test_window;
  byId("target-horizon").value = defaults.target_horizon;
  byId("long-threshold").value = defaults.long_threshold;
  byId("short-threshold").value = defaults.short_threshold;
  byId("cost-bps").value = defaults.transaction_cost_bps;
  byId("slippage-bps").value = defaults.slippage_bps;
  updateResearchContext();
}

async function switchAssetClass(assetClass) {
  if (assetClass === state.assetClass) return;
  state.assetClass = assetClass;
  updateAssetClassControls();
  await loadResearchProfile();
  state.overview = null;
  state.assetNews = null;
  state.marketNews = null;
  state.events = null;
  resetResearchOutputs();
  applyResearchPreset();
  if (!state.hasSelection || state.route === "home") {
    state.hasSelection = false;
    state.ticker = state.researchProfile?.default_ticker || (assetClass === "crypto" ? "BTC-USD" : "AAPL");
    byId("ticker-input").value = "";
    byId("header-price").textContent = "—";
    byId("header-change").textContent = "—";
    setHeaderState("warn", "Choose asset");
    await Promise.allSettled([loadOverview(true), loadHomeNews(true), loadEvents(true)]);
  } else {
    state.ticker = state.researchProfile?.default_ticker || (assetClass === "crypto" ? "BTC-USD" : "AAPL");
    await Promise.allSettled([loadOverview(true), loadMarket()]);
  }
}

function svgSparkline(values, change) {
  const clean = (values || []).map(Number).filter(Number.isFinite);
  if (clean.length < 2) return '<svg class="sparkline" aria-hidden="true"></svg>';
  let min = Math.min(...clean);
  let max = Math.max(...clean);
  if (min === max) { min -= 1; max += 1; }
  const points = clean.map((value, index) => {
    const x = 1 + (index / (clean.length - 1)) * 70;
    const y = 33 - ((value - min) / (max - min)) * 28;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const color = Number(change) >= 0 ? "#4ade80" : "#f87171";
  return `<svg class="sparkline" viewBox="0 0 72 38" preserveAspectRatio="none" aria-hidden="true"><polygon class="sparkline-area" points="1,36 ${points} 71,36" fill="${color}" fill-opacity="0.14" /><polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5" vector-effect="non-scaling-stroke" /></svg>`;
}

async function loadOverview(force = false) {
  if (state.overview && !force) {
    renderOverview(state.overview);
    return;
  }
  try {
    state.overview = await request(`/v1/market-overview?asset_class=${state.assetClass}`);
    renderOverview(state.overview);
  } catch (error) {
    state.overview = null;
    startTapeMotion(false);
    byId("market-tape-track").innerHTML = `<div class="tape-loading">Market overview unavailable · ${escapeHtml(error.message)}</div>`;
    byId("macro-list").innerHTML = '<p class="muted">Provider overview unavailable.</p>';
    byId("home-macro-list").innerHTML = '<p class="muted">Provider overview unavailable.</p>';
    ["trending", "gainers", "losers"].forEach((label) => {
      byId(`movers-${label}`).innerHTML = '<p class="muted">Provider overview unavailable.</p>';
    });
    byId("home-movers").innerHTML = '<p class="muted">Provider overview unavailable.</p>';
  }
}

function renderOverview(payload) {
  const tape = payload.tape || [];
  const tapeCards = (repeated = false) => tape.map((item) => `
    <button class="tape-card" data-market-ticker="${escapeHtml(item.ticker)}" aria-label="Analyze ${escapeHtml(item.name)}"${repeated ? ' aria-hidden="true" tabindex="-1"' : ""}>
      <span><small>${escapeHtml(item.name)}</small><strong>${fixedNumber(item.price, item.price < 1 ? 4 : 2)}</strong><b class="${directionClass(item.change_percent)}"><span>${signedNumber(item.change_value, item.price < 1 ? 4 : 2)}</span><span>${percent(item.change_percent)}</span></b></span>
      ${svgSparkline(item.history, item.change_percent)}
    </button>`).join("");
  byId("market-tape-track").innerHTML = tape.length ? `${tapeCards()}${tapeCards(true)}${tapeCards(true)}` : '<div class="tape-loading">No market overview observations returned.</div>';
  startTapeMotion(tape.length > 0);

  const macroItems = Object.values(payload.macro || {}).filter(Boolean);
  const macroMarkup = macroItems.map((item) => `
    <div class="macro-row"><span><small>${escapeHtml(item.name)}</small><strong>${number(item.price)}</strong></span>${svgSparkline(item.history, item.change_percent)}<b class="${directionClass(item.change_percent)}">${percent(item.change_percent)}</b></div>`).join("");
  byId("macro-list").innerHTML = macroItems.length ? macroMarkup : '<p class="muted">No macro observations returned.</p>';
  byId("home-macro-list").innerHTML = macroItems.length ? macroItems.map((item) => `<button class="pulse-card" data-market-ticker="${escapeHtml(item.ticker)}"><span>${escapeHtml(item.name)}</span><strong>${number(item.price)}</strong><b class="${directionClass(item.change_percent)}">${percent(item.change_percent)}</b>${svgSparkline(item.history, item.change_percent)}</button>`).join("") : '<p class="muted">No macro observations returned.</p>';
  byId("home-market-source").textContent = `${payload.source} · ${payload.freshness}`;
  byId("home-asof").textContent = `Updated ${dateLabel(payload.fetched_at, true)}`;
  byId("mover-method").textContent = payload.mover_method || "Separate market screens";
  renderMovers();
}

function moverRows(items, limit = 5) {
  return items?.length ? items.slice(0, limit).map((item) => `
    <button class="mover-row" data-market-ticker="${escapeHtml(item.ticker)}">
      <span class="mover-copy"><small>${escapeHtml(item.name)}</small><strong>${escapeHtml(item.ticker)}</strong></span>
      ${svgSparkline(item.history, item.change_percent)}
      <span class="mover-values"><span>${number(item.price)}</span><b class="${directionClass(item.change_percent)}">${percent(item.change_percent)}</b></span>
    </button>`).join("") : '<p class="muted">No observations returned.</p>';
}

function renderMovers() {
  const groups = [
    ["trending", "Trending", "Most active"],
    ["gainers", "Gainers", "Largest positive move"],
    ["losers", "Losers", "Largest negative move"],
  ];
  groups.forEach(([key]) => { byId(`movers-${key}`).innerHTML = moverRows(state.overview?.[key], 3); });
  byId("home-movers").innerHTML = groups.map(([key, title, subtitle]) => `<section class="mover-column"><h3>${title}<small>${subtitle}</small></h3>${moverRows(state.overview?.[key], 5)}</section>`).join("");
}

function startTapeMotion(hasItems) {
  cancelAnimationFrame(tapeMotionFrame);
  const viewport = byId("market-tape");
  viewport.scrollLeft = 0;
  tapeScrollPosition = 0;
  tapeLastFrame = 0;
  if (!hasItems || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const step = (timestamp) => {
    if (!tapeLastFrame) tapeLastFrame = timestamp;
    const elapsed = Math.min(34, timestamp - tapeLastFrame);
    tapeLastFrame = timestamp;
    if (!tapePaused) {
      tapeScrollPosition += elapsed * 0.04;
      const sequenceWidth = byId("market-tape-track").scrollWidth / 3;
      if (sequenceWidth && tapeScrollPosition >= sequenceWidth) tapeScrollPosition %= sequenceWidth;
      viewport.scrollLeft = Math.floor(tapeScrollPosition);
    } else {
      tapeScrollPosition = viewport.scrollLeft;
    }
    tapeMotionFrame = requestAnimationFrame(step);
  };
  tapeMotionFrame = requestAnimationFrame(step);
}

function nudgeTape(distance) {
  const viewport = byId("market-tape");
  const sequenceWidth = byId("market-tape-track").scrollWidth / 3;
  if (!sequenceWidth) return;
  tapeScrollPosition = ((viewport.scrollLeft + distance) % sequenceWidth + sequenceWidth) % sequenceWidth;
  viewport.scrollLeft = Math.round(tapeScrollPosition);
}

async function loadMarket() {
  const requestedTicker = state.ticker;
  setMarketState("loading", `Loading observed ${requestedTicker} data…`);
  setHeaderState("warn", "Connecting");
  byId("asset-ticker").textContent = requestedTicker;
  byId("news-ticker").textContent = requestedTicker;
  byId("research-ticker").textContent = requestedTicker;
  byId("ticker-input").value = requestedTicker;
  byId("source-status").textContent = "Waiting for provider response.";

  const [snapshotResult, newsResult, eventsResult] = await Promise.allSettled([
    request(`/v1/terminal/${encodeURIComponent(requestedTicker)}?period=${state.period}`),
    request(`/v1/news/${encodeURIComponent(requestedTicker)}?limit=8`),
    request(`/v1/events/${encodeURIComponent(requestedTicker)}`),
  ]);
  if (requestedTicker !== state.ticker) return;

  if (snapshotResult.status === "fulfilled") {
    state.snapshot = snapshotResult.value;
    try {
      renderMarket(snapshotResult.value);
      setMarketState("ready", `${requestedTicker} loaded · ${snapshotResult.value.freshness}.`);
      setHeaderState("ok", "Observed");
    } catch (error) {
      state.snapshot = null;
      renderMarketUnavailable(error.message);
      setMarketState("error", `Client render unavailable: ${error.message}`);
      setHeaderState("error", "Render error");
    }
  } else {
    state.snapshot = null;
    renderMarketUnavailable(snapshotResult.reason.message);
    setMarketState("error", `Observed data unavailable: ${snapshotResult.reason.message}`);
    setHeaderState("error", "Unavailable");
  }

  if (newsResult.status === "fulfilled") {
    state.assetNews = newsResult.value;
    renderSidebarNews(newsResult.value);
    if (state.route === "news") renderNewsFeed(byId("asset-news-list"), newsResult.value);
  } else {
    state.assetNews = { data_status: "unavailable", items: [] };
    renderSidebarNews(state.assetNews, newsResult.reason.message);
  }
  if (eventsResult.status === "fulfilled") {
    state.events = eventsResult.value;
    renderEvents(eventsResult.value);
  } else {
    renderEvents({ events: [], sources: [] }, eventsResult.reason.message);
  }
}

function renderMarket(snapshot) {
  const metrics = snapshot.metrics || {};
  const profile = snapshot.profile || {};
  const currency = snapshot.currency || "USD";
  const quoteType = String(snapshot.quote_type || "unknown").toLowerCase();
  const isCrypto = quoteType.includes("crypto") || snapshot.ticker.endsWith("-USD");
  byId("asset-ticker").textContent = snapshot.ticker;
  byId("asset-name").textContent = `${snapshot.name || snapshot.ticker} · ${snapshot.exchange || "Unknown venue"}`;
  byId("asset-type").textContent = `${snapshot.quote_type || "Asset"} · observed`;
  byId("asset-price").textContent = money(snapshot.price, currency);
  byId("header-price").textContent = money(snapshot.price, currency);
  const change = percent(snapshot.change_percent);
  byId("asset-change").textContent = `${change} daily`;
  byId("asset-change").className = directionClass(snapshot.change_percent);
  byId("header-change").textContent = change;
  byId("header-change").className = directionClass(snapshot.change_percent);

  const fundamentals = isCrypto ? [
    ["Market cap", compact(metrics.market_cap)],
    ["24h volume", compact(metrics.volume)],
    ["Circulating", compact(metrics.circulating_supply)],
    ["Max supply", compact(metrics.max_supply)],
    ["52W high", money(metrics.fifty_two_week_high, currency)],
    ["52W low", money(metrics.fifty_two_week_low, currency)],
  ] : [
    ["Market cap", compact(metrics.market_cap)],
    ["Volume", compact(metrics.volume)],
    ["Trailing P/E", number(metrics.trailing_pe)],
    ["Profit margin", ratioPercent(metrics.profit_margin)],
    ["Return on equity", ratioPercent(metrics.return_on_equity)],
    ["Beta", number(metrics.beta)],
  ];
  byId("fundamental-grid").innerHTML = fundamentals.map(([label, value]) => `<div class="fundamental-item"><span>${label}</span><strong>${value}</strong></div>`).join("");

  updateRange(snapshot);
  byId("left-sma20").textContent = money(metrics.sma_20, currency);
  byId("left-sma50").textContent = money(metrics.sma_50, currency);
  byId("asset-sector").textContent = [profile.sector, profile.industry].filter(Boolean).join(" · ") || "Profile unavailable";
  const description = profile.description || "Provider profile description unavailable for this asset.";
  byId("asset-description").textContent = description;
  byId("toggle-about").hidden = description.length < 290;
  document.querySelector(".about-asset").classList.toggle("is-expanded", state.aboutExpanded);
  byId("toggle-about").textContent = state.aboutExpanded ? "View less" : "View more";

  byId("tech-rsi").textContent = number(metrics.rsi_14, 1);
  byId("tech-volatility").textContent = percent(metrics.annualized_volatility, 1, false);
  byId("tech-trend").textContent = !finite(metrics.sma_20) || !finite(metrics.sma_50) ? "Unavailable" : Number(metrics.sma_20) >= Number(metrics.sma_50) ? "20D above 50D" : "20D below 50D";
  byId("tech-asof").textContent = dateLabel(snapshot.history?.at(-1)?.date);
  byId("source-status").textContent = `${snapshot.source}. ${snapshot.freshness}. Fetched ${dateLabel(snapshot.fetched_at, true)}.`;
  const technicalLabels = document.querySelectorAll(".technical-strip div > span");
  if (state.assetClass === "crypto") {
    technicalLabels[1].textContent = "365-day annualized volatility";
    technicalLabels[2].textContent = "30-observation momentum";
    byId("tech-trend").textContent = percent(metrics.momentum_30, 1);
  } else {
    technicalLabels[1].textContent = "252-day annualized volatility";
    technicalLabels[2].textContent = "Trend";
  }
  const optionsButton = byId("load-options");
  optionsButton.disabled = STATIC_DEMO || state.assetClass === "crypto";
  if (state.assetClass === "crypto") {
    byId("options-state").innerHTML = `<div class="empty-state"><strong>Spot crypto options are outside this feed</strong><p>${escapeHtml(state.researchProfile?.options_policy || "The selected spot ticker does not expose a standard listed chain.")}</p></div>`;
  } else if (!state.options.has(state.ticker)) {
    byId("options-state").innerHTML = '<div class="empty-state"><strong>Options not loaded</strong><p>The chain is requested only when needed.</p></div>';
  }
  updateResearchContext();
  drawMarketChart();
}

function updateRange(snapshot) {
  const use52w = byId("performance-period").value === "52w";
  const low = use52w ? snapshot.metrics.fifty_two_week_low : snapshot.metrics.period_low;
  const high = use52w ? snapshot.metrics.fifty_two_week_high : snapshot.metrics.period_high;
  byId("range-low").textContent = money(low, snapshot.currency);
  byId("range-high").textContent = money(high, snapshot.currency);
  const position = finite(low) && finite(high) && Number(high) !== Number(low)
    ? ((Number(snapshot.price) - Number(low)) / (Number(high) - Number(low))) * 100
    : 50;
  byId("range-position").style.left = `${Math.max(0, Math.min(100, position))}%`;
}

function renderMarketUnavailable(message) {
  byId("asset-name").textContent = "Observed source unavailable";
  byId("asset-price").textContent = "—";
  byId("asset-change").textContent = "No substitute data shown";
  byId("asset-change").className = "neutral";
  byId("header-price").textContent = "—";
  byId("header-change").textContent = "—";
  byId("fundamental-grid").innerHTML = ["Market cap", "Volume", "P/E", "Margin", "ROE", "Beta"].map((label) => `<div class="fundamental-item"><span>${label}</span><strong>—</strong></div>`).join("");
  ["range-low", "range-high", "left-sma20", "left-sma50", "tech-rsi", "tech-volatility", "tech-trend", "tech-asof"].forEach((id) => { byId(id).textContent = "—"; });
  byId("price-chart").innerHTML = '<div class="chart-empty">No chart rendered because observed data is unavailable.</div>';
  byId("source-status").textContent = message;
}

let chartSequence = 0;
function chartDomain(points, keys) {
  const values = points
    .flatMap((point) => keys.map((key) => point[key]))
    .filter(finite)
    .map(Number);
  if (!values.length) return null;
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) { min -= 1; max += 1; }
  const padding = (max - min) * 0.06;
  return [min - padding, max + padding];
}

function linePoints(points, key, width, top, bottom, domain, transform = (value) => value) {
  if (!domain) return "";
  return points.map((point, index) => {
    if (!finite(point[key])) return null;
    const value = transform(Number(point[key]));
    if (!Number.isFinite(value)) return null;
    const x = 46 + (index / Math.max(1, points.length - 1)) * (width - 62);
    const y = top + (1 - (value - domain[0]) / (domain[1] - domain[0])) * (bottom - top);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).filter(Boolean).join(" ");
}

function attachChartTooltip(container, points, formatter, verticalEnd = 435) {
  const tooltip = container.querySelector(".chart-tooltip");
  const crosshair = container.querySelector("[data-crosshair]");
  if (!tooltip || !crosshair || !points.length) return;
  container.onpointermove = (event) => {
    const rect = container.getBoundingClientRect();
    const localX = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
    const viewX = localX / rect.width * 1000;
    const ratio = Math.max(0, Math.min(1, (viewX - 46) / (984 - 46)));
    const index = Math.round(ratio * (points.length - 1));
    const point = points[index];
    const crossX = 46 + (index / Math.max(1, points.length - 1)) * (984 - 46);
    crosshair.setAttribute("x1", crossX);
    crosshair.setAttribute("x2", crossX);
    crosshair.setAttribute("y2", verticalEnd);
    crosshair.setAttribute("visibility", "visible");
    tooltip.innerHTML = formatter(point);
    tooltip.hidden = false;
    const tooltipWidth = 180;
    tooltip.style.left = `${Math.max(6, Math.min(rect.width - tooltipWidth - 6, localX + 12))}px`;
    tooltip.style.top = "8px";
  };
  container.onpointerleave = () => {
    tooltip.hidden = true;
    crosshair.setAttribute("visibility", "hidden");
  };
}

function drawMarketChart() {
  const container = byId("price-chart");
  const points = state.snapshot?.history || [];
  if (points.length < 2) {
    container.innerHTML = '<div class="chart-empty">No observed price series returned.</div>';
    return;
  }
  const width = 1000;
  const height = 470;
  const showAverages = byId("show-sma").checked;
  const showVolume = byId("show-volume").checked;
  const showRsi = byId("show-rsi").checked;
  const hasLowerPanel = showVolume || showRsi;
  const priceBottom = hasLowerPanel ? 292 : 425;
  const transform = state.chartScale === "log" ? (value) => value > 0 ? Math.log(value) : Number.NaN : (value) => value;
  const inverse = state.chartScale === "log" ? Math.exp : (value) => value;
  const domainKeys = showAverages ? ["low", "high", "close", "sma20", "sma50"] : ["low", "high", "close"];
  const rawDomain = chartDomain(
    points.map((point) => Object.fromEntries(
      domainKeys.map((key) => [key, finite(point[key]) ? transform(Number(point[key])) : null]),
    )),
    domainKeys,
  );
  const domain = rawDomain;
  if (!domain) {
    container.innerHTML = '<div class="chart-empty">No finite observations returned.</div>';
    return;
  }
  const mapY = (value) => 24 + (1 - (transform(Number(value)) - domain[0]) / (domain[1] - domain[0])) * (priceBottom - 24);
  const mapX = (index, total = points.length) => 46 + (index / Math.max(1, total - 1)) * (width - 62);
  const maxVolume = Math.max(...points.map((point) => Number(point.volume) || 0), 1);
  const grid = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const y = 24 + ratio * (priceBottom - 24);
    const label = inverse(domain[1] - ratio * (domain[1] - domain[0]));
    return `<line x1="46" x2="984" y1="${y}" y2="${y}" stroke="rgba(148,163,184,.1)"/><text x="8" y="${y + 4}" fill="#64748b" font-size="10" font-family="JetBrains Mono">${number(label, 1)}</text>`;
  }).join("");
  const volume = showVolume ? points.map((point, index) => {
    const barHeight = ((Number(point.volume) || 0) / maxVolume) * 45;
    return `<rect x="${mapX(index) - 1}" y="${354 - barHeight}" width="2" height="${barHeight}" fill="rgba(96,165,250,.28)"/>`;
  }).join("") : "";

  let mainSeries = "";
  if (state.chartType === "candlestick") {
    const step = Math.max(1, Math.ceil(points.length / 92));
    const sampled = points.filter((_, index) => index % step === 0 || index === points.length - 1);
    const candleWidth = Math.max(2.2, Math.min(8, ((width - 62) / sampled.length) * 0.58));
    mainSeries = sampled.map((point, index) => {
      const x = mapX(index, sampled.length);
      if (![point.open, point.close, point.high, point.low].every(finite)) return "";
      const open = Number(point.open);
      const close = Number(point.close);
      const high = Number(point.high);
      const low = Number(point.low);
      const color = close >= open ? "#4ade80" : "#f87171";
      const yOpen = mapY(open);
      const yClose = mapY(close);
      return `<line x1="${x}" x2="${x}" y1="${mapY(high)}" y2="${mapY(low)}" stroke="${color}" stroke-width="1"/><rect x="${x - candleWidth / 2}" y="${Math.min(yOpen, yClose)}" width="${candleWidth}" height="${Math.max(1.5, Math.abs(yOpen - yClose))}" fill="${color}" opacity=".82"/>`;
    }).join("");
  } else {
    const closeLine = linePoints(points, "close", width, 24, priceBottom, domain, transform);
    const [first, ...rest] = closeLine.split(" ");
    const last = rest.at(-1) || first;
    const gradientId = `price-area-${++chartSequence}`;
    const area = closeLine ? `${first} ${rest.join(" ")} ${last.split(",")[0]},${priceBottom} ${first.split(",")[0]},${priceBottom}` : "";
    mainSeries = `<defs><linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22d3ee" stop-opacity=".26"/><stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></linearGradient></defs><polygon points="${area}" fill="url(#${gradientId})"/><polyline points="${closeLine}" fill="none" stroke="#7dd3fc" stroke-width="2.1" vector-effect="non-scaling-stroke"/>`;
  }
  const sma20 = showAverages ? linePoints(points, "sma20", width, 24, priceBottom, domain, transform) : "";
  const sma50 = showAverages ? linePoints(points, "sma50", width, 24, priceBottom, domain, transform) : "";
  const rsiLine = showRsi ? linePoints(points, "rsi", width, 382, 432, [0, 100]) : "";
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio, tickIndex) => {
    const index = Math.round(ratio * (points.length - 1));
    const x = mapX(index);
    const anchor = tickIndex === 0 ? "start" : tickIndex === 4 ? "end" : "middle";
    return `<line x1="${x}" x2="${x}" y1="${priceBottom}" y2="${priceBottom + 5}" stroke="#64748b"/><text x="${x}" y="462" text-anchor="${anchor}" fill="#64748b" font-size="9" font-family="JetBrains Mono">${escapeHtml(dateLabel(points[index].date))}</text>`;
  }).join("");
  const lowerPanels = `${showVolume ? '<line x1="46" x2="984" y1="304" y2="304" stroke="rgba(148,163,184,.12)"/><text x="8" y="318" fill="#64748b" font-size="9" font-family="JetBrains Mono">VOL</text>' : ""}${showRsi ? '<rect x="46" y="397" width="938" height="20" fill="rgba(74,222,128,.035)"/><line x1="46" x2="984" y1="397" y2="397" stroke="rgba(74,222,128,.18)"/><line x1="46" x2="984" y1="417" y2="417" stroke="rgba(248,113,113,.18)"/><text x="12" y="401" fill="#4ade80" font-size="9" font-family="JetBrains Mono">70</text><text x="12" y="421" fill="#f87171" font-size="9" font-family="JetBrains Mono">30</text>' : ""}`;
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Observed ${escapeHtml(state.ticker)} price, moving averages and volume">
    ${grid}${lowerPanels}${volume}${mainSeries}
    <polyline points="${sma20}" fill="none" stroke="#fbbf24" stroke-width="1.35" opacity=".92" vector-effect="non-scaling-stroke"/>
    <polyline points="${sma50}" fill="none" stroke="#a78bfa" stroke-width="1.35" opacity=".88" vector-effect="non-scaling-stroke"/>
    <polyline points="${rsiLine}" fill="none" stroke="#4ade80" stroke-width="1.15" opacity=".85" vector-effect="non-scaling-stroke"/>
    ${xTicks}<text x="52" y="18" fill="#94a3b8" font-size="9" font-family="JetBrains Mono">PRICE · ${escapeHtml(state.snapshot.currency || "USD")} · ${state.chartScale.toUpperCase()}</text>
    <line data-crosshair x1="46" x2="46" y1="24" y2="435" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="3 4" visibility="hidden"/>
  </svg><div class="chart-tooltip" hidden></div>`;
  attachChartTooltip(container, points, (point) => `<strong>${escapeHtml(dateLabel(point.date))}</strong><span>Open <b>${money(point.open, state.snapshot.currency)}</b></span><span>High <b>${money(point.high, state.snapshot.currency)}</b></span><span>Low <b>${money(point.low, state.snapshot.currency)}</b></span><span>Close <b>${money(point.close, state.snapshot.currency)}</b></span><span>Volume <b>${compact(point.volume)}</b></span><span>RSI 14 <b>${number(point.rsi, 1)}</b></span>`);
}

function renderSidebarNews(payload, error = "") {
  const items = payload?.items || [];
  byId("sidebar-news").innerHTML = items.length ? items.slice(0, 4).map((item) => {
    const headline = item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>` : `<span>${escapeHtml(item.title)}</span>`;
    const thumbnail = item.thumbnail ? `<img src="${escapeHtml(item.thumbnail)}" alt="" loading="lazy" />` : '<span class="news-thumb-fallback" aria-hidden="true">HQ</span>';
    return `<article>${thumbnail}<div>${headline}<p>${escapeHtml(item.publisher)} · ${dateLabel(item.published_at)}</p></div></article>`;
  }).join("") : `<p class="muted">${escapeHtml(error || "No source headlines returned.")}</p>`;
}

function renderNewsFeed(container, payload, error = "") {
  const items = payload?.items || [];
  container.innerHTML = items.length ? items.map((item) => {
    const title = item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>` : `<span>${escapeHtml(item.title)}</span>`;
    const thumbnail = item.thumbnail ? `<img src="${escapeHtml(item.thumbnail)}" alt="" loading="lazy" />` : '<span class="news-thumb-fallback" aria-hidden="true">HQ</span>';
    return `<article class="news-item">${thumbnail}<div>${title}<p>${escapeHtml(item.publisher)} · ${dateLabel(item.published_at)}</p></div></article>`;
  }).join("") : `<div class="feed-empty">${escapeHtml(error || "No source headlines were returned. No replacement headlines are generated.")}</div>`;
}

async function loadHomeNews(force = false) {
  if (state.marketNews && !force) {
    renderNewsFeed(byId("home-news-list"), state.marketNews);
    return;
  }
  byId("home-news-list").innerHTML = '<div class="feed-empty">Loading market headlines…</div>';
  try {
    const marketContextTicker = state.assetClass === "crypto" ? "BTC-USD" : "^GSPC";
    state.marketNews = await request(`/v1/news/${encodeURIComponent(marketContextTicker)}?limit=12`);
    renderNewsFeed(byId("home-news-list"), state.marketNews);
    if (state.route === "news") renderNewsFeed(byId("general-news-list"), state.marketNews);
  } catch (error) {
    state.marketNews = { data_status: "unavailable", items: [] };
    renderNewsFeed(byId("home-news-list"), state.marketNews, error.message);
    if (state.route === "news") renderNewsFeed(byId("general-news-list"), state.marketNews, error.message);
  }
}

async function loadNewsHub(force = false) {
  byId("news-ticker").textContent = state.ticker;
  byId("asset-news-source").textContent = `${state.ticker} provider metadata`;
  byId("market-news-context").textContent = state.assetClass === "crypto" ? "Bitcoin market context" : "S&P 500 context";
  if (state.assetNews && !force) renderNewsFeed(byId("asset-news-list"), state.assetNews);
  else byId("asset-news-list").innerHTML = '<div class="feed-empty">Loading asset headlines…</div>';
  if (!state.marketNews || force) await loadHomeNews(force);
  renderNewsFeed(byId("general-news-list"), state.marketNews);
  if (!state.assetNews || force) {
    try {
      state.assetNews = await request(`/v1/news/${encodeURIComponent(state.ticker)}?limit=12`);
      renderNewsFeed(byId("asset-news-list"), state.assetNews);
      renderSidebarNews(state.assetNews);
    } catch (error) {
      renderNewsFeed(byId("asset-news-list"), { items: [] }, error.message);
    }
  }
}

function eventRows(events, limit = 5) {
  return events?.length ? events.slice(0, limit).map((event) => {
    const date = new Date(`${event.date}T12:00:00`);
    const dateBlock = Number.isNaN(date.valueOf()) ? '<time>—</time>' : `<time datetime="${escapeHtml(event.date)}"><b>${date.toLocaleDateString(undefined, { day: "2-digit" })}</b><span>${date.toLocaleDateString(undefined, { month: "short" })}</span></time>`;
    const title = event.url ? `<a href="${escapeHtml(event.url)}" target="_blank" rel="noreferrer">${escapeHtml(event.title)}</a>` : `<strong>${escapeHtml(event.title)}</strong>`;
    return `<article class="event-row kind-${escapeHtml(event.kind)}">${dateBlock}<div>${title}<p>${escapeHtml(event.detail || event.source || "Scheduled event")}</p></div></article>`;
  }).join("") : '<p class="muted">No verified upcoming events were returned.</p>';
}

function renderEvents(payload, error = "") {
  const events = payload?.events || [];
  byId("home-events-list").innerHTML = events.length ? eventRows(events, 5) : `<p class="muted">${escapeHtml(error || "No verified upcoming events were returned.")}</p>`;
  byId("sidebar-events-list").innerHTML = events.length ? eventRows(events, 3) : `<p class="muted">${escapeHtml(error || "No verified upcoming events were returned.")}</p>`;
  renderEventsCalendar(payload);
}

function renderEventsCalendar(payload) {
  const events = payload?.events || [];
  const container = byId("events-calendar");
  if (!events.length) {
    container.innerHTML = '<div class="feed-empty">No verified calendar events are available from the configured sources.</div>';
    return;
  }
  const months = new Map();
  events.forEach((event) => {
    const key = String(event.date).slice(0, 7);
    if (!months.has(key)) months.set(key, []);
    months.get(key).push(event);
  });
  container.innerHTML = [...months.entries()].map(([monthKey, monthEvents]) => {
    const [year, month] = monthKey.split("-").map(Number);
    const first = new Date(year, month - 1, 1);
    const days = new Date(year, month, 0).getDate();
    const blanks = Array.from({ length: first.getDay() }, () => '<span class="calendar-blank"></span>').join("");
    const byDay = new Map();
    monthEvents.forEach((event) => {
      const day = Number(String(event.date).slice(8, 10));
      if (!byDay.has(day)) byDay.set(day, []);
      byDay.get(day).push(event);
    });
    const cells = Array.from({ length: days }, (_, index) => {
      const day = index + 1;
      const dayEvents = byDay.get(day) || [];
      const title = dayEvents.map((event) => event.title).join(" · ");
      return `<span class="calendar-day ${dayEvents.length ? "has-event" : ""}" title="${escapeHtml(title)}"><b>${day}</b>${dayEvents.length ? `<i>${dayEvents.length}</i>` : ""}</span>`;
    }).join("");
    return `<section class="calendar-month"><h3>${first.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</h3><div class="weekday-row"><span>Sun</span><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span></div><div class="calendar-grid">${blanks}${cells}</div><div class="calendar-agenda">${eventRows(monthEvents, monthEvents.length)}</div></section>`;
  }).join("");
  const sourceNames = (payload.sources || []).filter((source) => source.status === "available").map((source) => source.name);
  byId("events-source-line").textContent = sourceNames.join(" · ") || "Configured sources unavailable";
}

async function loadEvents(force = false) {
  if (state.events && !force) {
    renderEvents(state.events);
    return;
  }
  const contextTicker = state.hasSelection ? state.ticker : state.assetClass === "crypto" ? "BTC-USD" : "SPY";
  try {
    state.events = await request(`/v1/events/${encodeURIComponent(contextTicker)}`);
    renderEvents(state.events);
  } catch (error) {
    state.events = { events: [], sources: [] };
    renderEvents(state.events, error.message);
  }
}

function drawComparisonChart(container, points) {
  if (!points?.length) {
    container.innerHTML = '<div class="chart-empty">No series returned.</div>';
    return;
  }
  const width = 1000;
  const height = 370;
  const equityTop = 25;
  const equityBottom = 247;
  const domain = chartDomain(points, ["strategy", "market"]);
  const strategy = linePoints(points, "strategy", width, equityTop, equityBottom, domain);
  const benchmark = linePoints(points, "market", width, equityTop, equityBottom, domain);
  const drawdownValues = points.map((point) => Number(point.drawdown)).filter(Number.isFinite);
  const minDrawdown = Math.min(...drawdownValues, -1);
  const drawdownLine = linePoints(points, "drawdown", width, 282, 335, [minDrawdown, 0]);
  const drawdownFirst = drawdownLine.split(" ")[0] || "46,282";
  const drawdownLast = drawdownLine.split(" ").at(-1) || "984,282";
  const drawdownArea = `${drawdownFirst} ${drawdownLine} ${drawdownLast.split(",")[0]},282 ${drawdownFirst.split(",")[0]},282`;
  const yGrid = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const y = equityTop + ratio * (equityBottom - equityTop);
    const value = domain[1] - ratio * (domain[1] - domain[0]);
    return `<line x1="46" x2="984" y1="${y}" y2="${y}" stroke="rgba(148,163,184,.1)"/><text x="7" y="${y + 4}" fill="#64748b" font-size="9" font-family="JetBrains Mono">$${number(value, 2)}</text>`;
  }).join("");
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio, tickIndex) => {
    const index = Math.round(ratio * (points.length - 1));
    const x = 46 + ratio * (984 - 46);
    const anchor = tickIndex === 0 ? "start" : tickIndex === 4 ? "end" : "middle";
    return `<line x1="${x}" x2="${x}" y1="335" y2="341" stroke="#64748b"/><text x="${x}" y="362" text-anchor="${anchor}" fill="#64748b" font-size="9" font-family="JetBrains Mono">${escapeHtml(dateLabel(points[index].date))}</text>`;
  }).join("");
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Growth of one dollar for strategy and underlying benchmark, with strategy drawdown">
    ${yGrid}<polyline points="${benchmark}" fill="none" stroke="#fbbf24" stroke-width="1.5" opacity=".82"/><polyline points="${strategy}" fill="none" stroke="#7dd3fc" stroke-width="2.1"/>
    <line x1="46" x2="984" y1="282" y2="282" stroke="rgba(148,163,184,.16)"/><polygon points="${drawdownArea}" fill="rgba(248,113,113,.16)"/><polyline points="${drawdownLine}" fill="none" stroke="#f87171" stroke-width="1"/>
    <text x="52" y="17" fill="#94a3b8" font-size="9" font-family="JetBrains Mono">GROWTH OF $1</text><text x="8" y="295" fill="#f87171" font-size="9" font-family="JetBrains Mono">DD</text><text x="8" y="335" fill="#64748b" font-size="9" font-family="JetBrains Mono">${number(minDrawdown, 0)}%</text>${xTicks}
    <line data-crosshair x1="46" x2="46" y1="25" y2="335" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="3 4" visibility="hidden"/>
  </svg><div class="chart-tooltip" hidden></div>`;
  attachChartTooltip(container, points, (point) => `<strong>${escapeHtml(dateLabel(point.date))}</strong><span>Strategy <b>$${number(point.strategy, 4)}</b></span><span>Benchmark <b>$${number(point.market, 4)}</b></span><span>Drawdown <b>${percent(point.drawdown, 2, false)}</b></span><span>Position <b>${number(point.position, 1)}</b></span><span>Probability <b>${finite(point.probability) ? ratioPercent(point.probability, 1) : "Rule-based"}</b></span><span>Daily return <b>${percent(point.strategy_return, 3)}</b></span>`, 335);
}

async function runBacktest(event) {
  event.preventDefault();
  const runId = ++state.backtestRunId;
  const requestedTicker = state.ticker;
  const requestedAssetClass = state.assetClass;
  const engine = byId("backtest-engine").value;
  const button = byId("run-backtest");
  button.disabled = true;
  button.textContent = engine === "sma" ? "Running simulation…" : "Training purged folds…";
  byId("backtest-result").innerHTML = `<div class="empty-state"><strong>${engine === "sma" ? "Applying fixed technical rules" : "Selecting models inside chronological training windows"}</strong><p>Outer test windows remain untouched until scoring. No interim result is presented as evidence.</p></div>`;
  try {
    const result = await request("/v1/backtests", {
      method: "POST",
      body: JSON.stringify({
        ticker: requestedTicker,
        engine,
        asset_class: requestedAssetClass,
        short_window: Number(byId("short-window").value),
        long_window: Number(byId("long-window").value),
        train_window: Number(byId("train-window").value),
        test_window: Number(byId("test-window").value),
        validation_fraction: Number(byId("validation-fraction").value),
        target_horizon: Number(byId("target-horizon").value),
        long_threshold: Number(byId("long-threshold").value),
        short_threshold: Number(byId("short-threshold").value),
        position_mode: byId("position-mode").value,
        transaction_cost_bps: Number(byId("cost-bps").value),
        slippage_bps: Number(byId("slippage-bps").value),
        risk_free_rate: Number(byId("risk-free-rate").value),
        lookback_years: Number(byId("lookback-years").value),
        use_regime_filter: byId("regime-filter").checked,
        n_trials: Number(byId("n-trials").value),
      }),
    });
    if (runId !== state.backtestRunId) return;
    renderBacktest(result);
  } catch (error) {
    if (runId !== state.backtestRunId) return;
    byId("backtest-result").innerHTML = `<div class="empty-state"><strong>Simulation unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
  } finally {
    if (runId === state.backtestRunId) {
      button.disabled = false;
      button.textContent = STATIC_DEMO ? "Reload frozen SMA result" : "Run purged walk-forward test";
    }
  }
}

function renderBacktest(result) {
  const evidence = result.evidence || {};
  const folds = evidence.folds || [];
  const metrics = [
    ["Total return", percent(result.Return_Pct)],
    ["Underlying", percent(result.Market_Return_Pct)],
    ["Annualized return", percent(result.Annualized_Return_Pct)],
    ["Annualized volatility", percent(result.Annualized_Volatility_Pct, 1, false)],
    ["Annualized Sharpe (excess return)", number(result.Sharpe_Ratio)],
    ["Sortino", number(result.Sortino_Ratio)],
    ["Calmar", number(result.Calmar_Ratio)],
    ["Maximum drawdown", percent(result.Max_Drawdown_Pct, 2, false)],
    ["Exposure", percent(result.Exposure_Pct, 1, false)],
    ["Turnover", `${number(result.Turnover, 1)}x`],
    ["Position changes", number(result.Total_Trades, 0)],
    ["Modeled cost drag", percent(result.Total_Cost_Pct, 2, false)],
  ];
  const foldRows = folds.map((fold) => `<tr><td>${escapeHtml(fold.selected_model)}</td><td>${escapeHtml(fold.test_start)} → ${escapeHtml(fold.test_end)}</td><td>${number(fold.validation_log_loss, 3)}</td><td>${number(fold.test_log_loss, 3)}</td><td>${number(fold.test_brier_score, 3)}</td><td>${ratioPercent(fold.test_balanced_accuracy)}</td></tr>`).join("");
  const detail = folds.length ? `<table class="fold-table"><thead><tr><th>Selected model</th><th>Untouched outer test</th><th>Validation log loss</th><th>Test log loss</th><th>Test Brier</th><th>Balanced accuracy</th></tr></thead><tbody>${foldRows}</tbody></table>` : `<p>Parameters: ${number(evidence.short_window, 0)} / ${number(evidence.long_window, 0)} observation SMA. No parameter or model search was performed.</p>`;
  const selectionText = evidence.model_selections ? Object.entries(evidence.model_selections).map(([model, count]) => `${model}: ${count} folds`).join(" · ") : "Rule-based engine";
  byId("backtest-result").innerHTML = `
    <div class="panel-heading compact"><div><h2>${escapeHtml(evidence.ticker || state.ticker)} · ${escapeHtml(evidence.engine || "historical simulation")}</h2><p>${escapeHtml(evidence.asset_class || state.assetClass)} · ${number(evidence.annualization_factor, 0)} observations/year</p></div><span class="data-badge simulated">Simulated</span></div>
    <div class="backtest-scoreboard">${metrics.map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("")}</div>
    <div class="backtest-chart-legend"><span><i></i>Strategy growth of $1</span><span><i class="benchmark-key"></i>Underlying buy-and-hold</span><span><i class="drawdown-key"></i>Strategy drawdown</span><span class="legend-hint">Move across the chart for exact values</span></div>
    <div id="backtest-chart" class="chart-shell backtest-chart"></div>
    <div class="backtest-diagnostics"><div><span>Model selection</span><strong>${escapeHtml(selectionText)}</strong></div><div><span>Probability rule</span><strong>${finite(evidence.long_threshold) ? `Long ≥ ${ratioPercent(evidence.long_threshold)} · Short ≤ ${ratioPercent(evidence.short_threshold)}` : "SMA rule"}</strong></div><div><span>Embargo</span><strong>${number(evidence.embargo_observations, 0)} observations</strong></div><div><span>Regime reference</span><strong>${escapeHtml(evidence.regime_reference || "Disabled")}</strong></div><div><span>Execution drag</span><strong>${number(evidence.transaction_cost_bps, 1)} + ${number(evidence.slippage_bps, 1)} bps</strong></div><div><span>Daily hit rate</span><strong>${percent(result.Hit_Rate_Pct, 1, false)}</strong></div></div>
    <details class="evidence-block"><summary>Inspect fold evidence, features, and limitations</summary><p>${escapeHtml(evidence.selection_rule || "Selection rule unavailable.")} ${escapeHtml(evidence.outer_test_policy || "")}</p>${detail}${evidence.features ? `<p>Features: ${escapeHtml(evidence.features.join(", "))}</p>` : ""}<ul class="limitations-list">${(evidence.limitations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></details>`;
  drawComparisonChart(byId("backtest-chart"), result.series);
}

async function loadOptions() {
  const button = byId("load-options");
  const cached = state.options.get(state.ticker);
  if (cached) {
    renderOptions(cached);
    return;
  }
  button.disabled = true;
  button.textContent = "Loading chain…";
  byId("options-state").innerHTML = '<div class="empty-state"><strong>Requesting listed chain</strong><p>Only the first four expirations and most active calls will be returned.</p></div>';
  try {
    const result = await request(`/v1/options/${encodeURIComponent(state.ticker)}`);
    state.options.set(state.ticker, result);
    renderOptions(result);
  } catch (error) {
    byId("options-state").innerHTML = `<div class="empty-state"><strong>Options unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
  } finally {
    button.disabled = STATIC_DEMO || state.assetClass === "crypto";
    button.textContent = STATIC_DEMO ? "Live backend required" : "Load options";
  }
}

function renderOptions(result) {
  const points = result.points || [];
  if (result.data_status !== "available" || !points.length) {
    byId("options-state").innerHTML = `<div class="empty-state"><strong>No listed chain returned</strong><p>${escapeHtml(result.message || "This provider has no standard listed options for the selected asset.")}</p></div>`;
    return;
  }
  byId("options-state").innerHTML = `<div class="options-layout"><div id="options-chart" class="chart-shell"></div><div class="options-summary"><div><span>Put / call OI</span><strong>${number(result.put_call_ratio)}</strong></div><div><span>Expirations</span><strong>${number(result.expirations?.length, 0)}</strong></div><div><span>Call observations</span><strong>${number(points.length, 0)}</strong></div></div></div><ul class="limitations-list">${(result.limitations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  drawOptionsChart(byId("options-chart"), points);
}

function drawOptionsChart(container, points) {
  const width = 850;
  const height = 270;
  const strikes = points.map((point) => Number(point.strike)).filter(Number.isFinite);
  const ivs = points.map((point) => Number(point.iv) * 100).filter(Number.isFinite);
  if (!strikes.length || !ivs.length) {
    container.innerHTML = '<div class="chart-empty">No finite implied-volatility points returned.</div>';
    return;
  }
  let minStrike = Math.min(...strikes); let maxStrike = Math.max(...strikes);
  let minIv = Math.min(...ivs); let maxIv = Math.max(...ivs);
  if (minStrike === maxStrike) maxStrike += 1;
  if (minIv === maxIv) maxIv += 1;
  const expirations = [...new Set(points.map((point) => point.expiration))];
  const colors = ["#7dd3fc", "#fbbf24", "#a78bfa", "#4ade80"];
  const dots = points.map((point) => {
    const x = 42 + ((Number(point.strike) - minStrike) / (maxStrike - minStrike)) * 790;
    const y = 18 + (1 - ((Number(point.iv) * 100 - minIv) / (maxIv - minIv))) * 213;
    const radius = finite(point.volume) ? Math.max(1.7, Math.min(5, Math.log10(Number(point.volume) + 1))) : 2;
    return `<circle cx="${x}" cy="${y}" r="${radius}" fill="${colors[Math.max(0, expirations.indexOf(point.expiration)) % colors.length]}" opacity=".65"><title>${escapeHtml(point.expiration)} · strike ${number(point.strike)} · IV ${percent(Number(point.iv) * 100, 1, false)}</title></circle>`;
  }).join("");
  const legend = expirations.map((expiry, index) => `<text x="${45 + index * 150}" y="261" fill="${colors[index % colors.length]}" font-size="10" font-family="JetBrains Mono">${escapeHtml(expiry)}</text>`).join("");
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Provider supplied implied volatility by strike and expiration"><line x1="42" x2="832" y1="231" y2="231" stroke="rgba(148,163,184,.2)"/><line x1="42" x2="42" y1="18" y2="231" stroke="rgba(148,163,184,.2)"/>${dots}${legend}<text x="8" y="18" fill="#64748b" font-size="9" font-family="JetBrains Mono">${number(maxIv, 0)}%</text><text x="8" y="231" fill="#64748b" font-size="9" font-family="JetBrains Mono">${number(minIv, 0)}%</text></svg>`;
}

function extractDecision(text) {
  const match = String(text || "").match(/FINAL DECISION:\s*(BUY|SELL|HOLD)/i);
  return match ? match[1].toUpperCase() : "Not parsed";
}

function extractCommitteeField(text, label) {
  const expression = new RegExp(`${label}:\\s*([\\s\\S]*?)(?=\\n(?:OVERRIDE|SYNTHESIS|FINAL DECISION):|$)`, "i");
  return String(text || "").match(expression)?.[1]?.trim() || "Not returned.";
}

async function runAnalysis() {
  const runId = ++state.analysisRunId;
  const requestedTicker = state.ticker;
  const button = byId("run-analysis");
  button.disabled = true;
  button.textContent = "Generating…";
  byId("analysis-output").innerHTML = '<div class="empty-state compact-empty"><strong>Waiting for local model</strong><p>Evidence is sent to the configured Ollama service; no fallback prose is invented.</p></div>';
  try {
    const result = await request("/v1/analysis", {
      method: "POST",
      body: JSON.stringify({ ticker: requestedTicker, model: byId("model-choice").value }),
    });
    if (runId !== state.analysisRunId) return;
    const report = result.report || {};
    const decision = extractDecision(report.pm);
    const override = extractCommitteeField(report.pm, "OVERRIDE");
    const synthesis = extractCommitteeField(report.pm, "SYNTHESIS");
    const quant = typeof report.quant === "object" ? report.quant.summary : report.quant;
    byId("analysis-output").innerHTML = `<div class="committee-verdict"><section class="verdict-panel"><span>Committee conclusion · generated</span><strong>${escapeHtml(decision)}</strong><p>Override: ${escapeHtml(override)}</p></section><section class="quant-prior"><h3>Quantitative prior</h3><p>${escapeHtml(quant || "No quantitative baseline returned.")}</p></section></div><div class="committee-cases"><article class="committee-case bull"><h3>Bullish thesis</h3><p>${escapeHtml(report.bull || "No bullish thesis returned.")}</p></article><article class="committee-case bear"><h3>Bearish thesis</h3><p>${escapeHtml(report.bear || "No bearish thesis returned.")}</p></article></div><article class="committee-synthesis"><h3>Judge’s reasoning</h3><pre>${escapeHtml(synthesis)}</pre></article><details class="committee-evidence"><summary>Inspect headline evidence and raw committee output</summary><pre>${escapeHtml(report.news || "No news context returned.")}</pre><pre>${escapeHtml(report.pm || "No raw synthesis returned.")}</pre></details>`;
  } catch (error) {
    if (runId !== state.analysisRunId) return;
    byId("analysis-output").innerHTML = `<div class="empty-state compact-empty"><strong>Generated analysis unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
  } finally {
    if (runId === state.analysisRunId) {
      button.disabled = false;
      button.textContent = "Run committee";
    }
  }
}

function loadPositions() {
  try {
    const raw = localStorage.getItem("hermes-positions-v2");
    if (raw === null) return DEMO_POSITIONS.map((position) => ({ ...position }));
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : DEMO_POSITIONS.map((position) => ({ ...position }));
  } catch { return DEMO_POSITIONS.map((position) => ({ ...position })); }
}

function savePositions() {
  localStorage.setItem("hermes-positions-v2", JSON.stringify(state.positions));
  state.portfolioIsDemo = false;
}

function renderPositions() {
  const container = byId("positions-list");
  byId("position-count").textContent = `${state.portfolioIsDemo ? "Demo · " : ""}${state.positions.length} ${state.positions.length === 1 ? "asset" : "assets"}`;
  container.innerHTML = state.positions.length ? state.positions.map((position) => `<div class="position-row"><strong>${escapeHtml(position.ticker)}</strong><span>${number(position.quantity, 6)} units</span><button data-remove-position="${escapeHtml(position.ticker)}" aria-label="Remove ${escapeHtml(position.ticker)}">Remove</button></div>`).join("") : '<p class="muted">No positions saved. Restore the demo or add a holding.</p>';
}

function resetDemoPortfolio() {
  state.positions = DEMO_POSITIONS.map((position) => ({ ...position }));
  localStorage.removeItem("hermes-positions-v2");
  state.portfolioIsDemo = true;
  state.portfolioAnalyzed = true;
  renderPositions();
  analyzePortfolio();
}

function upsertPosition(event) {
  event.preventDefault();
  const ticker = byId("position-ticker").value.trim().toUpperCase();
  const quantity = Number(byId("position-quantity").value);
  if (!ticker || !Number.isFinite(quantity) || quantity <= 0) return;
  const existing = state.positions.find((position) => position.ticker === ticker);
  if (existing) existing.quantity = quantity;
  else state.positions.push({ ticker, quantity });
  savePositions();
  renderPositions();
  event.target.reset();
}

async function analyzePortfolio() {
  if (!state.positions.length) {
    byId("portfolio-result").innerHTML = '<div class="empty-state"><strong>Add a position first</strong><p>Restore the default demonstration portfolio or add your own browser-local holding.</p></div>';
    return;
  }
  const button = byId("analyze-portfolio");
  button.disabled = true;
  button.textContent = "Calculating…";
  byId("portfolio-result").innerHTML = '<div class="empty-state"><strong>Aligning observed closes</strong><p>Calculating allocation, historical VaR and return correlation.</p></div>';
  try {
    const result = await request("/v1/portfolio", { method: "POST", body: JSON.stringify({ positions: state.positions, confidence: 0.95 }) });
    renderPortfolio(result);
  } catch (error) {
    byId("portfolio-result").innerHTML = `<div class="empty-state"><strong>Portfolio risk unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
  } finally {
    button.disabled = false;
    button.textContent = "Calculate portfolio risk";
  }
}

const ACADEMY_GROUPS = [
  ["Market foundations", [
    ["Asset class", "A group of instruments with similar structure and risk, such as equities, bonds, commodities, currencies, or cryptoassets."],
    ["Stock / equity", "A security representing ownership in a company. Its price reflects expectations about future cash flows, risk, and supply and demand."],
    ["ETF", "An exchange-traded fund holds a basket of assets and trades like a stock. Check its holdings, fees, liquidity, and tracking difference."],
    ["Index", "A rules-based benchmark such as the S&P 500. You cannot buy an index directly; funds and derivatives provide exposure."],
    ["Market capitalization", "Share price multiplied by shares outstanding. It measures equity value, not enterprise value or cash in the bank."],
    ["Bid, ask, and spread", "The bid is the best displayed buying price, the ask the best selling price, and the spread their difference—an immediate trading cost."],
    ["Volume and liquidity", "Volume counts traded units; liquidity describes how easily size can trade without moving price. High volume does not guarantee deep liquidity."],
    ["OHLC", "Open, high, low, and close summarize a trading interval. Hermes daily models use completed bars and lag signals to avoid trading on unavailable closes."],
    ["Market order / limit order", "A market order prioritizes execution; a limit order caps the price but may not fill. Hermes simulates neither live order type."],
    ["Long, short, and cash", "Long exposure benefits from rising prices, short exposure from falling prices, and cash has no market exposure but may earn a risk-free return."],
    ["Dividend and ex-dividend date", "A dividend distributes company cash. Buyers on or after the ex-dividend date generally do not receive the declared payment."],
    ["Earnings call", "A quarterly company update covering results, guidance, and management questions. Dates and estimates can change."],
  ]],
  ["Returns, risk, and portfolio", [
    ["Simple and log return", "Simple return is the percentage price change. Log returns add through time and are common in modeling; the two differ more for large moves."],
    ["Annualization", "Scaling a daily statistic to a yearly convention. Hermes uses 252 observations for equities and 365 for continuously traded crypto."],
    ["Volatility", "The dispersion of returns, usually annualized standard deviation. It measures variability, not direction or complete downside risk."],
    ["Drawdown", "The percentage fall from a prior portfolio peak. Maximum drawdown is the worst historical peak-to-trough loss in the tested path."],
    ["Historical Value at Risk", "The historical loss threshold exceeded in a selected tail percentage. It is an estimate—not a worst-case loss."],
    ["Expected shortfall", "The average loss beyond the VaR threshold. It describes tail severity but remains dependent on the historical sample."],
    ["Beta", "Sensitivity of an asset’s returns to a benchmark. A beta of 1.2 suggests historically larger moves in the benchmark’s direction, not a guarantee."],
    ["Correlation", "A -1 to +1 measure of how returns move together. It can change abruptly and does not imply causation."],
    ["Diversification", "Combining exposures whose risks do not move identically. Diversification can reduce specific risk but cannot eliminate market-wide losses."],
    ["Annualized Sharpe ratio", "Annualized excess return divided by annualized volatility. Hermes subtracts the configured annual risk-free rate and reports a historical simulation."],
    ["Sortino ratio", "Annualized excess return divided by downside deviation. It penalizes harmful volatility rather than all volatility."],
    ["Calmar ratio", "Annualized return divided by the absolute maximum drawdown. It is highly sensitive to the chosen period."],
    ["CAGR", "Compound annual growth rate: the constant annual rate connecting starting and ending value. It hides the path and drawdowns."],
    ["Turnover", "How much the position changes through time. Greater turnover usually increases costs, slippage, and model fragility."],
  ]],
  ["Charts, indicators, and options", [
    ["Moving average / SMA", "The arithmetic mean of recent closes. It smooths noise, lags turning points, and is not predictive by itself."],
    ["RSI · Relative Strength Index", "A 0–100 momentum oscillator. Above 70 or below 30 can indicate strength or extension, not an automatic reversal."],
    ["Momentum", "The tendency for recent winners or losers to continue over a chosen horizon. Results depend strongly on horizon and regime."],
    ["Support and resistance", "Areas where prior trading created repeated demand or supply. They are zones inferred from history, not fixed barriers."],
    ["Trend regime", "A coarse description of direction or risk conditions. Hermes can use a 200-day benchmark trend as a long-exposure filter."],
    ["Option", "A contract granting a right to buy (call) or sell (put) at a strike before or at expiration. Buyers pay premium; sellers assume obligations."],
    ["Strike and expiration", "The strike is the contract exercise price; expiration is when the option ceases. Time remaining materially affects value."],
    ["Implied volatility", "The volatility consistent with an option’s market price under a pricing model. It is forward-looking pricing, not a direct forecast."],
    ["Put/call open-interest ratio", "Open put contracts divided by open call contracts in the displayed chains. Expiry and strike composition make simple sentiment readings incomplete."],
    ["Delta, gamma, theta, vega", "Core option sensitivities: price, delta change, time decay, and implied-volatility exposure. They change with price and time."],
  ]],
  ["Models and honest backtesting", [
    ["Feature and target", "A feature is information available to a model; the target is what it learns to predict. Their timestamps must be aligned without future data."],
    ["Classification probability", "An estimated chance of a defined outcome, such as a positive five-day return. A probability is only useful if discrimination and calibration hold out of sample."],
    ["Baseline model", "A simple reference a complex model must beat. Hermes uses regularized logistic regression to test whether nonlinear complexity adds value."],
    ["XGBoost", "Gradient-boosted decision trees that capture nonlinear interactions. They can be strong on tabular data but overfit small, shifting financial samples."],
    ["TimesFM", "A pretrained time-series forecasting model. General forecasting ability does not prove tradable alpha, so Hermes labels it experimental until validated here."],
    ["Training, validation, and test", "Training fits parameters, validation selects choices, and the untouched test window estimates generalization. Reusing test results invalidates the separation."],
    ["Walk-forward evaluation", "Repeatedly train on past data and score the next chronological window. This better resembles deployment than random shuffling."],
    ["Purging and embargo", "Removing overlapping label periods between splits. It prevents a future return horizon from leaking across a boundary."],
    ["Look-ahead leakage", "Any use of information that was not available at the simulated decision time. Even subtle leakage can create spectacular fake performance."],
    ["Survivorship bias", "Testing only assets that still exist today while omitting delisted failures, which can overstate historical results."],
    ["Overfitting", "Learning noise or sample-specific behavior. Warning signs include high complexity, many trials, unstable folds, and a large validation-to-test drop."],
    ["Log loss", "A probability scoring rule that heavily penalizes confident wrong predictions. Lower is better."],
    ["Brier score", "Mean squared error of predicted probabilities. Lower is better and the score reflects both calibration and discrimination."],
    ["Balanced accuracy", "Average recall across classes. It is more informative than raw accuracy when outcomes are imbalanced."],
    ["Transaction cost and slippage", "Commission is an explicit fee; slippage is the gap between intended and achieved price. Hermes applies both per unit of turnover."],
  ]],
];

function renderAcademy(query = "") {
  const needle = query.trim().toLowerCase();
  const groups = ACADEMY_GROUPS.map(([title, terms]) => [title, terms.filter(([term, definition]) => `${term} ${definition}`.toLowerCase().includes(needle))]).filter(([, terms]) => terms.length);
  byId("academy-grid").innerHTML = groups.length ? groups.map(([title, terms]) => `<section class="glass-panel academy-group"><h2>${escapeHtml(title)} <span>${terms.length}</span></h2>${terms.map(([term, definition], index) => `<details ${!needle && index === 0 ? "open" : ""}><summary>${escapeHtml(term)}</summary><p>${escapeHtml(definition)}</p></details>`).join("")}</section>`).join("") : '<div class="glass-panel feed-empty">No glossary term matches that search.</div>';
}

function renderPortfolio(result) {
  const colors = ["#60a5fa", "#22d3ee", "#fbbf24", "#4ade80", "#a78bfa", "#f87171"];
  const segments = result.holdings.map((holding, index) => `<i style="width:${Math.max(0, Number(holding.weight) * 100)}%;background:${colors[index % colors.length]}" title="${escapeHtml(holding.ticker)} ${number(Number(holding.weight) * 100, 1)}%"></i>`).join("");
  const rows = result.holdings.map((holding) => `<tr><td>${escapeHtml(holding.ticker)}</td><td>${number(holding.quantity, 6)}</td><td>${money(holding.price)}</td><td>${money(holding.value)}</td><td>${number(Number(holding.weight) * 100, 1)}%</td></tr>`).join("");
  const labels = result.correlation.labels || [];
  const heat = [`<span></span>`, ...labels.map((label) => `<span>${escapeHtml(label)}</span>`), ...(result.correlation.values || []).flatMap((row, rowIndex) => [`<span>${escapeHtml(labels[rowIndex])}</span>`, ...row.map((value) => {
    const opacity = Math.max(0.08, Math.min(0.72, Math.abs(Number(value)) * 0.72));
    const color = Number(value) >= 0 ? `rgba(96,165,250,${opacity})` : `rgba(248,113,113,${opacity})`;
    return `<span style="background:${color}">${number(value, 2)}</span>`;
  })])].join("");
  byId("portfolio-result").innerHTML = `<div class="panel-heading"><div><h2>Portfolio snapshot</h2><p>Provider-delayed valuation · derived risk</p></div><span class="data-badge derived">Derived</span></div><div class="portfolio-summary"><div><span>Observed value</span><strong>${money(result.total_value)}</strong></div><div><span>95% historical 1D VaR</span><strong>${money(result.historical_var_value)}</strong></div><div><span>VaR percent</span><strong>${percent(result.historical_var_percent, 2, false)}</strong></div></div><h2>Allocation</h2><div class="allocation-bar">${segments}</div><table class="holding-table"><thead><tr><th>Asset</th><th>Quantity</th><th>Observed price</th><th>Value</th><th>Weight</th></tr></thead><tbody>${rows}</tbody></table><h2>Return correlation</h2><div class="heatmap" style="grid-template-columns:repeat(${labels.length + 1},1fr)">${heat}</div><ul class="limitations-list">${(result.limitations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

document.querySelectorAll(".nav-button").forEach((button) => button.addEventListener("click", () => setRoute(button.dataset.route)));
byId("terminal-brand").addEventListener("click", returnToLanding);
document.querySelectorAll("[data-route-link]").forEach((button) => button.addEventListener("click", () => setRoute(button.dataset.routeLink)));
document.querySelectorAll(".subtab").forEach((button) => button.addEventListener("click", () => setAnalysisTab(button.dataset.analysisTab)));
document.querySelectorAll("[data-research-tab]").forEach((button) => button.addEventListener("click", () => setResearchTab(button.dataset.researchTab)));
document.querySelectorAll("[data-asset-class]").forEach((button) => button.addEventListener("click", () => switchAssetClass(button.dataset.assetClass)));
document.querySelectorAll("[data-open-backtester]").forEach((button) => button.addEventListener("click", () => setResearchTab("backtester")));
document.querySelectorAll("#period-picker button").forEach((button) => button.addEventListener("click", () => {
  state.period = button.dataset.period;
  document.querySelectorAll("#period-picker button").forEach((item) => item.classList.toggle("is-active", item === button));
  loadMarket();
}));
document.querySelectorAll("#chart-type-picker button").forEach((button) => button.addEventListener("click", () => {
  state.chartType = button.dataset.chartType;
  document.querySelectorAll("#chart-type-picker button").forEach((item) => item.classList.toggle("is-active", item === button));
  drawMarketChart();
}));
document.querySelectorAll("#chart-scale-picker button").forEach((button) => button.addEventListener("click", () => {
  state.chartScale = button.dataset.chartScale;
  document.querySelectorAll("#chart-scale-picker button").forEach((item) => item.classList.toggle("is-active", item === button));
  drawMarketChart();
}));
["show-sma", "show-volume", "show-rsi"].forEach((id) => byId(id).addEventListener("change", drawMarketChart));
document.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-market-ticker]");
  if (trigger) setTicker(trigger.dataset.marketTicker);
});
document.addEventListener("error", (event) => {
  if (event.target instanceof HTMLImageElement && event.target.closest(".news-item, .sidebar-news")) event.target.classList.add("is-broken");
}, true);
byId("ticker-form").addEventListener("submit", (event) => { event.preventDefault(); setTicker(byId("ticker-input").value); });
byId("market-tape").addEventListener("pointerenter", () => { tapePaused = true; });
byId("market-tape").addEventListener("pointerleave", () => { tapePaused = false; });
byId("market-tape").addEventListener("focusin", () => { tapePaused = true; });
byId("market-tape").addEventListener("focusout", () => { tapePaused = false; });
byId("tape-prev").addEventListener("click", () => nudgeTape(-360));
byId("tape-next").addEventListener("click", () => nudgeTape(360));
byId("performance-period").addEventListener("change", () => { if (state.snapshot) updateRange(state.snapshot); });
byId("toggle-about").addEventListener("click", () => {
  state.aboutExpanded = !state.aboutExpanded;
  document.querySelector(".about-asset").classList.toggle("is-expanded", state.aboutExpanded);
  byId("toggle-about").textContent = state.aboutExpanded ? "View less" : "View more";
});
byId("backtest-engine").addEventListener("change", () => {
  const isSma = byId("backtest-engine").value === "sma";
  document.querySelectorAll(".model-only").forEach((node) => { node.hidden = isSma; });
  document.querySelectorAll(".sma-only").forEach((node) => { node.hidden = !isSma; });
});
byId("apply-research-preset").addEventListener("click", applyResearchPreset);
byId("backtest-form").addEventListener("submit", runBacktest);
byId("load-options").addEventListener("click", loadOptions);
byId("run-analysis").addEventListener("click", runAnalysis);
byId("refresh-news").addEventListener("click", () => loadNewsHub(true));
byId("open-events").addEventListener("click", () => { renderEventsCalendar(state.events || { events: [] }); byId("events-dialog").showModal(); });
document.querySelectorAll("[data-events-open]").forEach((button) => button.addEventListener("click", () => { renderEventsCalendar(state.events || { events: [] }); byId("events-dialog").showModal(); }));
byId("events-dialog").addEventListener("click", (event) => { if (event.target === byId("events-dialog")) byId("events-dialog").close(); });
byId("position-form").addEventListener("submit", upsertPosition);
byId("positions-list").addEventListener("click", (event) => {
  const ticker = event.target.dataset.removePosition;
  if (!ticker) return;
  state.positions = state.positions.filter((position) => position.ticker !== ticker);
  savePositions();
  renderPositions();
});
byId("analyze-portfolio").addEventListener("click", analyzePortfolio);
byId("reset-demo-portfolio").addEventListener("click", resetDemoPortfolio);
byId("academy-search").addEventListener("input", (event) => renderAcademy(event.target.value));
window.addEventListener("hashchange", syncExperienceFromLocation);

byId("events-dialog").querySelector(".dialog-close").addEventListener("click", () => byId("events-dialog").close());
document.querySelectorAll(".version-badge, [data-product-version]").forEach((node) => { node.textContent = PRODUCT_VERSION; });
renderAcademy();
setAnalysisTab("chart");
setResearchTab("models");
updateAssetClassControls();
renderPositions();
async function initializeTerminal() {
  configureStaticDemo();
  await loadResearchProfile();
  applyResearchPreset();
  await Promise.allSettled([loadOverview(), loadHomeNews(), loadEvents()]);
  if (state.hasSelection && !state.snapshot) await loadMarket();
  if (!state.hasSelection) setHeaderState("warn", "Choose asset");
}

function ensureTerminalInitialized() {
  if (!terminalInitialization) terminalInitialization = initializeTerminal();
  return terminalInitialization;
}

initializeLanding();
syncExperienceFromLocation();

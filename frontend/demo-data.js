export const STATIC_DEMO = location.hostname.endsWith(".github.io") || new URLSearchParams(location.search).get("demo") === "1";

let snapshotPromise = null;

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

async function loadSnapshot() {
  if (!snapshotPromise) {
    const url = new URL("./demo/snapshot.json", import.meta.url);
    snapshotPromise = fetch(url).then(async (response) => {
      if (!response.ok) throw new Error(`Frozen demo snapshot failed to load (${response.status}).`);
      return response.json();
    });
  }
  return snapshotPromise;
}

function unavailable(message) {
  throw new Error(`${message} The GitHub Pages build is an explicitly frozen interface demo; run Hermes locally for live requests.`);
}

function defaultPortfolio(body) {
  try {
    const positions = JSON.parse(body || "{}").positions || [];
    const expected = ["AAPL:12", "MSFT:8", "SPY:10", "NVDA:6"];
    return positions.map((item) => `${String(item.ticker).toUpperCase()}:${Number(item.quantity)}`).join("|") === expected.join("|");
  } catch {
    return false;
  }
}

export async function demoRequest(path, options = {}) {
  const snapshot = await loadSnapshot();
  const url = new URL(path, "https://hermes.demo");
  const segments = url.pathname.split("/").filter(Boolean);

  if (url.pathname === "/v1/market-overview") {
    return clone(snapshot.market_overview[url.searchParams.get("asset_class") || "equity"]);
  }
  if (segments[0] === "v1" && segments[1] === "research-profile") {
    return clone(snapshot.research_profile[decodeURIComponent(segments[2] || "equity")]);
  }
  if (segments[0] === "v1" && segments[1] === "terminal") {
    const ticker = decodeURIComponent(segments.slice(2).join("/")).toUpperCase();
    const result = snapshot.terminal[ticker];
    if (!result) unavailable(`No captured terminal snapshot is bundled for ${ticker}.`);
    return clone(result);
  }
  if (segments[0] === "v1" && segments[1] === "news") {
    const ticker = decodeURIComponent(segments.slice(2).join("/")).toUpperCase();
    const result = snapshot.news[ticker];
    if (!result) unavailable(`No captured headline set is bundled for ${ticker}.`);
    return clone(result);
  }
  if (segments[0] === "v1" && segments[1] === "events") {
    const ticker = decodeURIComponent(segments.slice(2).join("/")).toUpperCase();
    const fallback = ticker.endsWith("-USD") ? snapshot.events["BTC-USD"] : snapshot.events.SPY;
    return clone(snapshot.events[ticker] || fallback);
  }
  if (url.pathname === "/v1/portfolio") {
    if (!defaultPortfolio(options.body)) unavailable("Portfolio recalculation is available only for the bundled demonstration holdings.");
    return clone(snapshot.portfolio);
  }
  if (url.pathname === "/v1/backtests") return clone(snapshot.backtest);
  if (url.pathname === "/v1/options") unavailable("Listed-options snapshots are not bundled.");
  if (segments[0] === "v1" && segments[1] === "options") unavailable("Listed-options snapshots are not bundled.");
  if (url.pathname === "/v1/analysis") unavailable("Generated committee analysis requires the optional local Ollama service.");
  unavailable(`No frozen response is bundled for ${url.pathname}.`);
}

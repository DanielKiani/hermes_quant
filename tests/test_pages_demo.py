import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_static_demo_snapshot_is_explicitly_frozen() -> None:
    snapshot = json.loads((ROOT / "frontend" / "demo" / "snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["demo"]["mode"] == "frozen"
    assert snapshot["demo"]["captured_at"]
    assert snapshot["market_overview"]["equity"]["tape"]
    assert snapshot["market_overview"]["crypto"]["tape"]
    assert snapshot["terminal"]["AAPL"]["history"]
    assert snapshot["terminal"]["BTC-USD"]["history"]
    assert snapshot["portfolio"]["classification"] == "derived"
    assert snapshot["backtest"]["classification"] == "simulated"


def test_pages_runtime_uses_project_relative_assets() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "demo-data.js").read_text(encoding="utf-8")
    assert 'src="./media/' in html
    assert 'href="./styles.css"' in html
    assert 'src="./app.js"' in html
    assert 'url("./media/' in styles
    assert 'new URL("./demo/snapshot.json", import.meta.url)' in script
    assert '.github.io' in script
    assert 'mode": "frozen"' not in script  # Snapshot state lives in data, not an implied live runtime.


def test_static_demo_keeps_server_only_controls_locked_after_asset_render() -> None:
    app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'optionsButton.disabled = STATIC_DEMO || state.assetClass === "crypto";' in app
    assert 'button.disabled = STATIC_DEMO || state.assetClass === "crypto";' in app
    assert 'byId("run-analysis").disabled = true;' in app


def test_pages_workflow_builds_and_deploys_only_the_site_artifact() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    build_script = (ROOT / "scripts" / "build_pages.py").read_text(encoding="utf-8")
    assert "python scripts/build_pages.py" in workflow
    assert "actions/configure-pages@v5" in workflow
    assert "actions/upload-pages-artifact@v4" in workflow
    assert "actions/deploy-pages@v4" in workflow
    assert "path: _site" in workflow
    assert 'OUTPUT = ROOT / "_site"' in build_script
    assert 'OUTPUT / ".nojekyll"' in build_script

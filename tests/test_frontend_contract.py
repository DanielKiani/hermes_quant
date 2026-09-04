from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_frontend_has_truthful_state_vocabulary() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for label in ("Observed", "Derived", "Predicted", "Simulated", "Unavailable"):
        assert label.lower() in html.lower()
    assert "not a broker" in html.lower()
    assert "Research Lab" in html
    assert "Strategy Backtester" in html
    assert "AI Committee" in html
    assert 'data-asset-class="equity"' in html
    assert 'data-asset-class="crypto"' in html
    assert 'id="home-view" class="view is-active"' in html
    assert "Upcoming Market Calendar" in html
    assert "v0.6-Beta" in html
    assert "https://x.com/DanielKiani78" in html
    assert "https://github.com/danielkiani" in html
    assert "mailto:danialdatak@gmail.com" in html
    assert "This application is a simulated environment for research and portfolio purposes only." in html


def test_frontend_calls_api_instead_of_embedding_market_values() -> None:
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'const API = "/api"' in script
    assert "/v1/terminal/" in script
    assert "/v1/market-overview" in script
    assert "/v1/research-profile/" in script
    assert "/v1/options/" in script
    assert "/v1/news/" in script
    assert "/v1/events/" in script
    assert "/v1/portfolio" in script
    assert "/v1/backtests" in script
    assert "Math.random" not in script


def test_frontend_uses_constellation_background_and_exact_value_charts() -> None:
    styles = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'url("./media/bg_constellation.jpg")' in styles
    assert "attachChartTooltip" in script
    assert "Strategy growth of $1" in script
    assert "Validation-selected" in (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def test_frontend_exposes_requested_market_and_learning_surfaces() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    for mover in ("movers-trending", "movers-gainers", "movers-losers"):
        assert f'id="{mover}"' in html
    assert "DEMO_POSITIONS" in script
    assert "Annualized Sharpe (excess return)" in script
    assert "Bullish thesis" in script
    assert "Bearish thesis" in script
    assert "ACADEMY_GROUPS" in script
    assert "startTapeMotion" in script
    assert "tapeScrollPosition" in script
    assert "sparkline-area" in script


def test_nginx_preserves_spa_routes_and_proxies_api() -> None:
    config = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "proxy_pass http://api:8000" in config
    assert "try_files $uri $uri/ /index.html" in config


def test_frontend_has_cinematic_landing_and_terminal_handoff() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    for scene in ("hero", "signal", "validation", "committee", "portfolio", "gateway"):
        assert f'data-landing-target="{scene}"' in html
        assert f'data-landing-scene="{scene}"' in html
    assert "landing_hero_mobile.png" in html
    assert "hermes_logo.png" in html
    assert "dashboard.png" in html
    assert "backtester_engine.png" in html
    assert "multiagent_ai_synth.png" in html
    assert "portfolio.png" in html
    assert "syncExperienceFromLocation" in script
    assert "ensureTerminalInitialized" in script
    assert 'id="terminal-brand"' in html
    assert 'data-route="home">Home</button>' in html
    assert "returnToLanding" in script
    assert 'history.pushState(null, "", `${location.pathname}${location.search}`)' in script
    assert ".landing-stage {" in styles
    assert "position: sticky" in styles

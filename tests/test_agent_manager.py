from src.agent_manager import TradingAgentManager


def test_committee_preserves_quant_and_headline_evidence(monkeypatch) -> None:
    manager = TradingAgentManager(host="http://unused", model="test-model")
    monkeypatch.setattr(manager, "_get_basic_context", lambda _ticker: "observed context")
    monkeypatch.setattr(
        manager,
        "_get_ml_context",
        lambda _ticker, _model: ("validated probability", "follow the baseline"),
    )
    monkeypatch.setattr(manager, "_get_news_context", lambda _ticker: "- source headline")

    def fake_query(_prompt: str, role: str) -> str:
        if "long-biased" in role:
            return "upside case"
        if "skeptical" in role:
            return "downside case"
        return "OVERRIDE: NO\nSYNTHESIS: follows evidence\nFINAL DECISION: HOLD"

    monkeypatch.setattr(manager, "_query_ollama", fake_query)
    report = manager.analyze_stock("AAPL", "XGBoost")

    assert report["quant"]["summary"] == "validated probability"
    assert report["bull"] == "upside case"
    assert report["bear"] == "downside case"
    assert report["news"] == "- source headline"
    assert "FINAL DECISION: HOLD" in report["pm"]

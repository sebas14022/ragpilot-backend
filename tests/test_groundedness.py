from app.groundedness import classify_groundedness, groundedness_from_score


class _Settings:
    grounded_high = 0.72
    grounded_medium = 0.48
    groundedness_llm_fallback = True
    gemini_model = "gemini-3.6-flash"


def _settings():
    return _Settings()


def test_groundedness_from_score_thresholds(monkeypatch):
    monkeypatch.setattr("app.groundedness.get_settings", lambda: _settings())
    assert groundedness_from_score(0.90) == "High"
    assert groundedness_from_score(0.75) == "High"
    assert groundedness_from_score(0.55) == "Medium"
    assert groundedness_from_score(0.30) == "Low"


def test_classify_trusts_high_and_low_without_llm(monkeypatch):
    monkeypatch.setattr("app.groundedness.get_settings", lambda: _settings())
    monkeypatch.setattr("app.groundedness._llm_groundedness_check", lambda **k: "Medium")

    assert classify_groundedness(0.90, answer="a", context=["ctx"], question="q") == "High"
    assert classify_groundedness(0.10, answer="a", context=["ctx"], question="q") == "Low"


def test_classify_ambiguous_runs_llm(monkeypatch):
    monkeypatch.setattr("app.groundedness.get_settings", lambda: _settings())
    calls = {}

    def fake_llm(**kwargs):
        calls["ran"] = True
        return "Medium"

    monkeypatch.setattr("app.groundedness._llm_groundedness_check", fake_llm)
    assert classify_groundedness(0.55, answer="a", context=["ctx"], question="q") == "Medium"
    assert calls.get("ran") is True


def test_classify_fallback_disabled(monkeypatch):
    settings = _settings()
    settings.groundedness_llm_fallback = False

    def get():
        return settings

    monkeypatch.setattr("app.groundedness.get_settings", get)
    monkeypatch.setattr("app.groundedness._llm_groundedness_check", lambda **k: "Low")
    # Ambiguous band; fallback disabled -> heuristic 'Medium'.
    assert classify_groundedness(0.55, answer="a", context=["ctx"], question="q") == "Medium"


def test_no_context_is_low(monkeypatch):
    monkeypatch.setattr("app.groundedness.get_settings", lambda: _settings())
    assert classify_groundedness(None, answer="a", context=[], question="q") == "Low"


def test_baseline_without_retrieval_is_judged_by_content(monkeypatch):
    """Regression: the full-document branch has no similarity score.

    It used to short-circuit to "Low" for every single comparison, which made
    the RAG side look better by construction rather than on merit.
    """
    monkeypatch.setattr("app.groundedness.get_settings", lambda: _settings())
    monkeypatch.setattr("app.groundedness._llm_groundedness_check", lambda **k: "High")

    assert classify_groundedness(None, answer="a", context=["full doc"], question="q") == "High"


def test_baseline_without_llm_fallback_is_neutral(monkeypatch):
    settings = _settings()
    settings.groundedness_llm_fallback = False
    monkeypatch.setattr("app.groundedness.get_settings", lambda: settings)

    # Undecidable without the judge: "Medium" is the honest placeholder, not a
    # free win for the RAG branch.
    assert classify_groundedness(None, answer="a", context=["full doc"], question="q") == "Medium"

"""Tests for the prompt contracts and the answer post-processing guards."""

from __future__ import annotations

from app.completion import Completion, build_messages, complete, strip_foreign_citations


def test_rag_mode_numbers_passages_and_teaches_citation():
    system, user = build_messages("What is X?", ["first chunk", "second chunk"])

    assert "[1] first chunk" in user
    assert "[2] second chunk" in user
    assert "[1]" in system
    assert "What is X?" in user


def test_full_document_mode_never_numbers_the_corpus():
    system, user = build_messages(
        "What is X?", ["--- a.md ---\nbody"], mode="full-document"
    )

    # Numbering a single stuffed blob is what made the model invent line ranges.
    assert "[1]" not in user
    assert "--- a.md ---" in user
    assert "never" in system
    assert "citation markers" in system


def test_prompts_ask_for_the_established_behaviour_not_a_blind_refusal():
    """Regression: RAG used to abstain on questions answered implicitly.

    The retention passage states an immediate purge and no retroactive window;
    asked "how many days of grace?", a blind "say so plainly" rule made the
    model answer "not specified" instead of "no grace period applies".
    """
    rag_system, _ = build_messages("q", ["passage"])
    full_system, _ = build_messages("q", ["doc"], mode="full-document")

    for system in (rag_system, full_system):
        assert "does not apply" in system
        assert "instead of calling it unspecified" in system


def test_strip_foreign_citations_drops_cms_markers():
    raw = "The grace period is 90 days 【1†L71-L74】."

    assert strip_foreign_citations(raw) == "The grace period is 90 days."


def test_strip_foreign_citations_keeps_legitimate_rag_markers():
    assert strip_foreign_citations("Revenue grew 20% [1].") == "Revenue grew 20% [1]."


class _Settings:
    groq_api_key = ""  # force the Gemini path
    gemini_model = "gemini-test"


def test_complete_sanitises_answers_from_every_branch(monkeypatch):
    monkeypatch.setattr("app.completion.get_settings", lambda: _Settings())
    monkeypatch.setattr(
        "app.completion._call_gemini",
        lambda system, user: ("Supported 【9†L1-L3】 [1]", 12, "gemini-test"),
    )

    stuffed = complete("q", ["--- a.md ---\nbody"], mode="full-document")
    rag = complete("q", ["body"], mode="rag")

    assert isinstance(stuffed, Completion)
    # The invented marker goes; the passage reference the model added stays.
    assert stuffed.answer == "Supported [1]"
    assert rag.answer == "Supported [1]"
    assert stuffed.tokens_used == 12
    assert stuffed.model == "gemini-test"

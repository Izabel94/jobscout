"""LLM-driven Upwork screener-question answering.

Upwork lets clients add per-listing screener questions on top of the cover
letter ("describe your recent experience with similar projects", etc.).
These come in via `<textarea>` elements on the apply form whose nearby
label carries the question text.

This module takes the questions + the application context (cover letter,
adapted CV, listing) and produces one tailored answer per question via
the configured LLM provider.
"""

from __future__ import annotations

from pathlib import Path

from jobscout.config_loader import load_profile
from jobscout.llm import LLMJSONError, call_json

_MODEL_DRAFT = "gemini-2.5-flash"  # spec decision
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"
_PROMPT_SCREENER = (_PROMPTS_DIR / "screener.v1.md").read_text(encoding="utf-8")


def answer_questions(
    *,
    questions: list[str],
    listing_title: str,
    listing_description: str,
    cover_letter: str,
    adapted_cv: str,
) -> list[str]:
    """Generate answers for each screener question, in order.

    Returns a list of strings, one per input question. Raises LLMJSONError
    if the model returns malformed JSON or wrong-shaped output — the caller
    should fall back to letting the user fill the textareas manually.
    """
    if not questions:
        return []
    profile = load_profile()
    numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    rendered = (
        _PROMPT_SCREENER.replace("{{candidate_name}}", str(profile.get("full_name") or ""))
        .replace("{{listing_title}}", listing_title)
        .replace("{{listing_description}}", (listing_description or "")[:4000])
        .replace("{{cover_letter}}", cover_letter)
        .replace("{{adapted_cv}}", adapted_cv)
        .replace("{{numbered_questions}}", numbered)
    )
    result = call_json(
        model=_MODEL_DRAFT,
        system="You answer Upwork screener questions concisely and specifically.",
        user=rendered,
        max_tokens=1500,
    )
    answers = result.get("answers")
    if not isinstance(answers, list) or len(answers) != len(questions):
        raise LLMJSONError(
            f"expected {len(questions)} answers, got {answers!r}",
        )
    return [str(a) for a in answers]

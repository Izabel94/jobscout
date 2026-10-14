"""Score stage of the daily pipeline: applies the LLM scorer to status='new' listings."""

import logging
from pathlib import Path

from jobscout.config_loader import load_profile, render_candidate_block
from jobscout.db import list_unscored_new_listings, update_listing_status
from jobscout.llm import LLMJSONError, call_json
from jobscout.models import Listing, ListingStatus

log = logging.getLogger("score")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_MODEL_SCORE = "gemini-3.1-flash-lite"  # spec §10 decision
_MODEL_SCORE_FALLBACK = "gemini-2.5-flash"  # route around flash-lite 503 'high demand' spikes
_PROMPT = (Path(__file__).resolve().parent.parent / "config" / "prompts" / "score.v1.md").read_text()


def _build_score_prompt(profile: dict, listing: dict) -> str:
    """Render the score prompt with the candidate sourced from the profiles row.

    profile.scorer_notes (free-text from the Settings tab) is rendered as a
    'User preferences' header so the LLM sees it before the listing. Empty /
    missing notes => no header rendered.
    """
    notes = (profile.get("scorer_notes") or "").strip()
    user_pref_block = ""
    if notes:
        user_pref_block = "# User preferences (mandatory — apply as a hard filter)\n\n" f"{notes}\n\n"
    return (
        _PROMPT.replace("{{candidate_block}}", render_candidate_block(profile))
        .replace("{{user_pref_block}}", user_pref_block)
        .replace("{{title}}", listing.get("title", "") or "")
        .replace("{{description}}", (listing.get("description") or "")[:3000])
        .replace("{{rate_min}}", str(listing.get("rate_min") or ""))
        .replace("{{rate_max}}", str(listing.get("rate_max") or ""))
        .replace("{{currency}}", listing.get("currency") or "")
        .replace("{{rate_unit}}", listing.get("rate_unit") or "")
        .replace("{{hours_per_week}}", str(listing.get("hours_per_week") or ""))
        .replace("{{language}}", listing.get("language") or "")
        .replace("{{posted_at}}", str(listing.get("posted_at") or ""))
    )


def main() -> None:
    profile = load_profile()
    rows = list_unscored_new_listings()
    log.info("scoring %d listings with %s", len(rows), _MODEL_SCORE)
    for row in rows:
        listing = Listing.model_validate(row)
        listing_id = str(row["id"])
        try:
            out = call_json(
                model=_MODEL_SCORE,
                fallback_model=_MODEL_SCORE_FALLBACK,
                system="You output JSON only.",
                user=_build_score_prompt(profile, listing.model_dump(mode="json")),
                max_tokens=2000,
            )
            score = int(out["score"])
            rationale = str(out.get("rationale", ""))
            red_flags = out.get("red_flags") or []
            if any("agency" in str(flag).lower() for flag in red_flags):
                update_listing_status(listing_id, ListingStatus.REJECTED, score=score, score_rationale=rationale)
                log.info("rejected agency listing %s (LLM-judged)", listing_id)
                continue
            update_listing_status(listing_id, ListingStatus.SCORED, score=score, score_rationale=rationale)
        except (LLMJSONError, KeyError, ValueError) as e:
            log.error("score failed for %s: %s", listing_id, e)


if __name__ == "__main__":
    main()

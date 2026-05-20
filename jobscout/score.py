"""Score stage of the daily pipeline: applies the LLM scorer to status='new' listings."""

import logging
from pathlib import Path

from jobscout.config_loader import load_profile
from jobscout.db import list_unscored_new_listings, update_listing_status
from jobscout.llm import LLMJSONError, call_json
from jobscout.models import Listing, ListingStatus

log = logging.getLogger("score")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_PROMPT = (Path(__file__).resolve().parent.parent / "config" / "prompts" / "score.v1.md").read_text()


def _render(template: str, listing: Listing) -> str:
    return (
        template.replace("{{title}}", listing.title)
        .replace("{{description}}", (listing.description or "")[:3000])
        .replace("{{rate_min}}", str(listing.rate_min or ""))
        .replace("{{rate_max}}", str(listing.rate_max or ""))
        .replace("{{currency}}", listing.currency or "")
        .replace("{{rate_unit}}", listing.rate_unit.value if listing.rate_unit else "")
        .replace("{{hours_per_week}}", str(listing.hours_per_week or ""))
        .replace("{{language}}", listing.language or "")
        .replace("{{posted_at}}", str(listing.posted_at or ""))
    )


def main() -> None:
    profile = load_profile()
    model = profile["model_score"]
    rows = list_unscored_new_listings()
    log.info("scoring %d listings with %s", len(rows), model)
    for row in rows:
        listing = Listing.model_validate(row)
        listing_id = str(row["id"])
        try:
            out = call_json(
                model=model,
                system="You output JSON only.",
                user=_render(_PROMPT, listing),
                max_tokens=400,
            )
            update_listing_status(
                listing_id,
                ListingStatus.SCORED,
                score=int(out["score"]),
                score_rationale=str(out.get("rationale", "")),
            )
        except (LLMJSONError, KeyError, ValueError) as e:
            log.error("score failed for %s: %s", listing_id, e)


if __name__ == "__main__":
    main()

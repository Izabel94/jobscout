"""Hard filters and spam scoring for listings."""

import hashlib
import re

from jobscout.config_loader import load_profile, load_spam_rules
from jobscout.models import Arrangement, JobType, Listing, RateUnit

_EMBEDDING_THRESHOLD = 0.30  # spec decision

HIGH_CONFIDENCE_ONSITE_EVIDENCE = (
    "5 days",
    "5 tage",
    "100% on-site",
    "100% vor ort",
    "fully on-site",
    "vollständig vor ort",
    "no remote",
    "nicht remote",
)


def pass_structural(listing: Listing) -> bool:
    """Drop part-time/contract/intern. Drop high-confidence on-site. Keep everything else."""

    if listing.job_type_classified in (JobType.CONTRACT, JobType.PARTTIME, JobType.INTERN):
        return False

    if listing.arrangement == Arrangement.ONSITE:
        ev = (listing.arrangement_evidence or "").lower()
        if any(marker in ev for marker in HIGH_CONFIDENCE_ONSITE_EVIDENCE):
            return False

    return True


def has_hard_drop_pattern(listing: Listing) -> bool:
    rules = load_spam_rules()
    text = f"{listing.title}\n{listing.description or ''}"
    for group in ("upfront_fee", "unpaid_trial", "elaborate_application"):
        for pat in rules["hard_drop_patterns"].get(group, []):
            if re.search(pat, text, re.I):
                return True
    if any(re.search(kw, text, re.I) for kw in rules["mlm_keywords"]):
        return True
    return any(re.search(rf"\b{re.escape(company)}\b", text, re.I) for company in rules["mlm_companies"])


def _has_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def _matches_named_stack(text: str, tokens: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(t)}\b", text, re.I) for t in tokens)


def spam_score(listing: Listing) -> int:
    rules = load_spam_rules()
    weights = rules["spam_score_weights"]
    positive = rules["positive_signal_weights"]
    text = f"{listing.title}\n{listing.description or ''}"
    score = 0

    if _has_any(text, rules["scope_heavy_keywords"]) and (
        (listing.rate_unit == RateUnit.FIXED and listing.rate_max and listing.rate_max < rules["b1_min_fixed_eur"])
        or (listing.rate_unit == RateUnit.HOUR and listing.rate_max and listing.rate_max < rules["b1_min_hourly_eur"])
    ):
        score += weights["rate_vs_scope_mismatch"]

    has_ai = bool(re.search(r"\b(ai|ml|llm|chatgpt)\b", text, re.I))
    description_text = listing.description or ""
    has_real_stack = _matches_named_stack(description_text, rules["named_stack_tokens"])
    has_rpa = _has_any(text, rules["non_ai_stack_keywords"])
    if has_ai and not has_real_stack and has_rpa:
        score += weights["ai_claim_with_rpa_stack"]

    word_count = len((listing.description or "").split())
    if word_count < 80 and not has_real_stack:
        score += weights["short_listing_no_concrete"]

    if sum(1 for p in rules["autotranslation_patterns"] if re.search(p, text, re.I)) >= 2:
        score += weights["autotranslation_artifacts"]

    letters = sum(c.isalpha() for c in listing.title)
    caps = sum(c.isupper() for c in listing.title)
    if letters and caps / letters > 0.30:
        score += weights["excessive_caps_emoji"]

    if _has_any(text, rules["lowest_bidder_patterns"]):
        score += weights["lowest_bidder_language"]

    if has_real_stack:
        score += positive["named_tech_stack"]
    if re.search(r"linkedin\.com/in/[\w-]{3,}", text, re.I):
        score += positive["named_contact_linkedin"]
    if re.search(r"\bp95\b|\bhit@\d+\b|\bacceptance criteria\b|\bSLA\b|evaluations? set", text, re.I):
        score += positive["named_deliverables"]

    return score


def listing_hash(listing: Listing) -> str:
    return hashlib.sha1(((listing.description or "")[:500]).encode("utf-8")).hexdigest()


def _norm(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def _company(listing: Listing) -> str:
    raw = listing.raw or {}
    return str(raw.get("company") or "") if isinstance(raw, dict) else ""


def duplicate_ids(listings: list[Listing]) -> list[str]:
    """Ids to reject so each (title, company) keeps one row. Indeed re-scrapes
    the same posting under different source_ids across runs, slipping past the
    (source, source_id) constraint. Keep the richest copy (longest description,
    then earliest discovered); reject the rest. Rows missing a title or company
    are never grouped."""
    groups: dict[tuple[str, str], list[Listing]] = {}
    for listing in listings:
        key = (_norm(listing.title), _norm(_company(listing)))
        if not key[0] or not key[1]:
            continue
        groups.setdefault(key, []).append(listing)
    reject: list[str] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda listing: (-len(listing.description or ""), listing.discovered_at))
        reject.extend(str(listing.id) for listing in group[1:] if listing.id)
    return reject


def pass_skill_match(listing: Listing) -> bool:
    profile = load_profile()
    text = f"{listing.title}\n{listing.description or ''}".lower()
    return any(kw.lower() in text for kw in profile["required_skill_keywords"])


def pass_title_denylist(listing: Listing) -> bool:
    profile = load_profile()
    title = listing.title.lower()
    return not any(deny.lower() in title for deny in profile["title_denylist"])


def pass_embedding(listing: Listing) -> bool:
    from jobscout.embeddings import cosine_to_profile

    text = f"{listing.title}\n{listing.description or ''}"[:2048]
    return cosine_to_profile(text) >= _EMBEDDING_THRESHOLD

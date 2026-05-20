"""Hard filters and spam scoring for listings."""

import hashlib
import re
from decimal import Decimal

from jobscout.config_loader import load_profile, load_spam_rules
from jobscout.models import Listing, RateUnit, Source

# Cross-source full-time markers (EN + DE). "unbefristet" = indefinite-term,
# the German FTE marker employers use to avoid the word "Festanstellung".
_FULLTIME_LITERAL_RE = re.compile(
    r"full[- ]?time|fulltime|vollzeit|festanstellung|unbefristet|permanent (?:position|role|employment)",
    re.I,
)

# Workload statement with explicit /week qualifier. "24 hours" alone (e.g. an SLA) does NOT match.
_HOURS_PER_WEEK_RE = re.compile(
    r"\b(\d{1,3})(?:\s*(?:-|–|to|bis)\s*(\d{1,3}))?"  # noqa: RUF001 — EN DASH appears in real listings
    r"\s*(?:h|hours?|hrs?|std)\b"
    r"[\s/-]*(?:per|pro)?\s*(?:week|wk|woche)\b",
    re.I,
)

# LinkedIn descriptions rarely say "full-time" literally — gate on JobSpy's `job_type` field instead.
_ACCEPTED_LINKEDIN_JOB_TYPES = frozenset({"contract", "parttime", "temporary"})

# Freelancermap "X% Auslastung" = utilization. "100%" ≈ full-time, "50%" ≈ 20h/week.
# Two formats: "100% Auslastung" (badge) and "Auslastung: 80-100 %" (labeled field).
_AUSLASTUNG_RE = re.compile(
    r"(?:(\d{1,3})\s*%\s*Auslastung|Auslastung[:\s]+(\d{1,3})\s*(?:[-–]\s*\d{1,3}\s*)?%)",  # noqa: RUF001
    re.I,
)
_AUSLASTUNG_REFERENCE_HOURS = 40


def pass_structural(listing: Listing) -> bool:
    profile = load_profile()
    if listing.remote is False:
        return False
    # LinkedIn-specific: drop RLHF/data-labeling gig marketplaces (Alignerr, Outlier, etc.)
    # that post under engineering titles but route to a generic data-trainer onboarding form.
    if listing.source == Source.LINKEDIN:
        from jobscout.sources.linkedin import is_company_denylisted

        company = (listing.raw or {}).get("company")
        if is_company_denylisted(company):
            return False
    if listing.rate_max is not None and listing.rate_unit in (RateUnit.HOUR, None):
        if listing.currency == "USD":
            if listing.rate_max < Decimal(profile["target_rate_floor_usd_hr"]):
                return False
        else:
            if listing.rate_max < Decimal(profile["target_rate_floor_eur_hr"]):
                return False
    max_hours = Decimal(profile["max_hours_per_week"])
    if listing.hours_per_week is not None and listing.hours_per_week > max_hours:
        return False
    text = f"{listing.title}\n{listing.description or ''}"
    if _FULLTIME_LITERAL_RE.search(text):
        return False
    # The binding constraint across multiple "X hrs/week" mentions is the MINIMUM commitment.
    low_ends = [Decimal(m.group(1)) for m in _HOURS_PER_WEEK_RE.finditer(text)]
    if low_ends and min(low_ends) > max_hours:
        return False
    auslastung_pcts = []
    for m in _AUSLASTUNG_RE.finditer(text):
        pct_str = m.group(1) or m.group(2)
        if pct_str:
            auslastung_pcts.append(int(pct_str))
    if auslastung_pcts:
        implied_hours = Decimal(min(auslastung_pcts) * _AUSLASTUNG_REFERENCE_HOURS) / Decimal(100)
        if implied_hours > max_hours:
            return False
    job_type = listing.raw.get("job_type") if isinstance(listing.raw, dict) else None
    if isinstance(job_type, str) and job_type.lower() not in _ACCEPTED_LINKEDIN_JOB_TYPES:
        return False
    return not (listing.language and listing.language not in profile["languages_accepted"])


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

    profile = load_profile()
    threshold = float(profile["embedding_threshold"])
    text = f"{listing.title}\n{listing.description or ''}"[:2048]
    return cosine_to_profile(text) >= threshold

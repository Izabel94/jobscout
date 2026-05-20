from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Source(StrEnum):
    UPWORK = "upwork"
    BUNDESAGENTUR = "bundesagentur"
    FREELANCERMAP = "freelancermap"
    LINKEDIN = "linkedin"


class ListingStatus(StrEnum):
    NEW = "new"
    SCORED = "scored"
    DRAFTED = "drafted"
    COPIED = "copied"
    SUBMITTED = "submitted"
    REJECTED = "rejected"
    WON = "won"
    EXPIRED = "expired"


class RateUnit(StrEnum):
    HOUR = "hour"
    DAY = "day"
    FIXED = "fixed"
    SALARY = "salary"
    UNKNOWN = "unknown"


class Listing(BaseModel):
    id: str | None = None
    source: Source
    source_id: str
    url: str
    title: str
    description: str | None = None
    location: str | None = None
    remote: bool | None = None
    language: str | None = None
    rate_min: Decimal | None = None
    rate_max: Decimal | None = None
    rate_unit: RateUnit | None = None
    currency: str | None = None
    hours_per_week: Decimal | None = None
    duration_weeks: Decimal | None = None
    posted_at: datetime | None = None
    discovered_at: datetime = Field(default_factory=datetime.now)
    raw: dict[str, Any]
    score: int | None = Field(default=None, ge=0, le=100)
    score_rationale: str | None = None
    spam_score: int | None = None
    status: ListingStatus = ListingStatus.NEW


class Draft(BaseModel):
    id: str | None = None
    listing_id: str
    language: str
    subject: str | None = None
    body: str
    adapted_cv: str | None = None
    model: str
    prompt_version: str

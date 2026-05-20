from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Source(StrEnum):
    LINKEDIN = "linkedin"
    INDEED = "indeed"


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


class Arrangement(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class JobType(StrEnum):
    FULLTIME = "fulltime"
    PERMANENT = "permanent"
    CONTRACT = "contract"
    PARTTIME = "parttime"
    INTERN = "intern"
    UNKNOWN = "unknown"


class ApplyMethod(StrEnum):
    EXTERNAL_APPLY = "external_apply"
    EASY_APPLY = "easy_apply"


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
    arrangement: Arrangement | None = None
    arrangement_evidence: str | None = None
    job_type_classified: JobType | None = None
    job_type_evidence: str | None = None
    apply_method: ApplyMethod | None = None


class Draft(BaseModel):
    id: str | None = None
    listing_id: str
    language: str
    subject: str | None = None
    body: str
    adapted_cv: str | None = None
    model: str
    prompt_version: str

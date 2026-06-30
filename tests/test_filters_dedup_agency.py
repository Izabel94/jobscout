from __future__ import annotations

from datetime import datetime

from jobscout.filters import duplicate_ids
from jobscout.models import Listing, Source


def _listing(
    *, lid: str, title: str, company: str | None, source: Source = Source.INDEED,
    source_id: str = "x", description: str = "", discovered: str = "2026-06-01T00:00:00+00:00",
) -> Listing:
    return Listing(
        id=lid,
        source=source,
        source_id=source_id,
        url=f"https://example.com/{source_id}",
        title=title,
        description=description,
        discovered_at=datetime.fromisoformat(discovered),
        raw={"company": company} if company is not None else {},
    )


def test_duplicate_ids_collapses_same_title_company_across_source_ids():
    a = _listing(lid="a", title="Marketing Manager (m/w/d)", company="Volkswagen", source_id="1", description="x" * 50)
    b = _listing(lid="b", title="Marketing Manager (m/w/d)", company="Volkswagen", source_id="2", description="x" * 10)
    c = _listing(lid="c", title="Marketing Manager (m/w/d)", company="volkswagen ", source_id="3", description="x" * 5)
    # Keeps the longest description (a); rejects the other two.
    assert set(duplicate_ids([a, b, c])) == {"b", "c"}


def test_duplicate_ids_tiebreaks_on_earliest_discovered():
    early = _listing(lid="early", title="X", company="Y", source_id="1",
                     description="same", discovered="2026-06-01T00:00:00+00:00")
    late = _listing(lid="late", title="X", company="Y", source_id="2",
                    description="same", discovered="2026-06-05T00:00:00+00:00")
    assert duplicate_ids([early, late]) == ["late"]


def test_duplicate_ids_keeps_distinct_and_ignores_blank_keys():
    a = _listing(lid="a", title="Role A", company="Acme")
    b = _listing(lid="b", title="Role B", company="Acme")
    nocompany = _listing(lid="n", title="Role A", company=None)
    assert duplicate_ids([a, b, nocompany]) == []

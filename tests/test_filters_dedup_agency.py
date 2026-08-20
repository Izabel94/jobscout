from __future__ import annotations

from datetime import datetime

import pytest

from jobscout.filters import duplicate_ids, is_media_agency, media_agency_ids
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


def test_is_media_agency_denylist_and_keywords():
    assert is_media_agency(_listing(lid="1", title="T", company="Cordes Consulting"))
    assert is_media_agency(_listing(lid="2", title="T", company="Publicis Media Germany"))
    assert is_media_agency(_listing(lid="3", title="T", company="Remazing Nova"))
    assert is_media_agency(_listing(lid="4", title="T", company="Müller Werbeagentur GmbH"))
    assert is_media_agency(_listing(lid="5", title="T", company="Acme Digital Agency"))


def test_is_media_agency_keeps_inhouse_and_blank():
    assert not is_media_agency(_listing(lid="1", title="T", company="Volkswagen"))
    assert not is_media_agency(_listing(lid="2", title="T", company="adjoe"))
    assert not is_media_agency(_listing(lid="3", title="T", company=None))


def test_media_agency_ids_filters_list():
    agency = _listing(lid="a", title="T", company="Zenith Deutschland")
    inhouse = _listing(lid="b", title="T", company="Tchibo GmbH")
    assert media_agency_ids([agency, inhouse]) == ["a"]


@pytest.mark.parametrize(
    "company",
    [
        "OMD Germany",
        "Omnicom Media Group",
        "WPP Media",
        "GroupM Germany",
        "KINESSO",
        "IPG Mediabrands",
        "dentsu",
        "Digitas Germany",
        "Mediaplus Group",
        "Serviceplan",
        "PHD Germany",
        "Pulse Advertising",
        "Achtung!",  # name ends in punctuation
        "Achtung! Alive",
    ],
)
def test_holding_company_media_agencies_are_dropped(company: str) -> None:
    assert is_media_agency(_listing(lid="1", title="T", company=company))


@pytest.mark.parametrize(
    "company",
    [
        "Bauer Media Group",
        "Hubert Burda Media",
        "FUNKE Mediengruppe",
        "Ströer SE & Co. KGaA",
        "ZEIT Verlagsgruppe",
    ],
)
def test_publishers_and_media_owners_are_kept(company: str) -> None:
    assert not is_media_agency(_listing(lid="1", title="T", company=company))

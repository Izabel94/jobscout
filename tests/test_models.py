import pytest
from pydantic import ValidationError

from jobscout.models import Listing, ListingStatus, Source


def test_listing_minimal_construction():
    listing = Listing(
        source=Source.UPWORK,
        source_id="abc-123",
        url="https://example.com/job",
        title="LangChain RAG engineer",
        description="x" * 100,
        raw={"foo": "bar"},
    )
    assert listing.status == ListingStatus.NEW
    assert listing.score is None
    assert listing.discovered_at


def test_listing_rejects_invalid_status():
    with pytest.raises(ValidationError):
        Listing(
            source=Source.UPWORK,
            source_id="abc",
            url="https://x",
            title="t",
            raw={},
            status="bogus",  # type: ignore[arg-type]
        )

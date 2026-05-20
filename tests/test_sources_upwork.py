"""Unit tests for Upwork rate parsing.

The full `discover()` flow goes through Playwright, which we don't drive in
unit tests — it needs a real browser + a logged-in profile. Those parts are
covered by manual smoke runs (`make discover --only upwork`) instead.
"""

from decimal import Decimal

from jobscout.models import RateUnit
from jobscout.sources.upwork import _parse_rate


def test_parse_hourly_range() -> None:
    lo, hi, unit, ccy = _parse_rate("Hourly: $25.00 - $50.00")
    assert lo == Decimal("25.00")
    assert hi == Decimal("50.00")
    assert unit == RateUnit.HOUR
    assert ccy == "USD"


def test_parse_hourly_with_en_dash() -> None:
    """Real Upwork strings sometimes use the EN DASH (U+2013), not a hyphen."""
    lo, hi, unit, _ = _parse_rate("Hourly: $30.00 – $60.00")  # noqa: RUF001
    assert lo == Decimal("30.00")
    assert hi == Decimal("60.00")
    assert unit == RateUnit.HOUR


def test_parse_fixed_budget() -> None:
    lo, hi, unit, ccy = _parse_rate("Est. Budget: $500")
    assert lo == Decimal("500")
    assert hi == Decimal("500")
    assert unit == RateUnit.FIXED
    assert ccy == "USD"


def test_parse_unknown_returns_none() -> None:
    lo, hi, unit, ccy = _parse_rate("Hourly")
    assert lo is None
    assert hi is None
    assert unit == RateUnit.UNKNOWN
    assert ccy is None


def test_parse_range_without_hourly_tag() -> None:
    """Range present but no 'Hourly' keyword — treat unit as UNKNOWN, not HOUR."""
    lo, hi, unit, ccy = _parse_rate("Budget: $100 - $200")
    assert lo == Decimal("100")
    assert hi == Decimal("200")
    assert unit == RateUnit.UNKNOWN
    assert ccy == "USD"

import pytest

from jobscout.filters import pass_seniority
from jobscout.models import Listing, Source


def _l(title: str, description: str = "") -> Listing:
    return Listing(
        source=Source.LINKEDIN,
        source_id="x",
        url="https://x",
        title=title,
        description=description,
        raw={},
    )


@pytest.mark.parametrize(
    "title",
    [
        "Junior Performance Marketing Manager (all genders)",
        "Jr. Online Marketing Manager",
        "Werkstudent Marketing (m/w/d)",
        "Working Student Digital Marketing",
        "Praktikum Online Marketing",
        "Praktikant Performance Marketing (m/w/d)",
        "Marketing Trainee",
        "Entry Level Marketing Manager",
        "Studentische Aushilfe Marketing",
        "Duales Studium Marketing",
    ],
)
def test_seniority_drops_junior_titles(title: str) -> None:
    assert pass_seniority(_l(title)) is False


@pytest.mark.parametrize(
    "title",
    [
        "Senior Marketing Manager",
        "Performance Marketing Manager (m/w/d)",
        "Head of Digital Marketing",
        "International Marketing Manager",  # 'intern' substring must not trigger
        "Marketing Manager - Internal Comms",  # 'intern' substring must not trigger
    ],
)
def test_seniority_keeps_mid_and_senior_titles(title: str) -> None:
    assert pass_seniority(_l(title)) is True

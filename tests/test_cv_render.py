import base64
import re
from io import BytesIO

import pytest
from PIL import Image
from pypdf import PdfReader

from jobscout.cv_render import cv_markdown_to_pdf_bytes, inline_segments, parse_cv

CV = """# Julian Engelke

julian@example.de · +4917649281728 · <https://www.linkedin.com/in/julian-engelke>

**Senior Consultant Realtime Media**

## Berufserfahrung

### Mediaplus Realtime GmbH & Co KG | Hamburg, Hamburg, Germany

**Senior Consultant** | *2025-01 – Heute*

• Beratung bei der Konzeption und Umsetzung von Kampagnen für Kunden und Partner.
• Koordination der Vermarkter sowie der technischen Dienstleister.

### Mediaplus Realtime GmbH & Co KG | Hamburg, Hamburg, Germany

**Consultant** | *2023-12 – 2024-12*

## Ausbildung

### University of Hamburg

**Bachelor of Science** | *2020*

## Kenntnisse

Google Ads, Programmatische Medieneinkäufe
"""


@pytest.fixture(autouse=True)
def _no_photo(monkeypatch):
    monkeypatch.setattr("jobscout.cv_render.load_profile", lambda: {})


def _pdf_text(pdf: bytes) -> str:
    """Page text with all whitespace removed — pypdf splits kerned glyph runs with spaces."""
    text = "".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
    return re.sub(r"\s+", "", text)


def _has_image(pdf: bytes) -> bool:
    return re.search(rb"/Subtype\s*/Image", pdf) is not None


def _text(segs) -> str:
    return "".join(s["t"] for s in segs)


def test_parse_header_orders_and_labels_contact_like_the_template():
    doc = parse_cv(CV)
    assert doc["name"] == "Julian Engelke"
    assert _text(doc["headline"]) == "Senior Consultant Realtime Media"
    assert [(c["label"], c["text"]) for c in doc["contact"]] == [
        ("M", "+49 176 49281728"),
        ("E", "julian@example.de"),
        ("LinkedIn", "linkedin.com/in/julian-engelke"),
    ]


def test_parse_entry_puts_company_city_and_dates_on_the_right():
    first, second = parse_cv(CV)["sections"][0]["blocks"]
    assert first["title"] == "Senior Consultant"
    assert first["meta"] == "Mediaplus Realtime GmbH & Co KG, Hamburg | 01/2025 – Heute"
    assert len(first["bullets"]) == 2
    assert second["meta"] == "Mediaplus Realtime GmbH & Co KG, Hamburg | 12/2023 – 12/2024"
    assert second["bullets"] == []


def test_parse_entry_without_location_and_plain_paragraph_sections():
    doc = parse_cv(CV)
    education, skills = doc["sections"][1], doc["sections"][2]
    assert education["blocks"][0]["meta"] == "University of Hamburg | 2020"
    assert skills["blocks"] == [
        {
            "kind": "para",
            "segs": [{"t": "Google Ads, Programmatische Medieneinkäufe", "b": False, "i": False, "u": None}],
        }
    ]


def test_parse_detects_the_cv_language():
    assert parse_cv(CV)["lang"] == "de"
    assert parse_cv("# A\n\n## Experience\n\n- Led the team and the roadmap for the product.\n")["lang"] == "en"


def test_a_second_role_under_one_company_header_becomes_its_own_entry():
    doc = parse_cv("# A\n\n## Experience\n\n### Acme | Berlin\n\n**Lead** | *2022*\n\n- x\n\n**Dev** | *2020*\n\n- y\n")
    lead, dev = doc["sections"][0]["blocks"]
    assert (lead["title"], dev["title"]) == ("Lead", "Dev")
    assert dev["meta"] == "Acme, Berlin | 2020"
    assert [_text(b) for b in dev["bullets"]] == ["y"]


def test_consecutive_lines_join_into_one_paragraph():
    doc = parse_cv("# A\n\n## Summary\n\nFirst line\nsecond line\n\nNew paragraph\n")
    assert [_text(b["segs"]) for b in doc["sections"][0]["blocks"]] == ["First line second line", "New paragraph"]


def test_inline_segments_cover_bold_italic_links_and_autolinks():
    segs = inline_segments("**Lead:** ran *A/B tests* via [HubSpot](https://hubspot.com) <https://www.x.io/>")
    assert [(s["t"], s["b"], s["i"], s["u"]) for s in segs] == [
        ("Lead:", True, False, None),
        (" ran ", False, False, None),
        ("A/B tests", False, True, None),
        (" via ", False, False, None),
        ("HubSpot", False, False, "https://hubspot.com"),
        (" ", False, False, None),
        ("x.io", False, False, "https://www.x.io/"),
    ]


def test_empty_cv_parses_to_an_empty_document():
    doc = parse_cv("")
    assert (doc["name"], doc["contact"], doc["sections"]) == ("", [], [])


def test_pdf_renders_cv_text_including_typst_special_characters():
    pdf = cv_markdown_to_pdf_bytes(CV + "\n- Budget #1: 50 $ <fast> @team [x] = 100 %\n")
    assert pdf.startswith(b"%PDF")
    text = _pdf_text(pdf)
    assert "JULIANENGELKE" in text
    assert "Budget#1:50$<fast>@team[x]=100%" in text
    assert "MediaplusRealtimeGmbH&CoKG,Hamburg" in text


def test_pdf_embeds_profile_photo_only_when_present(monkeypatch):
    without = cv_markdown_to_pdf_bytes(CV)
    buf = BytesIO()
    Image.new("RGB", (60, 80), "red").save(buf, "JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    monkeypatch.setattr("jobscout.cv_render.load_profile", lambda: {"photo_jpeg_b64": b64})
    with_photo = cv_markdown_to_pdf_bytes(CV)
    assert _has_image(with_photo)
    assert not _has_image(without)


def _cv_with_bullets(n: int) -> str:
    bullet = "- Konzeption und Umsetzung programmatischer Kampagnen für Agentur- und Direktkunden.\n"
    return CV + "\n## Weitere Erfahrung\n\n### Acme | Berlin\n\n**Lead** | *2019*\n\n" + bullet * n


def _pages(pdf: bytes) -> int:
    return len(PdfReader(BytesIO(pdf)).pages)


def test_cv_that_just_overflows_is_tightened_onto_one_page(monkeypatch):
    import jobscout.cv_render as cv_render

    presets = cv_render._FIT_PRESETS
    monkeypatch.setattr(cv_render, "_FIT_PRESETS", presets[:1])  # regular layout only
    n = 1
    while _pages(cv_markdown_to_pdf_bytes(_cv_with_bullets(n))) == 1:
        n += 1
    monkeypatch.setattr(cv_render, "_FIT_PRESETS", presets)
    assert _pages(cv_markdown_to_pdf_bytes(_cv_with_bullets(n))) == 1


def test_genuinely_long_cv_keeps_regular_layout_across_pages():
    pdf = cv_markdown_to_pdf_bytes(_cv_with_bullets(80))
    assert _pages(pdf) >= 2

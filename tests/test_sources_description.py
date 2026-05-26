"""HTML → markdown helper tests."""

from __future__ import annotations

from jobscout.sources._description import html_to_markdown


def test_empty_returns_empty():
    assert html_to_markdown("") == ""
    assert html_to_markdown(None) == ""


def test_plain_text_passes_through_with_lstrip():
    raw = "    leading whitespace\nno indent\n   three spaces"
    out = html_to_markdown(raw)
    # Per-line lstrip should strip leading whitespace
    for line in out.split("\n"):
        assert not line.startswith(" "), f"line still indented: {line!r}"


def test_html_bullet_list_becomes_markdown_bullets():
    raw = "<ul><li>First</li><li>Second</li><li>Third</li></ul>"
    out = html_to_markdown(raw)
    assert "- First" in out
    assert "- Second" in out
    assert "- Third" in out


def test_html_heading_becomes_markdown_heading():
    raw = "<h2>Requirements</h2><p>Body text</p>"
    out = html_to_markdown(raw)
    assert "## Requirements" in out
    assert "Body text" in out


def test_html_link_converted():
    raw = '<p>See <a href="https://example.com">here</a>.</p>'
    out = html_to_markdown(raw)
    assert "[here](https://example.com)" in out


def test_script_and_style_stripped():
    raw = "<p>Real</p><script>alert(1)</script><style>p{color:red}</style>"
    out = html_to_markdown(raw)
    assert "alert" not in out
    assert "color:red" not in out
    assert "Real" in out

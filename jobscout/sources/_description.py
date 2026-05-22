"""HTML → markdown conversion for raw description fields scraped from
LinkedIn / Indeed. Both sources should pipe their raw HTML through here
before storing in `listings.description`.

Why: JobSpy's default markdown conversion flattens structure (bullets
collapse, leading whitespace triggers code blocks, sections run on).
Running HTML through markdownify preserves bullets, headings, and
section breaks.
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from markdownify import markdownify


def html_to_markdown(html_or_text: str | None) -> str:
    """Best-effort: if input looks like HTML, convert to clean markdown.
    Otherwise pass through with per-line lstrip (kills markdown's 4-space
    indent → code-block rule on plain text)."""
    if not html_or_text:
        return ""
    text = str(html_or_text)
    has_html_tags = "<" in text and ">" in text and ("</" in text or "/>" in text)
    if has_html_tags:
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = markdownify(
            str(soup),
            heading_style="ATX",  # # H1, ## H2 etc.
            bullets="-",          # use dashes (more uniform than `*+-`)
        )
    # Per-line lstrip — defends against the 4-space code-block bug on any
    # input. Idempotent on already-clean markdown.
    text = "\n".join(line.lstrip() for line in text.split("\n"))
    return text.strip()

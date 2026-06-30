"""Render adapted CV markdown to an A4 PDF via Chrome's `Page.printToPDF`.

Takes a Playwright `Page` (the worker passes a temp tab from the CDP Chrome
that's already up). Markdown is converted to HTML, the column-split regex
post-processing matches sidegig's flex layout convention, and Chrome writes
the PDF directly via `page.pdf(...)` — no native deps required.
"""

from __future__ import annotations

import base64
import html as html_lib
import mimetypes
import re
from pathlib import Path
from typing import TYPE_CHECKING

import markdown as md
from jinja2 import Template

if TYPE_CHECKING:
    from playwright.sync_api import Page

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_TEMPLATE_PATH = _CONFIG_DIR / "templates" / "cv.html.j2"
_PHOTO_PATH = _CONFIG_DIR / "profile_photo.jpg"

_H3_SPLIT_RE = re.compile(r"<h3>([^<|]+?)\s*\|\s*([^<]+?)</h3>")
_ROLE_LINE_RE = re.compile(
    r"<p>(<strong>[^<]+?</strong>)\s*\|\s*(<em>[^<]+?</em>)</p>",
)
_HEADER_RE = re.compile(r"^(<h1>[^<]+</h1>\s*<p>.*?</p>)\s*", re.DOTALL)


def _format_role_headers(html: str) -> str:
    html = _H3_SPLIT_RE.sub(
        r'<h3><span class="header-title">\1</span><span class="header-meta">\2</span></h3>',
        html,
    )
    return _ROLE_LINE_RE.sub(r"<p>\1<span>\2</span></p>", html)


def _split_header(html: str) -> tuple[str, str]:
    match = _HEADER_RE.match(html)
    if not match:
        return "", html
    return match.group(1), html[match.end():]


def _photo_data_uri() -> str | None:
    if not _PHOTO_PATH.exists():
        return None
    mime, _ = mimetypes.guess_type(_PHOTO_PATH.name)
    if not mime:
        mime = "image/jpeg"
    data = base64.b64encode(_PHOTO_PATH.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def cv_markdown_to_pdf(cv_md: str, out_path: Path, *, page: Page) -> Path:
    rendered_html = md.markdown(cv_md, extensions=["tables", "fenced_code"])
    rendered_html = _format_role_headers(rendered_html)
    header_html, body_html = _split_header(rendered_html)
    html = Template(_TEMPLATE_PATH.read_text(encoding="utf-8")).render(
        header_html=header_html,
        body_html=body_html,
        photo_data_uri=_photo_data_uri(),
    )
    page.set_content(html, wait_until="networkidle")
    page.pdf(path=str(out_path), format="A4", print_background=True)
    return out_path


_COVER_LETTER_HTML = (
    "<html><head><meta charset='utf-8'><style>"
    "body{font-family:Helvetica,Arial,sans-serif;font-size:11pt;line-height:1.5;"
    "margin:2.5cm;white-space:pre-wrap;}</style></head><body>__BODY__</body></html>"
)


def cover_letter_to_pdf(cover_letter: str, out_path: Path, *, page: Page) -> Path:
    """Render the plain-text cover letter to an A4 PDF, for forms that want the
    cover letter as a file upload rather than a textarea."""
    html = _COVER_LETTER_HTML.replace("__BODY__", html_lib.escape(cover_letter or ""))
    page.set_content(html, wait_until="networkidle")
    page.pdf(path=str(out_path), format="A4", print_background=True)
    return out_path

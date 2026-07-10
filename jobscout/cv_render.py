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


def _normalize_bullets(cv_md: str) -> str:
    """Profiles bootstrapped from LinkedIn use literal `• ` bullets with no blank
    line before them — markdown then folds them into the preceding role line
    instead of a list. Convert to `- ` and open the list with a blank line."""
    out: list[str] = []
    in_list = False
    for line in cv_md.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("• "):
            if not in_list and out and out[-1].strip():
                out.append("")
            out.append("- " + stripped[2:])
            in_list = True
        else:
            out.append(line)
            in_list = False
    return "\n".join(out)


def cv_markdown_to_html(cv_md: str) -> str:
    """Self-contained styled CV HTML (inline CSS + embedded photo). Pure Python —
    no Chrome/WeasyPrint — so it works on Cloud; the user prints it to PDF."""
    rendered_html = md.markdown(_normalize_bullets(cv_md), extensions=["tables", "fenced_code"])
    rendered_html = _format_role_headers(rendered_html)
    header_html, body_html = _split_header(rendered_html)
    return Template(_TEMPLATE_PATH.read_text(encoding="utf-8")).render(
        header_html=header_html,
        body_html=body_html,
        photo_data_uri=_photo_data_uri(),
    )


_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_PUNCT = {
    "–": "-", "—": "-", "−": "-", "•": "-", "…": "...", "€": "EUR",
    "’": "'", "‘": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "«": '"', "»": '"',
}


def _plain(text: str) -> str:
    """Strip markdown emphasis/links + map typographic punctuation to ASCII, then
    drop any residual non-latin-1 char (core PDF fonts are latin-1)."""
    text = _MD_LINK_RE.sub(r"\1", text).replace("**", "").replace("`", "")
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)", "", text)
    for uni, asc in _PUNCT.items():
        text = text.replace(uni, asc)
    return text.encode("latin-1", "ignore").decode("latin-1").strip()


def cv_markdown_to_pdf_bytes(cv_md: str) -> bytes:
    """Direct CV → PDF via fpdf2 — pure Python, no system libs, so it runs on
    Streamlit Cloud. Lays out the CV markdown structure (# name, contact line,
    ## section, ### company | location, **role** | *dates*, bullets)."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 12, 15)
    pdf.add_page()
    w = pdf.epw
    c1, c2 = w * 0.68, w * 0.32
    photo = _PHOTO_PATH if _PHOTO_PATH.exists() else None
    head_w = w - 26 if photo else w
    expect_contact = False

    for raw in cv_md.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            if photo:
                pdf.image(str(photo), x=pdf.w - 15 - 22, y=11, w=22)
            pdf.set_font("Helvetica", "B", 17)
            pdf.multi_cell(head_w, 9, _plain(line[2:]), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            expect_contact = True
        elif expect_contact and not line.startswith(("#", "-", "*", "•")):
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(90, 90, 90)
            pdf.multi_cell(head_w, 5, _plain(line), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)
            expect_contact = False
        elif line.startswith("## "):
            pdf.ln(2.5)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(w, 6, _plain(line[3:]).upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.line(15, pdf.get_y(), 15 + w, pdf.get_y())
            pdf.ln(1.5)
        elif line.startswith("### "):
            company, _, loc = line[4:].partition("|")
            pdf.ln(1.5)
            pdf.set_font("Helvetica", "B", 10.5)
            if loc.strip():
                pdf.cell(c1, 5.5, _plain(company))
                pdf.set_font("Helvetica", "", 9)
                pdf.cell(c2, 5.5, _plain(loc), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.multi_cell(w, 5.5, _plain(company), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif line.startswith("**") and "|" in line:
            role, dates = line.split("|", 1)
            pdf.set_font("Helvetica", "", 9.5)
            pdf.cell(c1, 5, _plain(role))
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(c2, 5, _plain(dates), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif line[:2] in ("- ", "* ", "• "):
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_x(18)
            pdf.multi_cell(w - 3, 4.6, "-  " + _plain(line[2:]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif line.startswith("**") and line.endswith("**"):
            pdf.set_font("Helvetica", "B", 10)
            pdf.multi_cell(w, 5.5, _plain(line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.set_font("Helvetica", "", 9.5)
            pdf.multi_cell(w, 4.8, _plain(line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())


def cv_markdown_to_pdf(cv_md: str, out_path: Path, *, page: Page) -> Path:
    page.set_content(cv_markdown_to_html(cv_md), wait_until="networkidle")
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

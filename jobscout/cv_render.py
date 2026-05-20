"""Render adapted CV markdown to A4 PDF via Jinja template + WeasyPrint.

WeasyPrint needs Pango + GLib (`brew install pango glib` on macOS); import
fails at runtime if they're missing.

CV markdown convention: `### Company | Location` for entries and `**Role**
| *Dates*` below — `|` is the column separator. HTML is post-processed so
the template's flex rules can two-column the meta side.
"""

import base64
import mimetypes
import re
from pathlib import Path

import markdown as md
from jinja2 import Template
from weasyprint import HTML

from jobscout.config_loader import load_profile

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_TEMPLATE = (_CONFIG_DIR / "templates" / "cv.html.j2").read_text(encoding="utf-8")
_DEFAULT_PHOTO_PATH = _CONFIG_DIR / "profile_photo.jpg"

# Split `<h3>Company | Location</h3>` into two spans for flex layout.
_H3_SPLIT_RE = re.compile(r"<h3>([^<|]+?)\s*\|\s*([^<]+?)</h3>")

# Role line: `<p><strong>Role</strong> | <em>Dates</em></p>` -> flex row.
_ROLE_LINE_RE = re.compile(
    r"<p>(<strong>[^<]+?</strong>)\s*\|\s*(<em>[^<]+?</em>)</p>",
)

# h1 + following contact paragraph render in .cv-header-text so the optional photo can sit beside them.
_HEADER_RE = re.compile(
    r"^(<h1>[^<]+</h1>\s*<p>.*?</p>)\s*",
    re.DOTALL,
)


def _format_role_headers(html: str) -> str:
    html = _H3_SPLIT_RE.sub(
        r'<h3><span class="header-title">\1</span><span class="header-meta">\2</span></h3>',
        html,
    )
    return _ROLE_LINE_RE.sub(r"<p>\1<span>\2</span></p>", html)


def _split_header(html: str) -> tuple[str, str]:
    """Falls back to (empty, html) when the expected `<h1>…</h1><p>…</p>` prefix is absent."""
    match = _HEADER_RE.match(html)
    if not match:
        return "", html
    return match.group(1), html[match.end() :]


def _photo_data_uri() -> str | None:
    """Returns base64 data URI of configured profile photo, or None if absent."""
    profile = load_profile()
    configured = profile.get("photo_path")
    photo_path = Path(configured) if configured else _DEFAULT_PHOTO_PATH
    if not photo_path.is_absolute():
        photo_path = _CONFIG_DIR.parent / photo_path
    if not photo_path.exists():
        return None
    mime, _ = mimetypes.guess_type(photo_path.name)
    if not mime:
        mime = "image/jpeg"
    data = base64.b64encode(photo_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def cv_markdown_to_pdf(cv_md: str, out_path: Path) -> Path:
    rendered_html = md.markdown(cv_md, extensions=["tables", "fenced_code"])
    rendered_html = _format_role_headers(rendered_html)
    header_html, body_html = _split_header(rendered_html)
    html = Template(_TEMPLATE).render(
        header_html=header_html,
        body_html=body_html,
        photo_data_uri=_photo_data_uri(),
    )
    HTML(string=html).write_pdf(str(out_path))
    return out_path

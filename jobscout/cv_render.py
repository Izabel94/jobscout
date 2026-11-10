"""Render CV markdown to an A4 PDF with Typst; render the cover letter via Chrome.

The CV markdown convention (written by the draft step and by
`config_loader.synthesize_cv_markdown_from_profile`):

    # Name
    email · phone · <https://linkedin.com/in/...>
    **Headline**
    ## Section
    ### Company | Location
    **Role** | *2023-01 - present*
    - bullet

`parse_cv` turns that into plain data; `config/templates/cv.typ` owns the whole
layout. Fonts are bundled in `config/fonts` and system fonts are ignored, so the
Streamlit download and the apply worker produce the same PDF on every machine.
"""

from __future__ import annotations

import base64
import html as html_lib
import io
import json
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typst
from pypdf import PdfReader

from jobscout.config_loader import load_profile

if TYPE_CHECKING:
    from playwright.sync_api import Page

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_TEMPLATE_PATH = _CONFIG_DIR / "templates" / "cv.typ"
_FONTS_DIR = _CONFIG_DIR / "fonts"

_INLINE_RE = re.compile(
    r"\*\*(?P<b>.+?)\*\*|(?<!\*)\*(?P<i>[^*]+?)\*(?!\*)|\[(?P<lt>[^\]]+)\]\((?P<lu>[^)]+)\)|<(?P<au>https?://[^>]+)>"
)
_ROLE_RE = re.compile(r"^\*\*(?P<role>.+?)\*\*\s*(?:\|\s*(?P<dates>.+))?$")
_BULLET_RE = re.compile(r"^[-*•]\s+")
_CONTACT_SPLIT_RE = re.compile(r"\s+[·|•]\s+")
_YEAR_MONTH_RE = re.compile(r"\b(\d{4})-(\d{2})\b")
_DE_MOBILE_RE = re.compile(r"^\+49(1[5-7]\d)(\d{6,8})$")
_CONTACT_ORDER = ["M", "E", "L", "LinkedIn", "Web"]
_DE_WORDS = {"und", "der", "die", "das", "von", "mit", "für", "sowie", "bei", "eines", "einer"}
_EN_WORDS = {"and", "the", "of", "with", "for", "to", "as", "by", "an"}


def _photo_b64() -> str | None:
    """The CV photo uploaded in Settings (base64 JPEG on the profile), or None."""
    return load_profile().get("photo_jpeg_b64") or None


def inline_segments(text: str) -> list[dict[str, Any]]:
    """Split markdown inline markup into styled plain-text runs: {t, b, i, u}."""
    segs: list[dict[str, Any]] = []
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            segs.append({"t": text[pos : m.start()], "b": False, "i": False, "u": None})
        if m["b"] is not None:
            segs.append({"t": m["b"], "b": True, "i": False, "u": None})
        elif m["i"] is not None:
            segs.append({"t": m["i"], "b": False, "i": True, "u": None})
        elif m["lt"] is not None:
            segs.append({"t": m["lt"], "b": False, "i": False, "u": m["lu"]})
        else:
            segs.append({"t": _display_url(m["au"]), "b": False, "i": False, "u": m["au"]})
        pos = m.end()
    if pos < len(text):
        segs.append({"t": text[pos:], "b": False, "i": False, "u": None})
    return segs


def _display_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url).rstrip("/")


def _contact_item(raw: str) -> dict[str, Any]:
    """Label one contact-line item the way the template shows it (M:, E:, L:, LinkedIn:)."""
    text = raw.strip().strip("<>")
    if "@" in text and " " not in text:
        return {"label": "E", "text": text, "url": f"mailto:{text}"}
    if re.match(r"^(https?://|www\.)", text) or "linkedin.com" in text:
        url = text if text.startswith("http") else f"https://{text}"
        label = "LinkedIn" if "linkedin.com" in text else "Web"
        return {"label": label, "text": _display_url(url), "url": url}
    if re.fullmatch(r"\+?[\d\s/()-]{7,}", text):
        phone = _DE_MOBILE_RE.sub(r"+49 \1 \2", text.replace(" ", ""))
        return {"label": "M", "text": phone, "url": f"tel:{text.replace(' ', '')}"}
    return {"label": "L", "text": text, "url": None}


def _city(location: str) -> str:
    return location.split(",")[0].strip()


def _dates(raw: str) -> str:
    return _YEAR_MONTH_RE.sub(r"\2/\1", raw.strip().strip("*").strip())


def _guess_lang(text: str) -> str:
    words = re.findall(r"[a-zäöüß]+", text.lower())
    de = sum(w in _DE_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    return "de" if de >= en else "en"


class _CvParser:
    """Line-based parser for the CV markdown convention in the module docstring."""

    def __init__(self) -> None:
        self.doc: dict[str, Any] = {"name": "", "headline": [], "contact": [], "intro": [], "sections": []}
        self.entry: dict[str, Any] | None = None
        self.prev_blank = True

    def feed(self, line: str) -> None:
        if not line or line == "---":
            self.prev_blank = True
            return
        if line.startswith("# "):
            self.doc["name"] = line[2:].strip()
        elif line.startswith("## "):
            self.doc["sections"].append({"title": line[3:].strip(), "blocks": []})
            self.entry = None
        elif not self.doc["sections"]:
            self._header_line(line)
        elif line.startswith("### "):
            self._company(line[4:])
        else:
            self._body_line(line)
        self.prev_blank = False

    def _header_line(self, line: str) -> None:
        role = _ROLE_RE.match(line)
        if role and not role["dates"] and not self.doc["headline"]:
            self.doc["headline"] = inline_segments(role["role"])
        elif not self.doc["contact"] and not line.startswith("**"):
            items = [_contact_item(p) for p in _CONTACT_SPLIT_RE.split(line) if p.strip()]
            self.doc["contact"] = sorted(items, key=lambda c: _CONTACT_ORDER.index(c["label"]))
        else:
            self.doc["intro"].append(inline_segments(line))

    def _company(self, text: str) -> None:
        org, _, loc = text.partition("|")
        city = _city(loc)
        self.entry = {
            "kind": "entry",
            "org": org.strip(),
            "city": city,
            "has_role": False,
            "title": org.strip(),
            "meta": city,
            "bullets": [],
            "paras": [],
        }
        self._blocks().append(self.entry)

    def _role(self, role: str, dates: str) -> None:
        assert self.entry is not None
        if self.entry["has_role"]:
            self._company(f"{self.entry['org']} | {self.entry['city']}")
            assert self.entry is not None
        place = ", ".join(p for p in (self.entry["org"], self.entry["city"]) if p)
        self.entry.update(title=role, meta=" | ".join(p for p in (place, _dates(dates)) if p), has_role=True)

    def _body_line(self, line: str) -> None:
        role = _ROLE_RE.match(line)
        if self.entry is not None and role and (role["dates"] or not self.entry["has_role"]):
            self._role(role["role"], role["dates"] or "")
        elif _BULLET_RE.match(line):
            self._bullet(inline_segments(_BULLET_RE.sub("", line)))
        else:
            self._para(line)

    def _bullet(self, segs: list[dict[str, Any]]) -> None:
        if self.entry is not None:
            self.entry["bullets"].append(segs)
            return
        blocks = self._blocks()
        if not blocks or blocks[-1]["kind"] != "list":
            blocks.append({"kind": "list", "items": []})
        blocks[-1]["items"].append(segs)

    def _para(self, line: str) -> None:
        """Add a text line; a line right after another (no blank between) continues its paragraph."""
        if self.entry is not None:
            paras: list[list[dict[str, Any]]] = self.entry["paras"]
            if paras and not self.prev_blank:
                paras[-1].extend(inline_segments(" " + line))
            else:
                paras.append(inline_segments(line))
            return
        blocks = self._blocks()
        if blocks and blocks[-1]["kind"] == "para" and not self.prev_blank:
            blocks[-1]["segs"].extend(inline_segments(" " + line))
        else:
            blocks.append({"kind": "para", "segs": inline_segments(line)})

    def _blocks(self) -> list[dict[str, Any]]:
        return self.doc["sections"][-1]["blocks"]  # type: ignore[no-any-return]


def parse_cv(cv_md: str) -> dict[str, Any]:
    """Turn CV markdown into the plain data `config/templates/cv.typ` lays out."""
    parser = _CvParser()
    for raw in cv_md.splitlines():
        parser.feed(raw.strip())
    doc = parser.doc
    doc["lang"] = _guess_lang(cv_md)
    return doc


def cv_markdown_to_pdf_bytes(cv_md: str) -> bytes:
    """Render CV markdown (plus the profile photo, if any) to A4 PDF bytes.

    Tries the regular layout first; if that spills onto a second page, retries with
    slightly tighter presets so a CV that only just overflows fits on one page. A CV
    that is genuinely longer keeps the regular layout across pages.
    """
    data = parse_cv(cv_md)
    photo_b64 = _photo_b64()
    data["has_photo"] = photo_b64 is not None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "cv.typ").write_bytes(_TEMPLATE_PATH.read_bytes())
        if photo_b64:
            (root / "photo.jpg").write_bytes(base64.b64decode(photo_b64))
        regular = _compile(root, data, _FIT_PRESETS[0])
        if _page_count(regular) == 1:
            return regular
        for preset in _FIT_PRESETS[1:]:
            tight = _compile(root, data, preset)
            if _page_count(tight) == 1:
                return tight
        return regular


# Body font size (pt) and vertical-spacing factor, regular first.
_FIT_PRESETS = ({"size": 9.5, "gap": 1.0}, {"size": 9.25, "gap": 0.8}, {"size": 9.0, "gap": 0.65})


def _compile(root: Path, data: dict[str, Any], fit: dict[str, float]) -> bytes:
    (root / "data.json").write_text(json.dumps({**data, "fit": fit}, ensure_ascii=False), encoding="utf-8")
    pdf = typst.compile(
        str(root / "cv.typ"),
        root=str(root),
        font_paths=[str(_FONTS_DIR)],
        ignore_system_fonts=True,
        format="pdf",
    )
    return bytes(pdf)


def _page_count(pdf: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf)).pages)


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

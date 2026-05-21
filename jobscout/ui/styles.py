"""Custom CSS injection. Streamlit's primitives + our theme config handle
most layout; this file adds the small bits Streamlit can't theme natively:
badge color classes, card border tweaks, score-pill background colors.
"""

from __future__ import annotations

import streamlit as st

_CSS = """
<style>
  /* Score pill — colour by threshold class */
  .jobscout-score { display:inline-block; padding:4px 10px; border-radius:14px; font-size:13px; font-weight:600; color:white; }
  .jobscout-score-high { background:#16a34a; }
  .jobscout-score-mid  { background:#ca8a04; }
  .jobscout-score-low  { background:#9ca3af; }

  /* Derived-field badges */
  .jobscout-badge { display:inline-block; padding:2px 9px; border-radius:10px; font-size:11px; font-weight:500; margin-right:4px; }
  .jobscout-badge-remote { background:#eff6ff; color:#1e40af; }
  .jobscout-badge-hybrid { background:#fef9c3; color:#854d0e; }
  .jobscout-badge-onsite { background:#ffedd5; color:#9a3412; }
  .jobscout-badge-unknown-arr { background:#f3f4f6; color:#374151; }
  .jobscout-badge-fulltime { background:#f0fdf4; color:#166534; }
  .jobscout-badge-permanent { background:#f0fdf4; color:#166534; }
  .jobscout-badge-external { background:#fef3c7; color:#854d0e; }
  .jobscout-badge-easy { background:#f3e8ff; color:#6b21a8; }
  .jobscout-badge-dropped { background:#fee2e2; color:#991b1b; }

  /* Seen-listing prefix glyph */
  .jobscout-seen-mark { color:#16a34a; font-weight:700; margin-right:6px; }

  /* Muted metadata row */
  .jobscout-meta { color:#6b7280; font-size:13px; }

  /* Scoring rationale callout */
  .jobscout-rationale { background:#f0fdf4; border-left:3px solid #16a34a;
    padding:8px 12px; font-size:13px; color:#374151; border-radius:0 6px 6px 0;
    margin:8px 0; }
</style>
"""


def inject() -> None:
    """Call once at app boot, before any Pipeline/Settings render."""
    st.markdown(_CSS, unsafe_allow_html=True)

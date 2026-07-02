"""Custom CSS injection. Streamlit's primitives + our theme config handle
most layout; this file adds the small bits Streamlit can't theme natively:
badge color classes, card border tweaks, score-pill background colors.
"""

from __future__ import annotations

import streamlit as st

_CSS = """
<style>
  /* Tab labels — Streamlit defaults render them small and muted */
  div[data-baseweb="tab-list"] button[role="tab"] p {
    font-size: 16px !important;
    font-weight: 500 !important;
  }


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
  .jobscout-badge-blocked { background:#fff7ed; color:#9a3412; border:1px solid #fdba74; }

  .jobscout-salary { font-size:13px; color:#166534; font-weight:600; margin:2px 0; }
  .jobscout-salary-src { color:#9ca3af; font-weight:400; font-size:11px; }

  /* Viewed-card left-border accent. The marker span is display:none itself;
     CSS :has() picks it up to style the enclosing card.
     data-test-scroll-behavior distinguishes the card-level stVerticalBlock
     from the page-level one (only the card has it). */
  .jobscout-viewed-marker { display: none; }
  div[data-testid="stVerticalBlock"][data-test-scroll-behavior]:has(.jobscout-viewed-marker) {
    border-left: 4px solid #16a34a !important;
  }

  /* Card title row — favicon + title flex layout */
  .jobscout-card-row { display:flex; align-items:center; gap:8px; }
  .jobscout-card-title { font-weight:600; font-size:15px; }

  /* Muted metadata row */
  .jobscout-meta { color:#6b7280; font-size:13px; }

  /* Scoring rationale callout */
  .jobscout-rationale { background:#f0fdf4; border-left:3px solid #16a34a;
    padding:8px 12px; font-size:13px; color:#374151; border-radius:0 6px 6px 0;
    margin:8px 0; }

  /* KPI hero tiles */
  .jobscout-kpi-tile {
    background:white; border:1px solid #eee; border-radius:10px; padding:14px;
  }
  .jobscout-kpi-label {
    color:#666; font-size:11px; letter-spacing:0.05em; text-transform:uppercase;
  }
  .jobscout-kpi-value {
    font-size:28px; font-weight:700; margin-top:4px;
  }
  .jobscout-kpi-suffix { color:#999; font-size:18px; }

  /* Pagination status caption */
  .jobscout-pagination-status {
    text-align:center; color:#666; font-size:13px; padding-top:8px;
  }

  /* Empty / no-match callout */
  .jobscout-empty-callout {
    background:#fafafa; border:1px dashed #ddd; border-radius:12px;
    padding:32px; text-align:center; color:#666;
  }
  .jobscout-empty-callout.compact { padding:24px; margin-bottom:14px; }
  .jobscout-empty-title {
    font-size:16px; font-weight:600; color:#1f2937; margin-bottom:8px;
  }
  .jobscout-empty-body { font-size:14px; }

  /* safe_render error banner */
  .jobscout-error-callout {
    background:#fef2f2; border:1px solid #fecaca; border-radius:12px;
    padding:16px; color:#7f1d1d;
  }
  .jobscout-error-title { font-weight:600; }

  /* Read-only profile snapshot in Settings */
  .jobscout-profile-snapshot {
    background:#fafafa; border:1px solid #eee; border-radius:10px;
    padding:18px; font-size:13px; color:#666;
  }
  .jobscout-profile-snapshot-title {
    font-weight:600; color:#1f2937; margin-bottom:8px;
  }
  .jobscout-profile-snapshot-footer {
    margin-top:8px; color:#999; font-size:12px;
  }

  /* Mobile reflow — at narrow widths, soften the KPI hero so 4 tiles wrap
     gracefully (Streamlit stacks st.columns on mobile, but the tile padding
     can feel cramped). */
  @media (max-width: 768px) {
    .jobscout-kpi-tile { padding:12px; }
    .jobscout-kpi-value { font-size:24px; }
    .jobscout-empty-callout { padding:24px 16px; }
    .jobscout-profile-snapshot { padding:14px; }
  }

  /* Settings chip coloring — marker span (display:none) is dropped in the
     same column as the chip button; CSS :has() finds the marker's nearest
     stColumn ancestor and styles the button inside. */
  .jobscout-chip-marker-search,
  .jobscout-chip-marker-deny { display: none; }

  /* Tight pill shape applied to ANY chip button (search or deny) */
  div[data-testid="stColumn"]:has(.jobscout-chip-marker-search) [data-testid="stButton"] > button,
  div[data-testid="stColumn"]:has(.jobscout-chip-marker-deny) [data-testid="stButton"] > button {
    border-radius: 14px;
    font-size: 13px;
    font-weight: 500;
    line-height: 1.2;
    padding: 4px 10px;
    min-height: 0;
  }

  /* Search-term chips — blue */
  div[data-testid="stColumn"]:has(.jobscout-chip-marker-search) [data-testid="stButton"] > button {
    background: #eff6ff !important;
    color: #1e40af !important;
    border: 1px solid #dbeafe !important;
  }
  div[data-testid="stColumn"]:has(.jobscout-chip-marker-search) [data-testid="stButton"] > button:hover {
    background: #dbeafe !important;
  }

  /* Title-denylist chips — red */
  div[data-testid="stColumn"]:has(.jobscout-chip-marker-deny) [data-testid="stButton"] > button {
    background: #fee2e2 !important;
    color: #991b1b !important;
    border: 1px solid #fecaca !important;
  }
  div[data-testid="stColumn"]:has(.jobscout-chip-marker-deny) [data-testid="stButton"] > button:hover {
    background: #fecaca !important;
  }

  /* Card Remove button — red so it reads as an actionable delete, not a
     disabled secondary button. Same marker+:has() mechanism as the chips, but
     descendant (not >) selector: the help= tooltip wraps the button in
     stTooltipHoverTarget divs inside stButton. */
  .jobscout-remove-marker { display: none; }
  div[data-testid="stColumn"]:has(.jobscout-remove-marker) [data-testid="stButton"] button {
    color: #b91c1c !important;
    border: 1px solid #fecaca !important;
  }
  div[data-testid="stColumn"]:has(.jobscout-remove-marker) [data-testid="stButton"] button:hover {
    color: #ffffff !important;
    background: #dc2626 !important;
    border-color: #dc2626 !important;
  }
</style>
"""


def inject() -> None:
    """Call once at app boot, before any Pipeline/Settings render."""
    st.markdown(_CSS, unsafe_allow_html=True)

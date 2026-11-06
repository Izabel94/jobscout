"""Custom CSS injection. Streamlit's primitives + our theme config handle
most layout; this file adds the small bits Streamlit can't theme natively:
badge color classes, the score tile, job-list rows and the detail header.
"""

from __future__ import annotations

import streamlit as st

_CSS = """
<style>
  /* Design tokens (OMR-inspired). New rules use these, never raw values, so sizes
     scale with the user's font size and the layout follows the screen. */
  :root {
    --js-space-1:0.25rem; --js-space-2:0.5rem; --js-space-3:0.75rem; --js-space-4:1rem; --js-space-5:1.25rem;
    --js-radius-control:0.5rem;
    --js-text-xs:0.75rem; --js-text-s:0.8125rem; --js-text-m:0.875rem;
    --js-text-l:clamp(1.125rem, 1rem + 0.6vw, 1.375rem);
    --js-tile:2.5rem; --js-tile-big:3.5rem;
    --js-ink:#0c0d0f; --js-text-subtle:#353a42; --js-text-subtlest:#6c7380;
    --js-surface-1:#f8f9fb; --js-surface-2:#f3f4f6;
    --js-primary:#7337fc; --js-primary-subtlest:#f4f2ff; --js-primary-subtle:#d8d4ff; --js-primary-text:#601ee3;
    --js-danger-bg:#fee5e7; --js-danger-fg:#b91740; --js-danger-border:#fdced4;
    --js-success-bg:#d1fae9; --js-success-fg:#065f4f;
    --js-warning-bg:#fbe69c; --js-warning-fg:#824a11;
    --js-mint-bg:#f1fcfb; --js-mint-fg:#146c71; --js-gold:#e39807;
    --js-header-h:3.75rem;  /* Streamlit's fixed top bar */
    --js-hairline:1px; --js-radius-pill:999px; --js-focus-w:2px;
    /* Layout: the list starts at --js-list-w of the width, capped at --js-list-default-max-w;
       the user can drag it up to --js-list-max-w. Both panes are as tall as the detail
       pane's content, at least --js-pane-min-h; the list scrolls inside that. */
    --js-list-w:38%; --js-list-default-max-w:34rem; --js-list-max-w:60%; --js-pane-min-h:70dvh;
    --js-list-min-h:50dvh;  /* stacked on phones there's no detail pane beside the list to match */
    --js-title-min-w:20rem;  /* below this the header actions wrap under the title */
    --js-photo-w:7rem;
    --js-row-title-lines:2;  /* list titles wrap to this many lines, then "…" */
  }

  /* Start content right under Streamlit's top bar instead of its ~6rem default gap */
  [data-testid="stMainBlockContainer"] { padding-top:var(--js-header-h); }
  .jobscout-wordmark { display:inline-block; background:var(--js-ink); color:#fff; font-weight:800;
    font-size:var(--js-text-l); letter-spacing:0.02em; padding:0 var(--js-space-2); line-height:1.3; }

  /* Tab labels — Streamlit defaults render them small and muted */
  div[data-baseweb="tab-list"] button[role="tab"] p {
    font-size: 16px !important;
    font-weight: 500 !important;
  }


  /* Score tile — colour by threshold class */
  .jobscout-score { display:inline-flex; align-items:center; justify-content:center; flex:none;
    width:var(--js-tile); height:var(--js-tile); border-radius:var(--js-radius-control); font-size:1rem; font-weight:800; }
  .jobscout-score-big { width:var(--js-tile-big); height:var(--js-tile-big); font-size:var(--js-text-l); }
  .jobscout-score-high { background:var(--js-success-bg); color:var(--js-success-fg); }
  .jobscout-score-mid  { background:var(--js-warning-bg); color:var(--js-warning-fg); }
  .jobscout-score-low  { background:var(--js-surface-2); color:var(--js-text-subtle); }

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

  .jobscout-badge-salary { background:var(--js-mint-bg); color:var(--js-mint-fg); }
  .jobscout-salary { font-size:var(--js-text-xs); color:var(--js-mint-fg); font-weight:700; }

  /* Muted metadata row */
  .jobscout-meta { color:var(--js-text-subtlest); font-size:var(--js-text-m); }

  /* Header counts — one line instead of KPI tiles */
  .jobscout-stats { display:flex; flex-wrap:wrap; gap:var(--js-space-1) var(--js-space-5);
    color:var(--js-text-subtlest); font-size:var(--js-text-m); }
  .jobscout-stats b { color:var(--js-ink); }

  /* Job list: scrolls on its own, sized to the screen. On phones the columns stack,
     so the list gets less height and the selected job stays reachable below it. */
  /* List width: user-resizable (handle at the column's bottom-right corner). min-width is
     left to Streamlit, so phones still stack the columns. */
  div[data-testid="stColumn"]:has(div.st-key-job-list) {
    flex:0 0 auto !important; width:min(var(--js-list-w), var(--js-list-default-max-w)); max-width:var(--js-list-max-w);
    overflow:auto; resize:horizontal; display:flex; flex-direction:column; }
  div[data-testid="stColumn"]:has(div.st-key-job-detail) { flex:1 1 0 !important; min-width:0; }
  /* Equal heights: the columns stretch to the taller one. The list's own rows must not make
     the row taller (height:0 + grow), so the detail pane decides and the list scrolls inside. */
  div[data-testid="stLayoutWrapper"]:has(> div.st-key-job-list) { flex:1 1 0; }  /* min-height stays auto: never smaller than the list's own minimum */
  div.st-key-job-list { flex:1 1 0; height:0; min-height:var(--js-list-min-h); overflow-y:auto; }
  div.st-key-job-detail { flex:1 1 auto; min-height:var(--js-pane-min-h); }

  /* Job list row. The row's st.button is stretched over the whole row and made
     invisible, so the row is one click target; its label stays the accessible name. */
  .jobscout-row { display:grid; grid-template-columns:var(--js-tile) minmax(0,1fr) auto; gap:var(--js-space-3); align-items:center; }
  .jobscout-row-text { min-width:0; }
  .jobscout-row-title { font-size:var(--js-text-m); font-weight:600; line-height:1.3; color:var(--js-text-subtle);
    display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:var(--js-row-title-lines); overflow:hidden; }
  .jobscout-row-title-new { font-weight:800; color:var(--js-ink); }
  .jobscout-row-sub { font-size:var(--js-text-s); color:var(--js-text-subtlest); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .jobscout-row-side { display:flex; flex-direction:column; align-items:flex-end; gap:var(--js-space-1);
    font-size:var(--js-text-xs); color:var(--js-text-subtlest); }
  .jobscout-row-star { color:var(--js-gold); }
  .jobscout-new-dot { width:var(--js-space-2); height:var(--js-space-2); border-radius:var(--js-radius-pill); background:var(--js-primary); }
  div[class*="st-key-row-"] {
    position:relative; padding:var(--js-space-2); border-radius:var(--js-radius-control); border:var(--js-hairline) solid transparent; }
  div[class*="st-key-row-"]:hover { background:var(--js-surface-1); }
  div[class*="st-key-row-"]:has(.jobscout-row-selected) { background:var(--js-primary-subtlest); border-color:var(--js-primary); }
  /* the row's button is invisible, so keyboard focus is shown on the row itself */
  div[class*="st-key-row-"]:has(button:focus-visible) { outline:var(--js-focus-w) solid var(--js-primary); outline-offset:var(--js-hairline); }
  /* Streamlit pulls markdown up by -1rem; inside a row that made the border cut the text */
  div[class*="st-key-row-"] [data-testid="stMarkdownContainer"] { margin-bottom:0; }
  /* overflow:hidden: a long title wraps the invisible label, and the button would
     otherwise spill over the next row and catch its clicks */
  div[class*="st-key-open-"] { position:absolute; inset:0; z-index:1; overflow:hidden; }
  /* pinned to the row's edges (not height:100%), so taller two-line rows stay fully clickable */
  div[class*="st-key-open-"] button { position:absolute; inset:0; width:auto; height:auto; min-height:0; opacity:0; }

  /* Detail pane header */
  /* Actions sit top right while the title still gets --js-title-min-w beside them; in a
     narrower pane they wrap under the title. Follows the pane's own width on any device. */
  div.st-key-detail-top > :first-child { flex:1 1 var(--js-title-min-w); min-width:0; }
  /* actions hug the right edge, wrapped or not (the flex item is Streamlit's layout wrapper) */
  div[data-testid="stLayoutWrapper"]:has(> div.st-key-detail-actions) { margin-left:auto; }
  .jobscout-detail-head { display:flex; gap:var(--js-space-4); align-items:flex-start; }
  .jobscout-detail-title { font-size:var(--js-text-l); font-weight:800; line-height:1.25; margin-bottom:var(--js-space-1); }
  .jobscout-chips { display:flex; flex-wrap:wrap; gap:var(--js-space-1); margin:var(--js-space-2) 0 var(--js-space-4); }
  .jobscout-chips .jobscout-badge { margin-right:0; }

  /* Hide is icon-only: its label is visually hidden but stays the accessible name */
  div[class*="st-key-remove-"] button [data-testid="stMarkdownContainer"] {
    position:absolute; width:var(--js-hairline); height:var(--js-hairline); overflow:hidden; clip-path:inset(50%); white-space:nowrap; }

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

  /* Mobile reflow — Streamlit stacks st.columns on narrow screens. */
  @media (max-width: 768px) {
    .jobscout-empty-callout { padding:24px 16px; }
    .jobscout-profile-snapshot { padding:14px; }
  }

  /* Settings chips: remove-buttons keyed rm-term-* (search terms, purple) and rm-deny-* (denylist, red) */
  div[class*="st-key-rm-term-"] button, div[class*="st-key-rm-deny-"] button {
    border-radius:var(--js-radius-pill); font-size:var(--js-text-s); font-weight:600; line-height:1.2;
    padding:var(--js-space-1) var(--js-space-3); min-height:0; max-width:100%; }
  div[class*="st-key-rm-term-"] button p, div[class*="st-key-rm-deny-"] button p {
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }  /* one line; long words get "…" */
  div[class*="st-key-rm-term-"], div[class*="st-key-rm-deny-"] { max-width:100%; }
  div[class*="st-key-rm-term-"] button { background:var(--js-primary-subtlest); color:var(--js-primary-text);
    border:var(--js-hairline) solid var(--js-primary-subtle); }
  div[class*="st-key-rm-deny-"] button { background:var(--js-danger-bg); color:var(--js-danger-fg);
    border:var(--js-hairline) solid var(--js-danger-border); }

  /* Settings: input + Add stay on one row; the input shrinks, the button never wraps away */
  div[class*="st-key-add-row-"] { flex-wrap:nowrap; }
  div[class*="st-key-add-row-"] > :first-child { flex:1 1 0; min-width:0; }

  /* Settings: CV photo preview */
  .jobscout-photo { width:var(--js-photo-w); border-radius:var(--js-radius-control); display:block; }
</style>
"""


def inject() -> None:
    """Call once at app boot, before any Pipeline/Settings render."""
    st.markdown(_CSS, unsafe_allow_html=True)

"""Password gate. No-op locally; required when JOBSCOUT_DEPLOYED is set.

Pattern: render a single password input in an st.form. On submit, compare
against JOBSCOUT_PASSWORD env var (or st.secrets fallback for Streamlit
Cloud). Sticky session via st.session_state.
"""

from __future__ import annotations

import os

import streamlit as st


def _deployed() -> bool:
    return bool(os.environ.get("JOBSCOUT_DEPLOYED"))


def _expected_password() -> str:
    if value := os.environ.get("JOBSCOUT_PASSWORD"):
        return value
    return st.secrets.get("JOBSCOUT_PASSWORD", "")


def auth_gate() -> None:
    """Render the password gate; halts page render until correct password entered."""
    if not _deployed() or st.session_state.get("jobscout_authed"):
        return

    expected = _expected_password()
    if not expected:
        st.error("JOBSCOUT_PASSWORD not configured in secrets.")
        st.stop()

    st.title("jobscout")
    with st.form("auth", clear_on_submit=False):
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    # 1Password autofill workaround — Streamlit emits autocomplete=new-password
    # with no username field, so password managers refuse to autofill.
    # Override autocomplete + inject hidden username (web.dev's documented
    # pattern for password-only logins).
    st.html(
        """
        <script>
        (function() {
          const SENTINEL = 'data-jobscout-uname';
          const decorate = () => {
            document.querySelectorAll('input[type="password"]').forEach(pw => {
              pw.setAttribute('autocomplete', 'current-password');
              pw.setAttribute('name', 'password');
              const host = pw.parentElement;
              if (!host || host.querySelector(`input[${SENTINEL}]`)) return;
              const u = document.createElement('input');
              u.type = 'text';
              u.name = 'username';
              u.setAttribute('autocomplete', 'username');
              u.setAttribute(SENTINEL, 'true');
              u.setAttribute('aria-hidden', 'true');
              u.tabIndex = -1;
              u.style.cssText = 'position:absolute;left:-9999px;width:1px;height:1px;opacity:0;pointer-events:none;';
              host.insertBefore(u, pw);
            });
          };
          decorate();
          const observer = new MutationObserver(decorate);
          observer.observe(document.body, { childList: true, subtree: true });
          setTimeout(() => observer.disconnect(), 5000);
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )

    if submitted:
        if pw == expected:
            st.session_state["jobscout_authed"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()

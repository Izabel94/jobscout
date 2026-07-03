"""Tests for DOM-aware page classification.

snapshot() runs against a real browser (deterministic); classify_page's state
mapping + failure handling are unit-tested with a stubbed LLM."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from jobscout.apply.page_state import PageAssessment, PageState, classify_page, snapshot


@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:  # no browser -> skip, don't fail
            pytest.skip(f"Playwright Chromium unavailable: {e}")
        pg = browser.new_page()
        try:
            yield pg
        finally:
            browser.close()


def test_snapshot_captures_password_and_buttons(page):
    page.set_content(
        "<html><head><title>Sign in</title></head><body>"
        "<h1>Please log in</h1>"
        "<input type='email' style='width:200px;height:30px'>"
        "<input type='password' style='width:200px;height:30px'>"
        "<button style='width:80px;height:30px'>Log in</button>"
        "</body></html>"
    )
    snap = snapshot(page)
    assert snap["title"] == "Sign in"
    assert snap["has_password"] is True
    assert "Please log in" in snap["headings"]
    assert any("Log in" in b for b in snap["buttons"])


def test_snapshot_ignores_hidden_nodes(page):
    page.set_content(
        "<html><body>"
        "<button style='display:none'>Hidden apply</button>"
        "<button style='width:80px;height:30px'>Visible apply</button>"
        "<input type='password' style='display:none'>"
        "</body></html>"
    )
    snap = snapshot(page)
    assert snap["has_password"] is False
    assert any("Visible apply" in b for b in snap["buttons"])
    assert not any("Hidden apply" in b for b in snap["buttons"])


class _StubPage:
    url = "https://example.com/job"

    def evaluate(self, *_a, **_k):
        return {"title": "t", "headings": [], "buttons": [], "has_password": False,
                "field_count": 0, "body_text": "x"}


def test_classify_maps_valid_state():
    with patch("jobscout.apply.page_state.call_json", return_value={"state": "unavailable", "reason": "private"}):
        a = classify_page(_StubPage())
    assert a.state == PageState.UNAVAILABLE
    assert a.blocked is True


def test_classify_unknown_state_falls_back_to_other():
    with patch("jobscout.apply.page_state.call_json", return_value={"state": "banana", "reason": "?"}):
        a = classify_page(_StubPage())
    assert a.state == PageState.OTHER


def test_classify_llm_failure_is_other_not_crash():
    with patch("jobscout.apply.page_state.call_json", side_effect=RuntimeError("boom")):
        a = classify_page(_StubPage())
    assert a.state == PageState.OTHER
    assert a.reason.startswith("classify_failed")


def test_blocked_property():
    assert PageAssessment(PageState.LOGIN_REQUIRED, "").blocked
    assert PageAssessment(PageState.UNAVAILABLE, "").blocked
    assert not PageAssessment(PageState.APPLICATION_FORM, "").blocked
    assert not PageAssessment(PageState.SUBMITTED, "").blocked

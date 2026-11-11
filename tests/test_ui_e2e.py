"""Browser e2e of both tabs (Pipeline split view, Settings) on phone, tablet, laptop and desktop.

Starts the real app (tests/e2e_app.py: app.py + in-memory fake DB) with
`streamlit run` and drives it in Chromium. Checks layout invariants that unit tests
can't see: no sideways scroll, nothing hidden under Streamlit's top bar, the job list
fits the screen, rows aren't clipped, actions stay inside the pane, clicking a row
opens that job. Skips when Chromium isn't installed.
"""

from __future__ import annotations

import contextlib
import re
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import expect

_ROOT = Path(__file__).resolve().parent.parent
_VIEWPORTS = {
    "phone": (390, 844),
    "tablet": (820, 1180),
    "laptop": (1280, 800),
    "desktop": (1920, 1080),
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def app_url() -> Iterator[str]:
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "tests/e2e_app.py",
         "--server.port", str(port), "--server.headless", "true"],
        cwd=_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )  # fmt: skip
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(url, timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.fail("streamlit did not start")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser() -> Iterator[object]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # any launch-path failure → skip, not fail
            pytest.skip(f"Playwright Chromium unavailable: {e}")
        yield b
        b.close()


_ROWS = 'div[class*="st-key-row-"]'


def _wait_until_idle(page) -> None:  # type: ignore[no-untyped-def]
    """Wait until Streamlit's script run is over and web fonts are in (widths shift when Manrope lands).

    Uses the script state Streamlit puts on its root element; the "Running..." widget only
    shows after a delay, so it can't tell an early run from an idle app."""
    page.wait_for_function(
        "document.querySelector('[data-test-script-state]')?.dataset.testScriptState === 'notRunning'"
        " && !document.querySelector('[data-stale=\"true\"]')"
        " && document.fonts.status === 'loaded'",
        timeout=15_000,
    )


def _wait_for_run_after_click(page) -> None:  # type: ignore[no-untyped-def]
    """A click starts a script run a moment later; wait for it to start, then to finish."""
    with contextlib.suppress(PlaywrightTimeout):  # a run shorter than the polling interval is already over
        page.wait_for_function(
            "document.querySelector('[data-test-script-state]')?.dataset.testScriptState === 'running'",
            timeout=3_000,
            polling=10,
        )
    _wait_until_idle(page)


@pytest.mark.parametrize("device", list(_VIEWPORTS))
def test_split_view_layout_holds_on(device: str, app_url: str, browser) -> None:  # type: ignore[no-untyped-def]
    width, height = _VIEWPORTS[device]
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(app_url)
    page.wait_for_selector(".jobscout-detail-title", timeout=60_000)
    _wait_until_idle(page)

    assert page.locator('[data-testid="stException"]').count() == 0
    assert page.evaluate("document.documentElement.scrollWidth") <= width, "page scrolls sideways"

    header_bottom = page.evaluate("document.querySelector('[data-testid=\"stHeader\"]').getBoundingClientRect().bottom")
    assert page.locator(".jobscout-wordmark").bounding_box()["y"] >= header_bottom - 1, "wordmark under the top bar"

    job_list = page.locator("div.st-key-job-list").bounding_box()
    detail = page.locator("div.st-key-job-detail").bounding_box()
    list_col = page.locator('div[data-testid="stColumn"]:has(div.st-key-job-list)').bounding_box()
    if abs(job_list["y"] - detail["y"]) <= 2:  # side by side: one height for both panes
        assert (
            abs((list_col["y"] + list_col["height"]) - (detail["y"] + detail["height"])) <= 2
        ), "panes differ in height"
    else:  # stacked on a phone: the list keeps a usable height of its own
        assert height / 3 <= job_list["height"] <= height, f"stacked list height {job_list['height']}"

    clipped = page.locator(_ROWS).evaluate_all("rows => rows.filter(r => r.scrollHeight > r.clientHeight + 1).length")
    assert clipped == 0, f"{clipped} rows clip their text"

    titles = page.locator(".jobscout-row-title")
    lines = titles.evaluate_all(
        "ts => ts.map(t => Math.round(t.clientHeight / parseFloat(getComputedStyle(t).lineHeight)))"
    )
    assert max(lines) <= 2, f"a list title runs over two lines: {lines}"

    misses = page.locator(_ROWS).evaluate_all(
        """rows => { const list = document.querySelector('div.st-key-job-list').getBoundingClientRect();
             const visible = r => { const b = r.getBoundingClientRect(); const y = b.y + b.height / 2;
               return y > Math.max(list.top, 0) && y < Math.min(list.bottom, innerHeight); };
             return rows.filter(visible).filter(r => { const b = r.getBoundingClientRect();
               return !document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2)?.closest('button'); }).length; }"""
    )
    assert misses == 0, f"{misses} rows don't hit their button in the middle"

    rows = page.locator(_ROWS)
    third_title = rows.nth(2).locator(".jobscout-row-title").inner_text()
    rows.nth(2).click()
    expect(page.locator(".jobscout-detail-title")).to_have_text(third_title, timeout=10_000)
    _wait_until_idle(page)

    pane = page.locator("div.st-key-job-detail").bounding_box()
    title = page.locator(".jobscout-detail-title").bounding_box()
    actions = ('div[class*="st-key-star-"] button', 'div[class*="st-key-remove-"] button', "a:has-text('Posting')",
               'div[class*="st-key-apply-"] button')  # fmt: skip
    boxes = [page.locator(f"{sel} >> visible=true").first.bounding_box() for sel in actions]
    for sel, box in zip(actions, boxes, strict=True):
        assert box["x"] + box["width"] <= pane["x"] + pane["width"] + 1, f"{sel} sticks out of the pane"
    tabs = page.locator('div.st-key-job-detail [data-baseweb="tab-list"]').bounding_box()
    apply_box = boxes[-1]
    assert abs(apply_box["x"] + apply_box["width"] - (tabs["x"] + tabs["width"])) <= 2, "actions not right-aligned"
    beside = [box["y"] < title["y"] + title["height"] for box in boxes]
    below = [box["y"] >= title["y"] + title["height"] for box in boxes]
    assert all(beside) or all(below), "actions split between beside and below the title"
    if all(beside):
        assert all(box["x"] >= title["x"] + title["width"] for box in boxes), "actions overlap the title"
    chips_bottom = page.locator(".jobscout-chips").evaluate("e => e.getBoundingClientRect().bottom")
    tabs_top = page.get_by_role("tab", name="Why it fits").bounding_box()["y"]
    assert tabs_top - chips_bottom >= 8, "no breathing room between the chips and the tabs"
    skip = page.get_by_role("button", name="Skip this job").bounding_box()
    assert skip["x"] + skip["width"] <= pane["x"] + pane["width"] + 1, "Skip sticks out of the pane"
    page.close()


@pytest.mark.parametrize("device", list(_VIEWPORTS))
def test_settings_layout_holds_on(device: str, app_url: str, browser) -> None:  # type: ignore[no-untyped-def]
    width, height = _VIEWPORTS[device]
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(app_url)
    page.wait_for_selector(".jobscout-detail-title", timeout=60_000)
    page.get_by_role("tab", name="Settings").click()
    page.wait_for_selector("div.st-key-rm-term-0 button", timeout=15_000)
    _wait_until_idle(page)

    assert page.locator('[data-testid="stException"]').count() == 0
    assert page.evaluate("document.documentElement.scrollWidth") <= width, "page scrolls sideways"

    for kind in ("term", "deny"):
        field = page.locator(f"div.st-key-new-{kind} input").bounding_box()
        add = page.locator(f"div.st-key-add-{kind} button").bounding_box()
        assert (
            add["y"] < field["y"] + field["height"] and field["y"] < add["y"] + add["height"]
        ), f"Add ({kind}) not on the input's row"
        chip = page.locator(f"div.st-key-rm-{kind}-0 button").bounding_box()
        assert chip["height"] < field["height"], f"{kind} chip wraps its text"

    save = page.get_by_role("button", name="Save changes").bounding_box()
    assert save["x"] + save["width"] <= width, "Save sticks out of the page"
    page.close()


def _drag_corner(page, selector: str, dx: float, dy: float) -> None:  # type: ignore[no-untyped-def]
    """Drag the native CSS resize handle at the element's bottom-right corner."""
    box = page.locator(selector).bounding_box()
    x, y = box["x"] + box["width"] - 3, box["y"] + box["height"] - 3
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y + dy, steps=8)
    page.mouse.up()


def test_user_can_resize_the_list_width_and_it_sticks(app_url: str, browser) -> None:  # type: ignore[no-untyped-def]
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(app_url)
    page.wait_for_selector(".jobscout-detail-title", timeout=60_000)
    _wait_until_idle(page)
    column = 'div[data-testid="stColumn"]:has(div.st-key-job-list)'
    width_before = page.locator(column).bounding_box()["width"]

    _drag_corner(page, column, dx=120, dy=0)
    width_after = page.locator(column).bounding_box()["width"]
    assert width_after > width_before + 60, (width_before, width_after)

    rows = page.locator(_ROWS)
    title = rows.nth(1).locator(".jobscout-row-title").inner_text()
    rows.nth(1).click()  # a rerun must not reset the user's sizes
    expect(page.locator(".jobscout-detail-title")).to_have_text(title, timeout=10_000)
    _wait_until_idle(page)
    assert abs(page.locator(column).bounding_box()["width"] - width_after) <= 1
    page.close()


def test_cover_letter_and_cv_show_in_full(app_url: str, browser) -> None:  # type: ignore[no-untyped-def]
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(app_url)
    page.wait_for_selector(".jobscout-detail-title", timeout=60_000)  # l0, which has a long CV
    _wait_until_idle(page)
    for tab in ("Cover letter", "CV"):
        page.get_by_role("tab", name=tab).click()
        _wait_until_idle(page)
        box = page.locator("div.st-key-job-detail textarea >> visible=true").first
        try:  # the box grows to its text right after it renders, so wait for it to settle
            box.evaluate(
                """t => new Promise((ok, fail) => { const end = Date.now() + 5000;
                     (function check() { if (t.scrollHeight - t.clientHeight <= 1) return ok();
                       if (Date.now() > end) return fail(); requestAnimationFrame(check); })(); })"""
            )
        except Exception:
            hidden = box.evaluate("t => t.scrollHeight - t.clientHeight")
            pytest.fail(f"{tab} box scrolls inside ({hidden}px hidden)")
    page.close()


def test_list_grows_with_a_long_detail_pane(app_url: str, browser) -> None:  # type: ignore[no-untyped-def]
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(app_url)
    page.wait_for_selector(".jobscout-detail-title", timeout=60_000)
    _wait_until_idle(page)
    short = page.locator("div.st-key-job-list").bounding_box()["height"]
    page.get_by_role("tab", name="CV").click()  # l0 has a long CV
    _wait_until_idle(page)
    page.wait_for_function(  # the CV box grows to its text right after rendering
        "(() => { const t = [...document.querySelectorAll('div.st-key-job-detail textarea')].find(e => e.offsetParent);"
        " return t && t.scrollHeight - t.clientHeight <= 1; })()",
        timeout=5_000,
    )
    detail = page.locator("div.st-key-job-detail").bounding_box()
    list_col = page.locator('div[data-testid="stColumn"]:has(div.st-key-job-list)').bounding_box()
    assert page.locator("div.st-key-job-list").bounding_box()["height"] > short, "list didn't grow with the CV"
    assert abs((list_col["y"] + list_col["height"]) - (detail["y"] + detail["height"])) <= 2, "panes differ in height"
    page.close()


def test_keyboard_focus_on_a_row_is_visible(app_url: str, browser) -> None:  # type: ignore[no-untyped-def]
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(app_url)
    page.wait_for_selector(".jobscout-detail-title", timeout=60_000)
    _wait_until_idle(page)
    page.locator('div[class*="st-key-open-"] button').first.focus()
    page.keyboard.press("Tab")  # keyboard navigation onto the next row
    outline = page.evaluate(
        "getComputedStyle(document.activeElement.closest('div[class*=\"st-key-row-\"]')).outlineStyle"
    )
    assert outline != "none", "focused row shows no outline"
    page.close()


def _open(browser, app_url: str):  # type: ignore[no-untyped-def]
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(app_url)
    page.wait_for_selector(".jobscout-detail-title", timeout=60_000)
    _wait_until_idle(page)
    return page


def _select_row(page, listing_id: str) -> None:  # type: ignore[no-untyped-def]
    page.locator(f'div[class*="st-key-row-"]:has(div.st-key-open-{listing_id})').click()
    _wait_until_idle(page)


def test_drafting_fills_letter_and_cv_and_unlocks_apply(app_url: str, browser) -> None:  # type: ignore[no-untyped-def]
    page = _open(browser, app_url)
    _select_row(page, "l5")
    page.get_by_role("tab", name="Cover letter").click()
    expect(page.locator("div.st-key-apply-l5 button >> visible=true").first).to_be_disabled()
    page.locator("div.st-key-draft-letter-l5 button").click()
    expect(page.locator("div.st-key-job-detail textarea >> visible=true").first).to_have_value(
        "Draft 1: Sehr geehrte Damen und Herren", timeout=10_000
    )
    expect(page.locator("div.st-key-apply-l5 button >> visible=true").first).to_be_enabled()
    page.close()


@pytest.mark.parametrize(
    ("tab", "button", "prefix"),
    [("CV", "CV as PDF", "lebenslauf"), ("Cover letter", "Cover letter as PDF", "anschreiben")],
)
def test_pdf_downloads_a_real_named_pdf(app_url: str, browser, tab: str, button: str, prefix: str) -> None:  # type: ignore[no-untyped-def]
    page = _open(browser, app_url)  # l0 has a draft
    _select_row(page, "l0")
    page.get_by_role("tab", name=tab).click()
    _wait_until_idle(page)
    with page.expect_download() as download:
        page.get_by_role("button", name=button).click()
    pdf = Path(download.value.path()).read_bytes()
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
    assert re.fullmatch(rf"{prefix}-[a-z-]+-\d{{4}}-\d{{2}}-\d{{2}}\.pdf", download.value.suggested_filename)
    page.close()


def test_login_walled_and_easy_apply_jobs_link_out(app_url: str, browser) -> None:  # type: ignore[no-untyped-def]
    page = _open(browser, app_url)
    _select_row(page, "l3")  # login wall
    link = page.get_by_role("link", name="Apply on site")
    expect(link).to_have_attribute("href", "https://ats.example/l3")
    expect(page.locator("div.st-key-apply-l3")).to_have_count(0)
    expect(page.get_by_text("needs a login")).to_be_visible()
    _select_row(page, "l4")  # easy apply: LinkedIn handles it
    expect(page.get_by_role("link", name="Open in LinkedIn")).to_have_attribute("href", "https://example.com/l4")
    expect(page.locator("div.st-key-apply-l4")).to_have_count(0)
    page.close()


def test_pagination_moves_between_pages(app_url: str, browser) -> None:  # type: ignore[no-untyped-def]
    page = _open(browser, app_url)
    status = page.locator(".jobscout-pagination-status")
    total = int(status.inner_text().split(" of ")[1])  # jobs passing the default "score 60+" filter
    assert total > 20, "fixture should span two pages"
    expect(status).to_have_text(f"1-20 of {total}")
    page.get_by_role("button", name="Next →").click()
    _wait_until_idle(page)
    expect(status).to_have_text(f"21-{total} of {total}")
    expect(page.locator('div[class*="st-key-open-"]')).to_have_count(total - 20)
    expect(page.locator(".jobscout-detail-title")).to_have_text(page.locator(".jobscout-row-title").first.inner_text())
    page.get_by_role("button", name="← Previous").click()
    _wait_until_idle(page)
    expect(status).to_have_text(f"1-20 of {total}")
    page.close()


def test_only_unviewed_keeps_the_opened_job_on_screen(app_url: str, browser) -> None:  # type: ignore[no-untyped-def]
    page = _open(browser, app_url)
    page.get_by_text("Only unviewed").click()
    _wait_until_idle(page)
    first = page.locator(_ROWS).first
    lid = first.locator('div[class*="st-key-open-"]').get_attribute("class").split("st-key-open-")[1].split()[0]
    title = first.locator(".jobscout-row-title").inner_text()
    _select_row(page, lid)
    page.get_by_role("tab", name="Job description").click()  # any further rerun
    _wait_until_idle(page)
    expect(page.locator(f"div.st-key-open-{lid}")).to_have_count(0)  # viewed now, so filtered out
    expect(page.locator(".jobscout-detail-title")).to_have_text(title)  # but still open
    page.close()


def test_photo_upload_save_and_reload(app_url: str, browser, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PIL import Image

    photo = tmp_path / "face.png"
    Image.new("RGB", (900, 1200), "teal").save(photo)
    page = _open(browser, app_url)
    page.get_by_role("tab", name="Settings").click()
    _wait_until_idle(page)
    expect(page.get_by_text("No photo yet")).to_be_visible()

    page.locator('div[class*="st-key-photo-upload-"] input[type=file]').set_input_files(str(photo))
    expect(page.locator("img.jobscout-photo")).to_be_visible(timeout=10_000)
    page.get_by_role("button", name="Remove photo").click()
    expect(page.locator("img.jobscout-photo")).to_have_count(0)
    page.locator('div[class*="st-key-photo-upload-"] input[type=file]').set_input_files(str(photo))  # same file again
    expect(page.locator("img.jobscout-photo")).to_be_visible(timeout=10_000)

    _wait_until_idle(page)  # a click during a run can be dropped
    page.get_by_role("button", name="Save changes").click()
    _wait_for_run_after_click(page)  # reloading before the save's run would cut it off
    page.reload()
    page.wait_for_selector(".jobscout-detail-title", timeout=60_000)
    page.get_by_role("tab", name="Settings").click()
    expect(page.locator("img.jobscout-photo")).to_be_visible(timeout=10_000)
    page.close()


def test_keyboard_selecting_a_row_keeps_focus_on_it(app_url: str, browser) -> None:  # type: ignore[no-untyped-def]
    page = _open(browser, app_url)
    button = page.locator("div.st-key-open-l2 button")
    button.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".jobscout-detail-title")).to_have_text(
        page.locator("div.st-key-row-l2 .jobscout-row-title").inner_text()
    )
    _wait_until_idle(page)
    focused_row = page.evaluate(
        "(document.activeElement.closest('div[class*=\"st-key-row-\"]')?.className.match(/st-key-row-\\S+/) || [''])[0]"
    )
    assert focused_row == "st-key-row-l2", f"focus moved to {focused_row or 'the page'}"
    page.close()

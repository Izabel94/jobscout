"""End-to-end classifier tests: a real Chromium drives external_ats.apply
against served pages — no mocks in the browser path.

Covers the two ways a walk can end still "on LinkedIn" (host monkeypatched to
the served address): a sign-in gate (no modal) must be login_wall, and a real
Easy Apply modal must raise EasyApplyAfterClickError. Skips when no Chromium
is available (CI without browsers)."""

from __future__ import annotations

import contextlib
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jobscout.apply.external_ats import ApplyOutcome, EasyApplyAfterClickError

_LOGIN_HTML = b"""<!doctype html><html><body>
<h1>Sign in to continue</h1>
<form>
  <input type="email" name="email" style="width:240px;height:32px">
  <input type="password" name="password" style="width:240px;height:32px">
  <button type="submit">Log in</button>
</form>
</body></html>"""

# A visible modal dialog with form fields and no password — an in-app Easy Apply.
_EASY_APPLY_MODAL_HTML = b"""<!doctype html><html><body>
<h1>Job title</h1>
<div role="dialog" aria-label="Einfach bewerben" style="width:400px;height:300px">
  <label>Phone <input type="tel" style="width:200px;height:30px"></label>
  <textarea style="width:300px;height:80px"></textarea>
  <button>Weiter</button>
</div>
</body></html>"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _serve(body: bytes) -> ThreadingHTTPServer:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # stdlib naming
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", _free_port()), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _wait_for_cdp(port: int, timeout_s: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        with contextlib.suppress(Exception), urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=1
        ) as r:
            if r.status == 200:
                return True
        time.sleep(0.3)
    return False


@pytest.fixture
def cdp_url():
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            exe = p.chromium.executable_path
    except Exception as e:  # any launch-path failure → skip, not fail
        pytest.skip(f"Playwright Chromium unavailable: {e}")
    port = _free_port()
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.Popen(
            [
                exe,
                "--headless=new",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--use-mock-keychain",  # no macOS keychain prompt for a throwaway profile
                "--password-store=basic",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            if not _wait_for_cdp(port):
                pytest.skip("Chromium CDP endpoint did not come up")
            yield f"http://127.0.0.1:{port}"
        finally:
            proc.terminate()
            with contextlib.suppress(Exception):
                proc.wait(timeout=10)


def _apply_against(body: bytes, cdp_url: str, monkeypatch):
    from jobscout.apply import external_ats

    server = _serve(body)
    monkeypatch.setenv("JOBSCOUT_CDP_URL", cdp_url)
    monkeypatch.setattr(external_ats, "_EASY_APPLY_HOST_FRAGMENT", "127.0.0.1")
    try:
        return external_ats.apply(
            ats_url=f"http://127.0.0.1:{server.server_address[1]}/",
            proposal="proposal body",
            cv_pdf_path=None,
            listing_title="AI Engineer",
            listing_description="desc",
            adapted_cv_md="# CV",
        )
    finally:
        server.shutdown()


def test_linkedin_signin_gate_reports_login_wall(cdp_url, monkeypatch):
    # Still "on LinkedIn" with no modal → sign-in gate, not Easy Apply.
    result = _apply_against(_LOGIN_HTML, cdp_url, monkeypatch)
    assert result.outcome == ApplyOutcome.NOT_FILLABLE
    assert result.reason == "login_wall"


def test_easy_apply_modal_raises_for_worker_to_flag(cdp_url, monkeypatch):
    # A genuine open modal raises; the worker flips apply_method to easy_apply.
    with pytest.raises(EasyApplyAfterClickError):
        _apply_against(_EASY_APPLY_MODAL_HTML, cdp_url, monkeypatch)

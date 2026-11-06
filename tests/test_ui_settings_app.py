"""Settings tab, run as a real Streamlit app (AppTest) against the in-memory fake profile."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from tests.ui_fake_db import FakeDB, install


def _app() -> None:
    from jobscout.ui.settings import render

    render()


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    fake = FakeDB([])
    install(monkeypatch.setattr, fake)
    return fake


def _run() -> AppTest:
    return AppTest.from_function(_app, default_timeout=30).run()


def _pending(at: AppTest) -> dict:
    return at.session_state["pending_profile"]


def test_removing_a_chip_drops_that_search_term(db: FakeDB) -> None:
    at = _run()
    at.button(key="rm-term-0").click().run()
    assert _pending(at)["required_skill_keywords"] == ["Account Manager"]


def test_adding_a_search_term_appends_it(db: FakeDB) -> None:
    at = _run()
    at.text_input(key="new-term").input("Growth Manager")
    at.button(key="add-term").click().run()
    assert _pending(at)["required_skill_keywords"] == ["Solutions Consultant", "Account Manager", "Growth Manager"]


def test_search_terms_are_capped_at_five(db: FakeDB) -> None:
    db.profile["required_skill_keywords"] = ["A", "B", "C", "D", "E"]
    at = _run()
    at.text_input(key="new-term").input("F")
    at.button(key="add-term").click().run()
    assert _pending(at)["required_skill_keywords"] == ["A", "B", "C", "D", "E"]
    assert any("Cap is 5" in w.value for w in at.warning)


def test_denylist_add_and_remove(db: FakeDB) -> None:
    at = _run()
    at.text_input(key="new-deny").input("SAP")
    at.button(key="add-deny").click().run()
    assert _pending(at)["title_denylist"] == ["Performance Marketing", "SAP"]
    at.button(key="rm-deny-0").click().run()
    assert _pending(at)["title_denylist"] == ["SAP"]


def test_arrangement_checkboxes_update_preferences(db: FakeDB) -> None:
    at = _run()
    at.checkbox(key="arr-onsite").check().run()
    at.checkbox(key="arr-remote").uncheck().run()
    assert _pending(at)["arrangement_preferences"] == ["hybrid", "onsite"]


def test_remove_photo_clears_it(db: FakeDB) -> None:
    db.profile["photo_jpeg_b64"] = "aGVsbG8="
    at = _run()
    assert any("jobscout-photo" in m.value for m in at.markdown), "photo should show before removing"
    at.button(key="photo-remove").click().run()
    assert _pending(at)["photo_jpeg_b64"] is None
    assert not any("jobscout-photo" in m.value for m in at.markdown)


def test_save_writes_the_pending_profile(db: FakeDB) -> None:
    at = _run()
    at.button(key="rm-deny-0").click().run()
    at.button(key="save").click().run()
    saved = [w[1] for w in db.writes if w[0] == "profile"]
    assert saved and saved[-1]["title_denylist"] == []


def test_discard_restores_the_stored_profile(db: FakeDB) -> None:
    at = _run()
    at.button(key="rm-term-0").click().run()
    at.button(key="discard").click().run()
    assert _pending(at)["required_skill_keywords"] == ["Solutions Consultant", "Account Manager"]
    assert not [w for w in db.writes if w[0] == "profile"]

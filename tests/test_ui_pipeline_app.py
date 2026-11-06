"""Pipeline split view, run as a real Streamlit app (AppTest) against an in-memory DB.

Only the DB boundary is faked; rendering, session state, callbacks and reruns are Streamlit's own.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from tests.ui_fake_db import FakeDB, install, make_draft, make_listing


def _app() -> None:
    from jobscout.ui.pipeline import render_listing_list

    render_listing_list()


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    fake = FakeDB(
        [
            make_listing("a", "Solutions Consultant"),
            make_listing("b", "Demand Growth Manager"),
            make_listing("c", "Marketing Manager"),
        ]
    )
    install(monkeypatch.setattr, fake)
    return fake


def _run() -> AppTest:
    return AppTest.from_function(_app, default_timeout=30).run()


def _detail_title(at: AppTest) -> str:
    heads = [m.value for m in at.markdown if "jobscout-detail-title" in m.value]
    assert len(heads) == 1, heads
    return heads[0].split('jobscout-detail-title">')[1].split("<")[0]


def test_first_job_is_shown_but_not_marked_viewed(db: FakeDB) -> None:
    at = _run()
    assert not at.exception
    assert _detail_title(at) == "Solutions Consultant"
    assert db.writes == []


def test_clicking_a_row_shows_that_job_and_marks_it_viewed(db: FakeDB) -> None:
    at = _run()
    at.button(key="open-b").click().run()
    assert _detail_title(at) == "Demand Growth Manager"
    assert db.writes == [("viewed", "b")]
    at.button(key="open-b").click().run()
    assert db.writes == [("viewed", "b")], "a second click must not write again"


def test_apply_is_blocked_until_a_draft_exists(db: FakeDB) -> None:
    at = _run()
    assert at.button(key="apply-a").disabled
    assert not any(w[0] == "apply" for w in db.writes)


def test_apply_with_a_draft_queues_the_request(db: FakeDB) -> None:
    db.drafts["a"] = make_draft("a")
    at = _run()
    at.button(key="apply-a").click().run()
    assert ("apply", "a") in db.writes
    assert at.button(key="apply-a").disabled, "a queued job can't be applied twice"
    assert any("Queued" in i.value for i in at.info)


def test_skip_rejects_the_job_and_shows_the_next_one(db: FakeDB) -> None:
    at = _run()
    at.button(key="open-b").click().run()
    at.button(key="skip-b").click().run()
    assert ("status", "b", "rejected") in db.writes
    assert _detail_title(at) == "Solutions Consultant"
    # A set: AppTest keeps a stale copy of a row from the run that st.rerun() cut short.
    assert {b.key for b in at.button if b.key and b.key.startswith("open-")} == {"open-a", "open-c"}


def test_remove_expires_the_job(db: FakeDB) -> None:
    at = _run()
    at.button(key="remove-a").click().run()
    assert ("status", "a", "expired") in db.writes
    assert _detail_title(at) == "Demand Growth Manager"


def test_job_opened_with_only_unviewed_stays_open(db: FakeDB) -> None:
    at = AppTest.from_function(_app, default_timeout=30)
    at.session_state["only_unviewed"] = True
    at.run()
    at.button(key="open-c").click().run()  # marks c viewed, so it leaves the filtered list
    assert "open-c" not in {b.key for b in at.button}
    assert _detail_title(at) == "Marketing Manager"


def test_changing_a_filter_starts_from_the_new_list(db: FakeDB) -> None:
    db.listings[1]["score"] = 65
    at = _run()
    at.button(key="open-b").click().run()
    at.session_state["min_score"] = 80
    at.run()
    assert _detail_title(at) == "Solutions Consultant"


def test_job_that_left_the_pipeline_is_not_kept_open(db: FakeDB) -> None:
    at = _run()
    at.button(key="open-b").click().run()
    db.listings[1]["status"] = "submitted"  # e.g. the apply worker finished it
    at.run()
    assert _detail_title(at) == "Solutions Consultant"


def test_unsaved_edits_survive_switching_jobs(db: FakeDB) -> None:
    db.drafts["a"] = make_draft("a")
    at = _run()
    at.text_area(key="body-a-d-a").input("Liebe Frau Muster").run()
    at.button(key="open-b").click().run()
    at.button(key="open-a").click().run()
    assert at.text_area(key="body-a-d-a").value == "Liebe Frau Muster"


def test_saving_edits_writes_the_edited_letter_and_the_cv(db: FakeDB) -> None:
    db.drafts["a"] = make_draft("a")
    at = _run()
    at.text_area(key="body-a-d-a").input("Liebe Frau Muster").run()
    at.button(key="save-letter-d-a").click().run()
    assert ("save", "d-a", "Liebe Frau Muster", "# CV") in db.writes


def test_star_toggles_the_bookmark(db: FakeDB) -> None:
    at = _run()
    at.button(key="star-a").click().run()
    assert ("star", "a", True) in db.writes


def test_drafting_creates_letter_and_cv_and_unlocks_apply(db: FakeDB) -> None:
    at = _run()
    assert at.button(key="apply-a").disabled
    at.button(key="draft-letter-a").click().run()
    assert at.text_area(key="body-a-d1-a").value.startswith("Draft 1")
    assert at.text_area(key="cv-a-d1-a").value == "# CV draft 1"
    assert not at.button(key="apply-a").disabled


def test_draft_again_replaces_the_text_and_drops_unsaved_edits(db: FakeDB) -> None:
    at = _run()
    at.button(key="draft-letter-a").click().run()
    at.text_area(key="body-a-d1-a").input("my unsaved edit").run()
    at.button(key="redraft-a").click().run()
    assert at.text_area(key="body-a-d2-a").value.startswith("Draft 2")


def test_star_label_flips_with_the_bookmark(db: FakeDB) -> None:
    at = _run()
    assert at.button(key="star-a").label == "☆"
    at.button(key="star-a").click().run()
    assert at.button(key="star-a").label == "★"


def test_discard_edits_restores_the_saved_text(db: FakeDB) -> None:
    db.drafts["a"] = make_draft("a")
    at = _run()
    at.text_area(key="body-a-d-a").input("scratch").run()
    at.button(key="discard-letter-d-a").click().run()
    assert at.text_area(key="body-a-d-a").value == "Sehr geehrte Damen und Herren"
    assert not [b for b in at.button if b.key == "save-letter-d-a"]


def test_unstarring_under_favorites_only_does_not_keep_the_job_open(db: FakeDB) -> None:
    for listing in db.listings[:2]:
        listing["bookmarked"] = True
    at = AppTest.from_function(_app, default_timeout=30)
    at.session_state["only_bookmarked"] = True
    at.run()
    at.button(key="open-b").click().run()
    at.button(key="star-b").click().run()
    assert _detail_title(at) == "Solutions Consultant"


def test_an_emptied_last_page_steps_back(db: FakeDB) -> None:
    at = AppTest.from_function(_app, default_timeout=30)
    at.session_state["page"] = 3  # past the end, like a last page that just emptied
    at.run()
    assert at.session_state["page"] == 0
    assert _detail_title(at) == "Solutions Consultant"

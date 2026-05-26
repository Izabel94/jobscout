"""Unit tests for the multi-round target selector in external_ats.

The iterative fill loop in `_run` asks the LLM about a subset of fields
each round. Round 1 sees all enumerated fields; rounds 2+ see only fields
that are new (page lazy-rendered them after earlier fills) or that lost
their value (page re-render cleared a previously-filled textarea). The
checkbox/radio case is special: 'unchecked' is meaningful state, not
'empty', so already-seen checkboxes are not re-targeted.
"""

from jobscout.apply.external_ats import _select_round_targets


def _text(fid: str, current: str = "") -> dict:
    return {"id": fid, "kind": "text", "currentValue": current}


def _textarea(fid: str, current: str = "") -> dict:
    return {"id": fid, "kind": "textarea", "currentValue": current}


def _checkbox(fid: str, checked: bool) -> dict:
    return {"id": fid, "kind": "checkbox", "currentValue": "checked" if checked else "unchecked"}


def test_empty_fields_yields_empty_targets():
    assert _select_round_targets([], set()) == []


def test_all_new_fields_returned():
    fields = [_text("a"), _text("b"), _text("c")]
    targets = _select_round_targets(fields, seen_ids=set())
    assert [f["id"] for f in targets] == ["a", "b", "c"]


def test_seen_filled_text_field_is_skipped():
    """Seen field whose currentValue is non-empty doesn't get re-asked."""
    fields = [_text("a", current="julian.engelke@hotmail.de")]
    targets = _select_round_targets(fields, seen_ids={"a"})
    assert targets == []


def test_seen_empty_textarea_is_retargeted():
    """The cover-letter-cleared-by-re-render case."""
    fields = [_textarea("cover", current="")]
    targets = _select_round_targets(fields, seen_ids={"cover"})
    assert [f["id"] for f in targets] == ["cover"]


def test_seen_whitespace_only_field_is_retargeted():
    fields = [_text("a", current="   ")]
    targets = _select_round_targets(fields, seen_ids={"a"})
    assert [f["id"] for f in targets] == ["a"]


def test_unchecked_checkbox_after_seen_is_not_retargeted():
    """unchecked is meaningful state, not 'empty' — don't re-ask."""
    fields = [_checkbox("opt_in", checked=False)]
    targets = _select_round_targets(fields, seen_ids={"opt_in"})
    assert targets == []


def test_radio_unchecked_after_seen_is_not_retargeted():
    fields = [{"id": "race_white", "kind": "radio", "currentValue": "unchecked"}]
    targets = _select_round_targets(fields, seen_ids={"race_white"})
    assert targets == []


def test_mixed_round_2_scenario():
    """Realistic round-2 page snapshot after a CV upload:
      - 'first_name', 'last_name', 'email' filled in round 1, still filled — skip
      - 'cover_letter' filled in round 1 but cleared by re-render — re-target
      - 'state' lazy-revealed after 'country' was selected — new, target
      - 'eeoc_race' radio still unchecked — already presented, skip
    """
    fields = [
        _text("first_name", current="Julian"),
        _text("last_name", current="Engelke"),
        _text("email", current="julian.engelke@hotmail.de"),
        _textarea("cover_letter", current=""),  # re-render cleared it
        _text("state"),  # lazy-revealed
        {"id": "eeoc_race", "kind": "radio", "currentValue": "unchecked"},
    ]
    seen = {"first_name", "last_name", "email", "cover_letter", "eeoc_race"}
    target_ids = [f["id"] for f in _select_round_targets(fields, seen_ids=seen)]
    assert target_ids == ["cover_letter", "state"]


def test_field_with_no_id_is_dropped():
    fields = [{"kind": "text", "currentValue": ""}, _text("ok")]
    targets = _select_round_targets(fields, seen_ids=set())
    assert [f["id"] for f in targets] == ["ok"]

def test_external_ats_module_loads():
    from jobscout.apply import external_ats

    assert callable(external_ats.apply)
    assert callable(external_ats._enumerate_fields)
    assert callable(external_ats._ask_llm_for_actions)
    src = (external_ats.__file__ or "").rstrip("c")
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "JOBSCOUT_CDP_URL" in text
    assert "UPWORK_CDP_URL" not in text

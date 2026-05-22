from jobscout.apply.external_ats import _candidate_context


def test_candidate_context_basic_fields():
    profile_row = {
        "full_name": "Test Candidate",
        "email": "candidate@example.test",
        "phone": "+49 000 0000000",
        "location": "Hamburg, Germany",
        "linkedin_url": "https://www.linkedin.com/in/test-candidate-fixture/",
        "years_experience": 5,
        "languages": {"German": "C2 / Muttersprache", "English": "C1"},
        "target_rate_floor_eur": 65,
    }
    ctx = _candidate_context(profile_row)
    assert ctx["candidate_name"] == "Test Candidate"
    assert ctx["candidate_email"] == "candidate@example.test"
    assert ctx["candidate_phone"] == "+49 000 0000000"
    assert ctx["candidate_location"] == "Hamburg, Germany"
    assert ctx["candidate_linkedin"].endswith("test-candidate-fixture/")
    assert ctx["years_experience"] == "5"
    assert ctx["target_rate_eur_hr"] == "65"
    assert "German: C2" in ctx["candidate_languages"]
    assert "English: C1" in ctx["candidate_languages"]


def test_candidate_context_defaults_missing_fields_empty():
    ctx = _candidate_context({"full_name": "X", "linkedin_url": "https://li.example/x"})
    assert ctx["candidate_portfolio"] == ""
    assert ctx["work_authorization"] == ""
    assert ctx["available_hours_per_week"] == ""
    assert ctx["target_rate_usd_hr"] == ""
    assert "none configured" in ctx["sensitive_defaults"]

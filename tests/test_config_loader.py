from jobscout.config_loader import load_profile, load_spam_rules


def test_load_profile_has_required_skills():
    p = load_profile()
    assert "LangChain" in p["required_skill_keywords"]
    # Floor is configurable — assert it exists and is numeric rather than
    # pinning a specific value, since the user adjusts these as the
    # LinkedIn/Upwork pool shifts.
    assert isinstance(p["target_rate_floor_eur_hr"], int | float)
    assert p["target_rate_floor_eur_hr"] > 0


def test_load_spam_rules_drop_threshold():
    r = load_spam_rules()
    assert r["spam_score_drop_threshold"] == 5
    assert "DVAG" in r["mlm_companies"]
    assert "elaborate_application" in r["hard_drop_patterns"]

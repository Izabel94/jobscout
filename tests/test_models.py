from jobscout.models import ApplyMethod, Arrangement, JobType, Listing, Source


def test_source_enum_restricted_to_linkedin_indeed():
    assert {s.value for s in Source} == {"linkedin", "indeed"}


def test_arrangement_enum():
    assert Arrangement.REMOTE.value == "remote"
    assert Arrangement.HYBRID.value == "hybrid"
    assert Arrangement.ONSITE.value == "onsite"
    assert Arrangement.UNKNOWN.value == "unknown"


def test_job_type_enum():
    assert JobType.FULLTIME.value == "fulltime"
    assert JobType.PERMANENT.value == "permanent"
    assert JobType.CONTRACT.value == "contract"
    assert JobType.PARTTIME.value == "parttime"
    assert JobType.INTERN.value == "intern"
    assert JobType.UNKNOWN.value == "unknown"


def test_apply_method_enum():
    assert ApplyMethod.EXTERNAL_APPLY.value == "external_apply"
    assert ApplyMethod.EASY_APPLY.value == "easy_apply"


def test_listing_has_new_fields():
    listing = Listing(
        source=Source.LINKEDIN,
        source_id="abc",
        url="https://linkedin.com/jobs/view/123",
        title="ML Engineer",
        raw={},
    )
    assert listing.arrangement is None
    assert listing.job_type_classified is None
    assert listing.apply_method is None
    assert listing.arrangement_evidence is None
    assert listing.job_type_evidence is None

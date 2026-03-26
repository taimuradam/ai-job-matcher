from __future__ import annotations

from app.schemas import CandidatePreferenceInput, NormalizedJob
from app.services.job_search import _job_matches_plan, _location_matches_preferences, _merge_preferences, build_search_plan
from app.services.profile_extraction import build_candidate_profile


def test_search_plan_respects_preferences_and_generates_query_families() -> None:
    candidate = build_candidate_profile(
        "resume.txt",
        """
        Python backend developer building FastAPI and SQL APIs.
        Built data dashboards and ML experiments.
        """,
    )
    preferences = CandidatePreferenceInput(
        target_roles=["backend engineer", "data analyst"],
        must_have_skills=["Python", "FastAPI"],
        excluded_roles=["sales"],
    )

    plan = build_search_plan(candidate, preferences)

    assert len(plan.exact_role_queries) >= 3
    assert len(plan.adjacent_role_queries) >= 3
    assert len(plan.stack_queries) == 2
    assert "backend engineer intern" in plan.combined_queries
    assert "junior backend engineer" in plan.combined_queries
    assert plan.excluded_roles == ["sales"]


def test_location_preferences_match_city_and_state_aliases() -> None:
    job = NormalizedJob(
        id="job-1",
        title="Backend Engineer Intern",
        normalized_title="backend engineer",
        company="Example",
        location="Hybrid - Phoenix, AZ",
        location_type="hybrid",
        location_regions=["Arizona", "United States"],
        description_text="Build backend APIs.",
        employment_type="Internship",
        seniority_band="entry-level",
        required_skills=["Python"],
        preferred_skills=[],
        domain_tags=[],
        salary_range=None,
        visa_support=None,
        published_at=None,
        job_age_days=None,
        source="Fixture",
        source_type="fixture",
        source_quality=0.8,
        apply_url=None,
    )
    preferences = CandidatePreferenceInput(
        preferred_locations=["Phoenix, Arizona"],
        remote_preference="hybrid_or_remote",
    )

    assert _location_matches_preferences(job, preferences) is True


def test_location_preferences_filter_non_matching_onsite_roles() -> None:
    job = NormalizedJob(
        id="job-2",
        title="Backend Engineer Intern",
        normalized_title="backend engineer",
        company="Example",
        location="Onsite - New York, NY",
        location_type="onsite",
        location_regions=["New York", "United States"],
        description_text="Build backend APIs.",
        employment_type="Internship",
        seniority_band="entry-level",
        required_skills=["Python"],
        preferred_skills=[],
        domain_tags=[],
        salary_range=None,
        visa_support=None,
        published_at=None,
        job_age_days=None,
        source="Fixture",
        source_type="fixture",
        source_quality=0.8,
        apply_url=None,
    )
    preferences = CandidatePreferenceInput(
        preferred_locations=["Phoenix, AZ"],
        remote_preference="onsite_friendly",
    )

    assert _location_matches_preferences(job, preferences) is False


def test_job_matching_keeps_adjacent_early_career_titles() -> None:
    candidate = build_candidate_profile(
        "resume.txt",
        """
        Python backend developer building FastAPI services and SQL APIs.
        Built platform tooling, Dockerized services, and internal developer tools.
        1 year experience through internships.
        """,
    )
    preferences = CandidatePreferenceInput(
        target_roles=["backend engineer"],
        must_have_skills=["Python", "FastAPI", "SQL"],
        remote_preference="remote_or_hybrid",
        employment_preferences=["internship"],
    )
    plan = build_search_plan(candidate, preferences)
    job = NormalizedJob(
        id="job-3",
        title="Software Engineer Intern",
        normalized_title="software engineer",
        company="Example",
        location="Remote - United States",
        location_type="remote",
        location_regions=["United States", "Remote"],
        description_text="Build backend platform APIs using Python, FastAPI, SQL, Docker, and internal tooling.",
        employment_type="Internship",
        seniority_band="entry-level",
        required_skills=["Python", "FastAPI", "SQL"],
        preferred_skills=["Docker", "Git"],
        domain_tags=["developer tools"],
        salary_range=None,
        visa_support=None,
        published_at=None,
        job_age_days=None,
        source="Fixture",
        source_type="fixture",
        source_quality=0.8,
        apply_url=None,
    )

    assert _job_matches_plan(job, candidate, plan, preferences) is True


def test_blank_manual_fields_do_not_fall_back_to_inferred_preferences() -> None:
    candidate = build_candidate_profile(
        "resume.txt",
        """
        Backend student based in Phoenix, Arizona.
        Looking for remote internships building Python APIs with FastAPI and SQL.
        """
    )
    merged = _merge_preferences(
        candidate,
        CandidatePreferenceInput(
            target_roles=[],
            preferred_locations=[],
            remote_preference=None,
            employment_preferences=[],
            must_have_skills=[],
            excluded_roles=[],
            ranking_mode="balanced",
        ),
    )

    assert merged.target_roles
    assert merged.preferred_locations == []
    assert merged.remote_preference is None
    assert merged.employment_preferences == []
    assert merged.must_have_skills == []

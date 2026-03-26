from __future__ import annotations

from pathlib import Path

from app.schemas import CandidatePreferenceInput, JobRecord, ProviderStatus, SearchPlan
from app.services.evaluation import evaluate_saved_search_case
from app.services.job_search import apply_search_funnel, build_search_plan, normalize_job
from app.services.profile_extraction import build_candidate_profile
from app.services.scoring import analyze_search_results


def test_inferred_preferences_do_not_hard_filter_without_confirmation() -> None:
    candidate = build_candidate_profile(
        "resume.txt",
        """
        Backend student based in Phoenix, Arizona.
        Building Python APIs with FastAPI and SQL.
        Looking for remote or hybrid early-career work.
        """
    )
    preferences = CandidatePreferenceInput(
        target_roles=["backend engineer"],
        preferred_locations=["Phoenix, AZ"],
        remote_preference="hybrid_or_remote",
        employment_preferences=["internship"],
        must_have_skills=["Python", "FastAPI", "SQL"],
        search_mode="broad_recall",
        confirmed_preferences={},
    )
    jobs = [
        normalize_job(
            JobRecord(
                title="Backend Engineer Intern",
                company="Phoenix Apps",
                location="Hybrid - Phoenix, AZ",
                description="Required: Python, FastAPI, SQL. Build backend APIs.",
                employment_type="Internship",
                source="Fixture",
            )
        ),
        normalize_job(
            JobRecord(
                title="Backend Developer",
                company="Remote Stack",
                location="Remote",
                description="Required: Python, APIs, SQL, Docker. Build product backend services.",
                employment_type="Full-time",
                source="Fixture",
            )
        ),
    ]

    filtered, _, diagnostics = apply_search_funnel(
        candidate=candidate,
        preferences=preferences,
        jobs=jobs,
    )

    assert len(filtered) == 2
    assert diagnostics.active_hard_filters == []


def test_low_result_runs_relax_confirmed_filters_instead_of_stopping_early() -> None:
    candidate = build_candidate_profile(
        "resume.txt",
        """
        Backend-focused student building Python APIs with FastAPI and SQL.
        1 year internship experience.
        """
    )
    preferences = CandidatePreferenceInput(
        target_roles=["backend engineer"],
        preferred_locations=["Phoenix, AZ"],
        remote_preference="onsite_friendly",
        employment_preferences=["internship"],
        must_have_skills=["Python", "FastAPI", "SQL"],
        search_mode="broad_recall",
        confirmed_preferences={
            "preferred_locations": True,
            "remote_preference": True,
            "employment_preferences": True,
        },
    )
    jobs = [
        normalize_job(
            JobRecord(
                title="Backend Engineer",
                company="Remote Stack",
                location="Remote",
                description="Required: Python, FastAPI, SQL. Build backend services.",
                employment_type="Full-time",
                source="Fixture",
            )
        ),
        normalize_job(
            JobRecord(
                title="Software Engineer Intern",
                company="Coast Labs",
                location="Remote",
                description="Build Python APIs, SQL tooling, and internal platforms.",
                employment_type="Internship",
                source="Fixture",
            )
        ),
    ]

    filtered, _, diagnostics = apply_search_funnel(
        candidate=candidate,
        preferences=preferences,
        jobs=jobs,
    )

    assert len(filtered) == 2
    assert diagnostics.fallback_triggered is True
    assert diagnostics.relaxation_steps


def test_generic_location_parsing_handles_arbitrary_city_and_state_names() -> None:
    candidate = build_candidate_profile(
        "resume.txt",
        """
        Software engineer based in Seattle, WA.
        Open to remote work and willing to work from Austin, Texas.
        Built Python and React applications.
        """
    )
    job = normalize_job(
        JobRecord(
            title="Software Engineer Intern",
            company="Windy City Apps",
            location="Hybrid - Chicago, IL",
            description="Build APIs and internal tools with Python and SQL.",
            employment_type="Internship",
            source="Fixture",
        )
    )

    assert any("Seattle" in location or "Washington" in location for location in candidate.preferred_locations)
    assert any(region in job.location_regions for region in ["Chicago, IL", "Illinois"])


def test_score_calibration_keeps_plausible_adjacent_matches_out_of_low_30s() -> None:
    candidate = build_candidate_profile(
        "resume.txt",
        """
        Python developer building FastAPI tools, SQL dashboards, and Dockerized APIs.
        Built internal platform services and developer tooling projects.
        2 years experience.
        """
    )
    preferences = CandidatePreferenceInput(
        target_roles=["backend engineer"],
        must_have_skills=["Python", "FastAPI", "SQL"],
        search_mode="broad_recall",
    )
    jobs = [
        normalize_job(
            JobRecord(
                title="Software Engineer Intern",
                company="Fit Co",
                location="Remote",
                description="Build backend APIs with Python, SQL, Docker, and internal tooling.",
                employment_type="Internship",
                source="Fixture",
            )
        ),
        normalize_job(
            JobRecord(
                title="Senior Sales Engineer",
                company="Noise Corp",
                location="Remote",
                description="Required: presentations, quota ownership, account management, 7+ years experience.",
                employment_type="Full-time",
                source="Fixture",
            )
        ),
    ]
    response = analyze_search_results(
        candidate=candidate,
        preferences=preferences,
        jobs=jobs,
        search_plan=SearchPlan(
            exact_role_queries=["backend engineer intern"],
            adjacent_role_queries=["software engineer intern"],
            stack_queries=["Python backend engineer"],
            title_synonyms=["python developer"],
            widened_role_queries=["backend developer", "api engineer"],
            excluded_roles=[],
            combined_queries=["backend engineer intern", "software engineer intern", "Python backend engineer"],
            search_mode="broad_recall",
            active_filters=[],
        ),
        provider_statuses=[
            ProviderStatus(provider="Fixture", status="ok", fetched_jobs=2, normalized_jobs=2, freshness="fixture", source_quality=0.8),
        ],
    )

    assert response.matches[0].job.title == "Software Engineer Intern"
    assert response.matches[0].score >= 46


def test_saved_regression_case_returns_broader_ranked_set() -> None:
    result = evaluate_saved_search_case(
        Path(__file__).resolve().parents[1] / "app" / "data" / "regression_saved_search_case.json"
    )

    assert result["jobs_after_funnel"] >= 10
    assert result["top_5_role_hits"] >= 3

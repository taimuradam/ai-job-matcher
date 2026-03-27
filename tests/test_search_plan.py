from __future__ import annotations

from app.copilot.fit_engine import assess_opportunity, build_action_plan
from app.copilot.schemas import CandidateProfileData, OpportunityData, SearchTargetData


def test_fit_engine_enforces_binary_eligibility_and_action_plan_generation() -> None:
    profile = CandidateProfileData(
        filename="resume.txt",
        summary="Targeting backend internships.",
        skills_confirmed=["Python", "FastAPI", "SQL"],
        skills_inferred=["Docker"],
        core_roles=["backend engineer"],
        adjacent_roles=["software engineer"],
        seniority="early-career",
        industries=[],
        preferred_locations=["Phoenix, AZ"],
        remote_preference="remote_or_hybrid",
        employment_preferences=["internship"],
        education_level=[],
        years_experience=1,
        projects=[],
        evidence=[],
        confidence={},
        signals=[],
        llm_summary="Targeting backend internships.",
    )
    target = SearchTargetData(
        target_roles=["backend engineer"],
        role_families=["backend engineer", "software engineer"],
        query_terms=["backend engineer intern", "python backend engineer"],
        preferred_locations=["Phoenix, AZ"],
        work_modes=["remote", "hybrid"],
        employment_preferences=["internship"],
        must_have_skills=["Python", "FastAPI", "SQL"],
        excluded_keywords=[],
        seniority_ceiling="entry-level",
        search_mode="balanced",
        strict_location=False,
        strict_work_mode=False,
        strict_employment=False,
        strict_must_have=False,
    )
    opportunity = OpportunityData(
        id="job-1",
        raw_listing_id=None,
        dedupe_key="job-1",
        title="Backend Engineer Intern",
        normalized_title="backend engineer",
        company="Phoenix Apps",
        location="Remote",
        location_type="remote",
        location_regions=["Remote", "United States"],
        description_text="Required: Python, FastAPI, SQL. Build APIs and platform tooling.",
        employment_type="Internship",
        seniority_band="entry-level",
        required_skills=["Python", "FastAPI", "SQL"],
        preferred_skills=["Docker"],
        domain_tags=["developer tools"],
        salary_range=None,
        visa_support=None,
        published_at=None,
        job_age_days=2,
        source="Fixture",
        source_type="fixture",
        source_quality=0.8,
        apply_url="https://example.com/backend",
    )

    assessment = assess_opportunity(profile, target, opportunity)
    plan = build_action_plan(profile, target, opportunity, assessment)

    assert assessment.eligible is True
    assert assessment.triage_decision in {"apply", "tailor"}
    assert plan is not None
    assert plan.resume_tailoring_steps


def test_strict_filters_make_mismatched_role_ineligible() -> None:
    profile = CandidateProfileData(
        filename="resume.txt",
        summary="Targeting backend internships.",
        skills_confirmed=["Python", "FastAPI", "SQL"],
        skills_inferred=[],
        core_roles=["backend engineer"],
        adjacent_roles=[],
        seniority="early-career",
        industries=[],
        preferred_locations=["Phoenix, AZ"],
        remote_preference="remote_or_hybrid",
        employment_preferences=["internship"],
        education_level=[],
        years_experience=1,
        projects=[],
        evidence=[],
        confidence={},
        signals=[],
        llm_summary="Targeting backend internships.",
    )
    target = SearchTargetData(
        target_roles=["backend engineer"],
        role_families=["backend engineer"],
        query_terms=["backend engineer intern"],
        preferred_locations=["Phoenix, AZ"],
        work_modes=["remote"],
        employment_preferences=["internship"],
        must_have_skills=["Python", "FastAPI", "SQL"],
        excluded_keywords=["sales"],
        seniority_ceiling="entry-level",
        search_mode="balanced",
        strict_location=True,
        strict_work_mode=True,
        strict_employment=True,
        strict_must_have=True,
    )
    opportunity = OpportunityData(
        id="job-2",
        raw_listing_id=None,
        dedupe_key="job-2",
        title="Senior Sales Engineer",
        normalized_title="sales engineer",
        company="Noise Corp",
        location="Onsite - New York, NY",
        location_type="onsite",
        location_regions=["New York", "United States"],
        description_text="Required: quota ownership, sales presentations, 6+ years experience.",
        employment_type="Full-time",
        seniority_band="senior",
        required_skills=["Presentations"],
        preferred_skills=[],
        domain_tags=[],
        salary_range=None,
        visa_support=None,
        published_at=None,
        job_age_days=10,
        source="Fixture",
        source_type="fixture",
        source_quality=0.7,
        apply_url=None,
    )

    assessment = assess_opportunity(profile, target, opportunity)

    assert assessment.eligible is False
    assert assessment.triage_decision == "skip"
    assert assessment.ineligibility_reasons


def test_employment_mismatch_reduces_score_without_needing_strict_mode() -> None:
    profile = CandidateProfileData(
        filename="resume.txt",
        summary="Targeting backend internships.",
        skills_confirmed=["Python", "FastAPI", "SQL"],
        skills_inferred=["Docker"],
        core_roles=["backend engineer"],
        adjacent_roles=["software engineer"],
        seniority="early-career",
        industries=[],
        preferred_locations=["Phoenix, AZ"],
        remote_preference="remote_or_hybrid",
        employment_preferences=["internship"],
        education_level=[],
        years_experience=1,
        projects=[],
        evidence=[],
        confidence={},
        signals=[],
        llm_summary="Targeting backend internships.",
    )
    target = SearchTargetData(
        target_roles=["backend engineer"],
        role_families=["backend engineer", "software engineer"],
        query_terms=["backend engineer intern", "python backend engineer"],
        preferred_locations=["Phoenix, AZ"],
        work_modes=["remote", "hybrid"],
        employment_preferences=["internship"],
        must_have_skills=["Python", "FastAPI", "SQL"],
        excluded_keywords=[],
        seniority_ceiling="entry-level",
        search_mode="balanced",
        strict_location=False,
        strict_work_mode=False,
        strict_employment=False,
        strict_must_have=False,
    )
    internship = OpportunityData(
        id="job-3",
        raw_listing_id=None,
        dedupe_key="job-3",
        title="Backend Engineer Intern",
        normalized_title="backend engineer",
        company="Phoenix Apps",
        location="Remote",
        location_type="remote",
        location_regions=["Remote", "United States"],
        description_text="Required: Python, FastAPI, SQL. Build APIs and platform tooling.",
        employment_type="Internship",
        seniority_band="entry-level",
        required_skills=["Python", "FastAPI", "SQL"],
        preferred_skills=["Docker"],
        domain_tags=["developer tools"],
        salary_range=None,
        visa_support=None,
        published_at=None,
        job_age_days=2,
        source="Fixture",
        source_type="fixture",
        source_quality=0.8,
        apply_url="https://example.com/backend-intern",
    )
    full_time = internship.model_copy(
        update={
            "id": "job-4",
            "dedupe_key": "job-4",
            "title": "Backend Engineer",
            "employment_type": "Full-time",
        }
    )

    internship_assessment = assess_opportunity(profile, target, internship)
    full_time_assessment = assess_opportunity(profile, target, full_time)

    assert internship_assessment.scores.total > full_time_assessment.scores.total
    assert any("Employment type" in line for line in full_time_assessment.explanation)

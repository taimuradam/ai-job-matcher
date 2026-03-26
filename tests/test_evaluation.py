from __future__ import annotations

from app.copilot.llm import maybe_enrich_profile, maybe_generate_action_plan
from app.copilot.schemas import ActionPlanData, CandidateProfileData


class BrokenClient:
    provider_name = "broken-llm"

    def profile_grounding(self, *, resume_text: str, profile: CandidateProfileData) -> dict:
        del resume_text
        del profile
        return {"not": "a profile"}

    def action_plan(
        self,
        *,
        profile: CandidateProfileData,
        opportunity_title: str,
        assessment_summary: str,
    ) -> dict:
        del profile
        del opportunity_title
        del assessment_summary
        return {"summary": 42}


def test_llm_profile_contract_falls_back_on_invalid_payload() -> None:
    profile = CandidateProfileData(
        filename="resume.txt",
        summary="Targeting backend internships.",
        skills_confirmed=["Python"],
        skills_inferred=[],
        core_roles=["backend engineer"],
        adjacent_roles=[],
        seniority="early-career",
        industries=[],
        preferred_locations=[],
        remote_preference="remote_or_hybrid",
        employment_preferences=[],
        education_level=[],
        years_experience=1,
        projects=[],
        evidence=[],
        confidence={},
        signals=[],
        llm_summary="Targeting backend internships.",
    )

    enriched, status = maybe_enrich_profile(
        resume_text="resume text",
        profile=profile,
        llm_client=BrokenClient(),
    )

    assert enriched == profile
    assert status.mode == "fallback"


def test_llm_action_plan_contract_falls_back_on_invalid_payload() -> None:
    profile = CandidateProfileData(
        filename="resume.txt",
        summary="Targeting backend internships.",
        skills_confirmed=["Python"],
        skills_inferred=[],
        core_roles=["backend engineer"],
        adjacent_roles=[],
        seniority="early-career",
        industries=[],
        preferred_locations=[],
        remote_preference="remote_or_hybrid",
        employment_preferences=[],
        education_level=[],
        years_experience=1,
        projects=[],
        evidence=[],
        confidence={},
        signals=[],
        llm_summary="Targeting backend internships.",
    )
    default_plan = ActionPlanData(
        generated_by="deterministic",
        summary="Worth tailoring before applying.",
        missing_requirements=["Docker"],
        strongest_evidence=["Built Python APIs."],
        resume_tailoring_steps=["Move the strongest backend project higher."],
    )

    plan = maybe_generate_action_plan(
        default_plan=default_plan,
        profile=profile,
        opportunity_title="Backend Engineer Intern",
        assessment_summary="Strong role fit with one missing skill.",
        llm_client=BrokenClient(),
    )

    assert plan == default_plan

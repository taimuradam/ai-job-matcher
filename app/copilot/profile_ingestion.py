from __future__ import annotations

from datetime import UTC, datetime

from app.copilot.llm import StructuredLLMClient, maybe_enrich_profile
from app.copilot.schemas import CandidateProfileData, EvidenceItem, LLMStatus, ProfileIngestResponse, ProjectSignal
from app.copilot.target_builder import build_search_target
from app.services.profile_extraction import build_candidate_profile


def _profile_summary(profile: CandidateProfileData) -> str:
    roles = ", ".join(profile.core_roles[:2]) or "resume-derived roles still need confirmation"
    skills = ", ".join(profile.skills_confirmed[:4] or profile.skills_inferred[:4] or ["general engineering"])
    experience = (
        f"{profile.years_experience:.1f} years of experience"
        if profile.years_experience is not None
        else "limited explicit experience markers"
    )
    return f"Targeting {roles} with strengths in {skills} and {experience}."


def ingest_resume_text(
    *,
    filename: str,
    resume_text: str,
    llm_client: StructuredLLMClient | None = None,
) -> tuple[CandidateProfileData, LLMStatus]:
    extracted = build_candidate_profile(filename, resume_text)
    profile = CandidateProfileData(
        filename=extracted.filename,
        summary=None,
        skills_confirmed=extracted.skills_confirmed,
        skills_inferred=extracted.skills_inferred,
        core_roles=extracted.core_roles,
        adjacent_roles=extracted.adjacent_roles,
        seniority=extracted.seniority,
        industries=extracted.industries,
        preferred_locations=extracted.preferred_locations,
        remote_preference=extracted.remote_preference,
        employment_preferences=extracted.employment_preferences,
        education_level=extracted.education_level,
        years_experience=extracted.years_experience,
        projects=[
            ProjectSignal(
                title=project.title,
                summary=project.summary,
                related_skills=project.related_skills,
                confidence=project.confidence,
            )
            for project in extracted.projects
        ],
        evidence=[
            EvidenceItem(
                label=evidence.label,
                detail=evidence.snippet,
                confidence=evidence.confidence,
            )
            for evidence in extracted.evidence_snippets
        ],
        confidence=extracted.confidence,
        signals=extracted.signals,
        llm_summary=None,
    )
    profile.summary = _profile_summary(profile)
    profile.llm_summary = profile.summary
    enriched_profile, llm_status = maybe_enrich_profile(
        resume_text=resume_text,
        profile=profile,
        llm_client=llm_client,
    )
    if not enriched_profile.summary:
        enriched_profile.summary = _profile_summary(enriched_profile)
    if not enriched_profile.llm_summary:
        enriched_profile.llm_summary = enriched_profile.summary
    return enriched_profile, llm_status


def build_ingest_response(
    *,
    filename: str,
    resume_text: str,
    llm_client: StructuredLLMClient | None = None,
) -> ProfileIngestResponse:
    profile, llm_status = ingest_resume_text(
        filename=filename,
        resume_text=resume_text,
        llm_client=llm_client,
    )
    return ProfileIngestResponse(
        generated_at=datetime.now(UTC),
        profile=profile,
        suggested_target=build_search_target(profile),
        llm_status=llm_status,
    )

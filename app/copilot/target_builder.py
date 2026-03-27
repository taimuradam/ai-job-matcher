from __future__ import annotations

from app.copilot.schemas import CandidateProfileData, SearchTargetData
from app.services.taxonomy import dedupe_preserve_order, expand_role_aliases, normalize_text


def _work_modes(remote_preference: str) -> list[str]:
    preference = normalize_text(remote_preference)
    if preference in {"", "unspecified", "unknown", "none"}:
        return []
    if preference == "onsite_friendly":
        return ["onsite", "hybrid", "remote"]
    if preference == "hybrid_or_remote":
        return ["hybrid", "remote"]
    return ["remote", "hybrid"]


def _seniority_ceiling(profile: CandidateProfileData) -> str:
    if profile.seniority == "early-career":
        return "mid-level" if (profile.years_experience or 0) >= 2 else "entry-level"
    if profile.seniority == "mid-level":
        return "mid-level"
    return "senior"


def _role_query_variants(role: str, seniority: str) -> list[str]:
    normalized = normalize_text(role)
    variants = [role]
    if seniority == "early-career":
        if "intern" not in normalized:
            variants.append(f"{role} intern")
        if "junior" not in normalized:
            variants.append(f"junior {role}")
        if "new grad" not in normalized:
            variants.append(f"new grad {role}")
        if "associate" not in normalized:
            variants.append(f"associate {role}")
    return dedupe_preserve_order(variants)


def build_search_target(profile: CandidateProfileData) -> SearchTargetData:
    target_roles = profile.core_roles[:3]
    role_families = dedupe_preserve_order(target_roles + profile.adjacent_roles[:4])
    query_terms: list[str] = []
    for role in role_families[:5]:
        for alias in expand_role_aliases(role):
            query_terms.extend(_role_query_variants(alias, profile.seniority))
    if profile.skills_confirmed and target_roles:
        query_terms.extend(
            f"{skill} {target_roles[0]}"
            for skill in profile.skills_confirmed[:3]
        )

    return SearchTargetData(
        target_roles=target_roles,
        role_families=role_families,
        query_terms=dedupe_preserve_order(query_terms)[:16],
        preferred_locations=profile.preferred_locations[:5],
        work_modes=_work_modes(profile.remote_preference),
        employment_preferences=profile.employment_preferences[:4],
        must_have_skills=profile.skills_confirmed[:6],
        excluded_keywords=[],
        seniority_ceiling=_seniority_ceiling(profile),
        search_mode="balanced",
    )

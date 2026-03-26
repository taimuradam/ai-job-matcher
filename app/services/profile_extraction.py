from __future__ import annotations

import re

from app.schemas import CandidateEvidence, CandidateProfile, CandidateProject
from app.services.taxonomy import (
    INDUSTRY_KEYWORDS,
    ROLE_LIBRARY,
    dedupe_preserve_order,
    extract_education,
    extract_location_mentions,
    extract_matching_lines,
    extract_resume_signals,
    extract_skills,
    extract_years_of_experience,
    expand_role_aliases,
    meaningful_tokens,
    normalize_text,
)

PROJECT_HINTS = ("project", "built", "developed", "created", "designed", "launched", "hackathon")


def _infer_roles(skills: list[str], text: str) -> tuple[list[str], list[str], dict[str, float]]:
    normalized = normalize_text(text)
    role_scores: list[tuple[str, float]] = []
    confidences: dict[str, float] = {}
    for role, profile in ROLE_LIBRARY.items():
        keywords = profile["keywords"]
        role_skills = profile["skills"]
        keyword_hits = sum(1 for keyword in keywords if keyword in normalized)
        skill_hits = len(set(skills) & set(role_skills))
        title_hits = sum(1 for alias in expand_role_aliases(role) if normalize_text(alias) in normalized)
        token_hits = sum(1 for token in role.split() if token in normalized)
        score = keyword_hits * 0.26 + skill_hits * 0.22 + title_hits * 0.14 + token_hits * 0.08
        if score > 0:
            role_scores.append((role, score))
            confidences[role] = min(0.35 + score / 5.0, 0.94)

    ranked = [role for role, _ in sorted(role_scores, key=lambda item: item[1], reverse=True)]
    core_roles = ranked[:3] or ["software engineer"]

    adjacent_roles: list[str] = []
    for role in core_roles:
        role_profile = ROLE_LIBRARY.get(role, {})
        adjacent_roles.extend(role_profile.get("adjacent", []))
    adjacent_roles = dedupe_preserve_order(adjacent_roles)[:4]
    return core_roles, adjacent_roles, confidences


def _infer_seniority(text: str, years_experience: float | None) -> tuple[str, float]:
    normalized = normalize_text(text)
    if any(term in normalized for term in ("intern", "student", "new grad", "new graduate", "entry level")):
        return "early-career", 0.9
    if years_experience is None:
        return "early-career", 0.65
    if years_experience < 3:
        return "early-career", 0.88
    if years_experience < 6:
        return "mid-level", 0.82
    return "senior", 0.84


def _infer_industries(text: str) -> list[str]:
    normalized = normalize_text(text)
    matches = [
        industry
        for industry, keywords in INDUSTRY_KEYWORDS.items()
        if any(keyword in normalized for keyword in keywords)
    ]
    return matches[:3]


def _infer_remote_preference(text: str) -> tuple[str, float]:
    normalized = normalize_text(text)
    if "onsite" in normalized or "on-site" in normalized:
        return "onsite_friendly", 0.7
    if "hybrid" in normalized:
        return "hybrid_or_remote", 0.72
    if "remote" in normalized:
        return "remote_or_hybrid", 0.76
    return "remote_or_hybrid", 0.48


def _infer_locations(text: str) -> list[str]:
    lines = extract_matching_lines(
        text,
        {"based in", "located in", "location", "remote", "hybrid"},
        limit=4,
    )
    locations = extract_location_mentions(text, limit=5)
    for line in lines:
        cleaned = re.sub(r"\s+", " ", line).strip(" -")
        if len(cleaned) <= 80:
            locations.append(cleaned)
    return dedupe_preserve_order(locations)[:4]


def _infer_employment_preferences(text: str, seniority: str) -> list[str]:
    normalized = normalize_text(text)
    preferences: list[str] = []
    if "intern" in normalized or "internship" in normalized:
        preferences.append("internship")
    if "new grad" in normalized or "new graduate" in normalized:
        preferences.append("new_grad")
    if "contract" in normalized:
        preferences.append("contract")
    if "full-time" in normalized or "full time" in normalized:
        preferences.append("full_time")

    if not preferences:
        if seniority == "early-career":
            preferences = ["internship", "new_grad", "full_time"]
        else:
            preferences = ["full_time"]
    return dedupe_preserve_order(preferences)


def _infer_implied_skills(skills: list[str], core_roles: list[str], text: str) -> list[str]:
    normalized = normalize_text(text)
    inferred: list[str] = []
    if "dashboard" in normalized and "Data Visualization" not in skills:
        inferred.append("Data Visualization")
    if "api" in normalized and "REST APIs" not in skills:
        inferred.append("REST APIs")
    if "llm" in normalized and "OpenAI API" not in skills:
        inferred.append("OpenAI API")
    if "prompt" in normalized and "Prompt Engineering" not in skills:
        inferred.append("Prompt Engineering")
    if "evaluation" in normalized and "LLM Evaluation" not in skills:
        inferred.append("LLM Evaluation")
    if "pipeline" in normalized and "ETL" not in skills:
        inferred.append("ETL")
    if "airflow" in normalized and "Airflow" not in skills:
        inferred.append("Airflow")
    if "terraform" in normalized and "Terraform" not in skills:
        inferred.append("Terraform")
    if "graphql" in normalized and "GraphQL" not in skills:
        inferred.append("GraphQL")
    for role in core_roles:
        role_profile = ROLE_LIBRARY.get(role, {})
        for role_skill in role_profile.get("skills", set()):
            if role_skill not in skills:
                inferred.append(role_skill)
    return dedupe_preserve_order(inferred)[:6]


def _extract_projects(text: str, skills: list[str]) -> list[CandidateProject]:
    projects: list[CandidateProject] = []
    lines = [line.strip(" -") for line in text.splitlines() if line.strip()]
    for line in lines:
        lowered = normalize_text(line)
        if not any(hint in lowered for hint in PROJECT_HINTS):
            continue
        project_skills = [skill for skill in skills if normalize_text(skill) in lowered]
        title = line[:72]
        if len(title) < 12:
            title = "Resume project evidence"
        projects.append(
            CandidateProject(
                title=title,
                summary=line[:180],
                related_skills=project_skills[:5],
                confidence=0.72 if project_skills else 0.58,
            )
        )
        if len(projects) == 4:
            break
    return projects


def _build_evidence(
    text: str,
    core_roles: list[str],
    skills: list[str],
    inferred_skills: list[str],
) -> list[CandidateEvidence]:
    evidence: list[CandidateEvidence] = []
    for role in core_roles[:3]:
        keywords = set(role.split())
        for snippet in extract_matching_lines(text, keywords, limit=1):
            evidence.append(CandidateEvidence(label=f"Role evidence: {role}", snippet=snippet, confidence=0.78))
    for skill in skills[:4]:
        for snippet in extract_matching_lines(text, {normalize_text(skill)}, limit=1):
            evidence.append(CandidateEvidence(label=f"Confirmed skill: {skill}", snippet=snippet, confidence=0.86))
    for skill in inferred_skills[:2]:
        for snippet in extract_matching_lines(text, meaningful_tokens(skill), limit=1):
            evidence.append(CandidateEvidence(label=f"Inferred skill: {skill}", snippet=snippet, confidence=0.52))
    return evidence[:8]


def build_candidate_profile(filename: str, resume_text: str) -> CandidateProfile:
    confirmed_skills = extract_skills(resume_text)
    years_experience = extract_years_of_experience(resume_text)
    education_level = extract_education(resume_text)
    core_roles, adjacent_roles, role_confidence = _infer_roles(confirmed_skills, resume_text)
    seniority, seniority_confidence = _infer_seniority(resume_text, years_experience)
    skills_inferred = _infer_implied_skills(confirmed_skills, core_roles, resume_text)
    projects = _extract_projects(resume_text, confirmed_skills + skills_inferred)
    remote_preference, remote_confidence = _infer_remote_preference(resume_text)
    evidence = _build_evidence(resume_text, core_roles, confirmed_skills, skills_inferred)

    confidence = {
        "core_roles": max(role_confidence.values(), default=0.42),
        "adjacent_roles": 0.67 if adjacent_roles else 0.35,
        "seniority": seniority_confidence,
        "skills_confirmed": 0.92 if confirmed_skills else 0.22,
        "skills_inferred": 0.56 if skills_inferred else 0.28,
        "remote_preference": remote_confidence,
        "projects": 0.74 if projects else 0.33,
    }

    return CandidateProfile(
        filename=filename,
        skills_confirmed=confirmed_skills,
        skills_inferred=skills_inferred,
        core_roles=core_roles,
        adjacent_roles=adjacent_roles,
        seniority=seniority,
        industries=_infer_industries(resume_text),
        preferred_locations=_infer_locations(resume_text),
        remote_preference=remote_preference,
        employment_preferences=_infer_employment_preferences(resume_text, seniority),
        education_level=education_level,
        years_experience=years_experience,
        projects=projects,
        evidence_snippets=evidence,
        confidence=confidence,
        signals=extract_resume_signals(resume_text),
    )

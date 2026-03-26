from __future__ import annotations

import hashlib
import re
import time
from collections import Counter
from dataclasses import dataclass, field

import httpx

from app.schemas import (
    CandidatePreferenceInput,
    CandidateProfile,
    JobRecord,
    NormalizedJob,
    ProviderStatus,
    SearchDiagnostics,
    SearchPlan,
)
from app.services.taxonomy import (
    INDUSTRY_KEYWORDS,
    REGION_KEYWORDS,
    ROLE_LIBRARY,
    STATE_ABBREVIATIONS,
    cosine_similarity,
    dedupe_preserve_order,
    expand_role_aliases,
    extract_location_mentions,
    extract_skills,
    meaningful_tokens,
    normalize_text,
    parse_iso_age_days,
)


class JobSearchError(ValueError):
    """Raised when live job discovery cannot produce any results."""


@dataclass
class JobSearchResult:
    jobs: list[NormalizedJob]
    search_plan: SearchPlan
    provider_statuses: list[ProviderStatus]
    diagnostics: SearchDiagnostics = field(default_factory=SearchDiagnostics)


@dataclass(frozen=True)
class _SearchAttempt:
    apply_location: bool
    apply_employment: bool
    max_stage: int
    min_relevance_hits: int
    relaxation_note: str | None = None


_CACHE_TTL_SECONDS = 600
_PROVIDER_CACHE: dict[tuple[str, str], tuple[float, object]] = {}
_SOURCE_QUALITY = {
    "Remotive": 0.74,
    "RemoteOK": 0.68,
}
_SEARCH_MODE_SETTINGS = {
    "broad_recall": {
        "query_limit": 16,
        "max_stage": 2,
        "min_relevance_hits": 1,
        "min_results": 10,
        "remotive_limit": 30,
    },
    "balanced": {
        "query_limit": 12,
        "max_stage": 2,
        "min_relevance_hits": 2,
        "min_results": 6,
        "remotive_limit": 24,
    },
    "high_precision": {
        "query_limit": 8,
        "max_stage": 1,
        "min_relevance_hits": 2,
        "min_results": 4,
        "remotive_limit": 20,
    },
}


def _cache_get(key: tuple[str, str]) -> object | None:
    cached = _PROVIDER_CACHE.get(key)
    if cached is None:
        return None
    created_at, value = cached
    if time.time() - created_at > _CACHE_TTL_SECONDS:
        _PROVIDER_CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: tuple[str, str], value: object) -> None:
    _PROVIDER_CACHE[key] = (time.time(), value)


def _clean_list(items: list[str]) -> list[str]:
    return dedupe_preserve_order([item.strip() for item in items if item and item.strip()])


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _search_mode(preferences: CandidatePreferenceInput | None) -> str:
    mode = normalize_text(preferences.search_mode if preferences else "broad_recall")
    return mode if mode in _SEARCH_MODE_SETTINGS else "broad_recall"


def _is_confirmed(preferences: CandidatePreferenceInput, key: str) -> bool:
    return bool((preferences.confirmed_preferences or {}).get(key))


def _active_hard_filters(preferences: CandidatePreferenceInput) -> list[str]:
    active: list[str] = []
    if _is_confirmed(preferences, "preferred_locations") and preferences.preferred_locations:
        active.append("preferred_locations")
    if _is_confirmed(preferences, "remote_preference") and preferences.remote_preference:
        active.append("remote_preference")
    if _is_confirmed(preferences, "employment_preferences") and preferences.employment_preferences:
        active.append("employment_preferences")
    if preferences.excluded_roles:
        active.append("excluded_roles")
    return active


def _merge_preferences(
    candidate: CandidateProfile,
    preferences: CandidatePreferenceInput | None,
) -> CandidatePreferenceInput:
    if preferences is None:
        return CandidatePreferenceInput(
            target_roles=candidate.core_roles[:3],
            preferred_locations=candidate.preferred_locations[:4],
            remote_preference=candidate.remote_preference,
            employment_preferences=candidate.employment_preferences,
            must_have_skills=candidate.skills_confirmed[:5],
            excluded_roles=[],
            ranking_mode="balanced",
            search_mode="broad_recall",
            confirmed_preferences={},
        )

    cleaned_target_roles = _clean_list(preferences.target_roles)
    return CandidatePreferenceInput(
        target_roles=cleaned_target_roles or candidate.core_roles[:3] or ["software engineer"],
        preferred_locations=_clean_list(preferences.preferred_locations),
        remote_preference=_clean_optional_text(preferences.remote_preference),
        employment_preferences=_clean_list(preferences.employment_preferences),
        must_have_skills=_clean_list(preferences.must_have_skills),
        excluded_roles=_clean_list(preferences.excluded_roles),
        ranking_mode=preferences.ranking_mode or "balanced",
        search_mode=_search_mode(preferences),
        confirmed_preferences=dict(preferences.confirmed_preferences or {}),
    )


def _entry_level_variant(role: str, seniority: str) -> str:
    normalized = normalize_text(role)
    if seniority != "early-career":
        return role
    if any(term in normalized for term in ("intern", "junior", "entry", "new grad", "associate")):
        return role
    return f"{role} intern"


def _role_query_variants(role: str, seniority: str) -> list[str]:
    normalized = normalize_text(role)
    variants = [role]
    if seniority == "early-career":
        if "intern" not in normalized:
            variants.append(f"{role} intern")
        if "junior" not in normalized:
            variants.append(f"junior {role}")
        if "associate" not in normalized:
            variants.append(f"associate {role}")
        if "new grad" not in normalized and "graduate" not in normalized:
            variants.append(f"new grad {role}")
    return dedupe_preserve_order(variants)


def _expanded_role_queries(roles: list[str], seniority: str) -> list[str]:
    queries: list[str] = []
    for role in roles:
        for alias in expand_role_aliases(role):
            queries.extend(_role_query_variants(alias, seniority))
    return dedupe_preserve_order(queries)


def build_search_plan(
    candidate: CandidateProfile,
    preferences: CandidatePreferenceInput | None = None,
) -> SearchPlan:
    merged = _merge_preferences(candidate, preferences)
    settings = _SEARCH_MODE_SETTINGS[_search_mode(merged)]
    target_roles = merged.target_roles or candidate.core_roles or ["software engineer"]
    excluded_roles = {normalize_text(item) for item in merged.excluded_roles}
    adjacent_roles = [
        role for role in candidate.adjacent_roles
        if normalize_text(role) not in excluded_roles
    ]

    exact_queries = _expanded_role_queries(target_roles[:3], candidate.seniority)[:6]
    if not exact_queries and target_roles:
        exact_queries = [_entry_level_variant(target_roles[0], candidate.seniority)]

    adjacent_queries = _expanded_role_queries(adjacent_roles[:3], candidate.seniority)[:6]

    stack_queries: list[str] = []
    base_role = target_roles[0] if target_roles else "software engineer"
    stack_seed = merged.must_have_skills[:3] or candidate.skills_confirmed[:2]
    for skill in stack_seed:
        stack_queries.append(f"{skill} {base_role}")

    title_synonyms: list[str] = []
    for role in target_roles[:3]:
        role_profile = ROLE_LIBRARY.get(normalize_text(role), ROLE_LIBRARY.get(role))
        if isinstance(role_profile, dict):
            title_synonyms.extend(role_profile.get("synonyms", []))
    title_synonyms = dedupe_preserve_order(title_synonyms)[:6]

    widened_role_queries = dedupe_preserve_order(
        _expanded_role_queries(target_roles[:3] + adjacent_roles[:3] + title_synonyms[:3], candidate.seniority)
    )[:10]

    combined = dedupe_preserve_order(
        exact_queries + adjacent_queries + stack_queries + title_synonyms + widened_role_queries
    )[: settings["query_limit"]]
    return SearchPlan(
        exact_role_queries=dedupe_preserve_order(exact_queries),
        adjacent_role_queries=dedupe_preserve_order(adjacent_queries),
        stack_queries=dedupe_preserve_order(stack_queries),
        title_synonyms=title_synonyms,
        widened_role_queries=widened_role_queries,
        excluded_roles=merged.excluded_roles,
        combined_queries=combined,
        search_mode=_search_mode(merged),
        active_filters=_active_hard_filters(merged),
    )


def _resume_query_keywords(candidate: CandidateProfile, plan: SearchPlan, preferences: CandidatePreferenceInput) -> set[str]:
    keywords = {
        token
        for query in plan.combined_queries + plan.widened_role_queries
        for token in meaningful_tokens(query)
    }
    keywords.update(normalize_text(skill) for skill in candidate.skills_confirmed[:8])
    keywords.update(normalize_text(skill) for skill in candidate.skills_inferred[:6])
    keywords.update(normalize_text(skill) for skill in preferences.must_have_skills[:5])
    return {keyword for keyword in keywords if keyword}


def _candidate_search_blob(candidate: CandidateProfile, plan: SearchPlan) -> str:
    return "\n".join(
        [
            " ".join(candidate.core_roles),
            " ".join(candidate.adjacent_roles),
            " ".join(plan.title_synonyms),
            " ".join(candidate.skills_confirmed),
            " ".join(candidate.skills_inferred),
            " ".join(project.summary for project in candidate.projects),
            " ".join(candidate.signals),
        ]
    )


def _relevance_signal(
    job: NormalizedJob,
    candidate: CandidateProfile,
    plan: SearchPlan,
    preferences: CandidatePreferenceInput,
) -> tuple[int, float]:
    normalized = normalize_text(
        f"{job.title}\n{job.normalized_title}\n{job.description_text}\n{' '.join(job.required_skills)}\n{' '.join(job.preferred_skills)}"
    )
    keywords = _resume_query_keywords(candidate, plan, preferences)
    hits = sum(1 for keyword in keywords if keyword in normalized)
    role_tokens = meaningful_tokens(
        " ".join(candidate.core_roles + candidate.adjacent_roles + plan.title_synonyms + plan.widened_role_queries)
    )
    if any(token in normalized for token in role_tokens):
        hits += 1
    semantic = cosine_similarity(_candidate_search_blob(candidate, plan), f"{job.title}\n{job.description_text}")
    return hits, semantic


def _looks_relevant(
    job: NormalizedJob,
    candidate: CandidateProfile,
    plan: SearchPlan,
    preferences: CandidatePreferenceInput,
    *,
    min_hits: int,
) -> bool:
    normalized = normalize_text(f"{job.title} {job.description_text}")
    if any(normalize_text(role) in normalized for role in preferences.excluded_roles):
        return False
    hits, semantic = _relevance_signal(job, candidate, plan, preferences)
    return hits >= min_hits or semantic >= 0.23 or (hits >= 1 and semantic >= 0.14)


async def _fetch_remotive_jobs(client: httpx.AsyncClient, query: str, *, limit: int) -> list[JobRecord]:
    cache_key = ("Remotive", f"{query}:{limit}")
    cached = _cache_get(cache_key)
    if isinstance(cached, list):
        return cached

    response = await client.get(
        "https://remotive.com/api/remote-jobs",
        params={"search": query, "limit": limit},
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("jobs", [])
    jobs: list[JobRecord] = []
    for item in items:
        title = (item.get("title") or "").strip()
        description = (item.get("description") or "").strip()
        if not title or not description:
            continue
        jobs.append(
            JobRecord(
                title=title,
                company=(item.get("company_name") or "Unknown").strip(),
                location=(item.get("candidate_required_location") or "Remote").strip(),
                description=description,
                employment_type=(item.get("job_type") or "").strip() or None,
                url=(item.get("url") or "").strip() or None,
                source="Remotive",
                source_type="api",
                published_at=(item.get("publication_date") or "").strip() or None,
            )
        )
    _cache_set(cache_key, jobs)
    return jobs


async def _fetch_remoteok_jobs(client: httpx.AsyncClient) -> list[JobRecord]:
    cache_key = ("RemoteOK", "feed")
    cached = _cache_get(cache_key)
    if isinstance(cached, list):
        return cached

    response = await client.get(
        "https://remoteok.com/api",
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    jobs: list[JobRecord] = []
    if not isinstance(payload, list):
        return jobs

    for item in payload:
        if not isinstance(item, dict):
            continue
        title = (item.get("position") or item.get("title") or "").strip()
        description = (item.get("description") or "").strip()
        if not title or not description:
            continue
        jobs.append(
            JobRecord(
                title=title,
                company=(item.get("company") or "Unknown").strip(),
                location=(item.get("location") or "Remote").strip(),
                description=description,
                employment_type=(item.get("employment_type") or "").strip() or None,
                url=(item.get("url") or item.get("apply_url") or "").strip() or None,
                source="RemoteOK",
                source_type="api",
                published_at=(item.get("date") or "").strip() or None,
            )
        )
    _cache_set(cache_key, jobs)
    return jobs


def _normalize_title(title: str) -> str:
    normalized = normalize_text(title)
    normalized = re.sub(r"\b(senior|sr\.?|staff|principal|lead|intern|junior|jr\.?|associate)\b", "", normalized)
    normalized = normalized.replace("fullstack", "full stack")
    normalized = normalized.replace("backend developer", "backend engineer")
    normalized = normalized.replace("frontend developer", "frontend engineer")
    normalized = normalized.replace("software developer", "software engineer")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _location_aliases(value: str) -> set[str]:
    normalized = normalize_text(value)
    aliases = {normalized}
    aliases.update(part.strip() for part in re.split(r"[,/|-]+", normalized) if part.strip())
    aliases.update(token for token in re.findall(r"[a-z]{2,}", normalized))
    for token in list(aliases):
        if token in STATE_ABBREVIATIONS:
            aliases.add(STATE_ABBREVIATIONS[token])
        for abbreviation, full_name in STATE_ABBREVIATIONS.items():
            if token == full_name:
                aliases.add(abbreviation)
    return {alias for alias in aliases if alias}


def _infer_location_type(location: str, text: str) -> str:
    combined = normalize_text(f"{location} {text}")
    if "hybrid" in combined:
        return "hybrid"
    if "remote" in combined or "work from home" in combined or "anywhere" in combined:
        return "remote"
    if location and normalize_text(location) not in {"", "not specified"}:
        return "onsite"
    return "unknown"


def _infer_location_regions(location: str, text: str) -> list[str]:
    combined = normalize_text(f"{location} {text}")
    regions = [label for key, label in REGION_KEYWORDS.items() if re.search(rf"(?<![a-z]){re.escape(key)}(?![a-z])", combined)]
    regions.extend(extract_location_mentions(f"{location}\n{text}", limit=8))
    for alias, expanded in STATE_ABBREVIATIONS.items():
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", combined) or expanded in combined:
            regions.append(expanded.title())
    return dedupe_preserve_order(regions)


def _infer_seniority_band(title: str, text: str) -> str:
    combined = normalize_text(f"{title} {text}")
    if any(term in combined for term in ("intern", "new grad", "entry level", "entry-level", "recent graduate", "0-2 years", "0 to 2 years", "associate", "junior", "jr")):
        return "entry-level"
    if any(term in combined for term in ("senior", "staff", "principal", "lead", "manager", "5+ years", "6+ years", "7+ years")):
        return "senior"
    if any(term in combined for term in ("3+ years", "4+ years", "mid-level", "mid level")):
        return "mid-level"
    return "entry-level"


def _extract_required_and_preferred_skills(text: str) -> tuple[list[str], list[str]]:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    required: list[str] = []
    preferred: list[str] = []
    for sentence in sentences:
        skills = extract_skills(sentence)
        if not skills:
            continue
        normalized = normalize_text(sentence)
        if any(marker in normalized for marker in ("required", "must have", "need", "experience with", "proficient in", "requirements", "what you'll bring", "you have")):
            required.extend(skills)
        elif any(marker in normalized for marker in ("nice to have", "bonus", "preferred", "plus", "helpful", "ideally")):
            preferred.extend(skills)

    all_skills = extract_skills(text)
    if not required:
        required = all_skills[:5]
    preferred.extend(skill for skill in all_skills if skill not in required)
    return dedupe_preserve_order(required)[:6], dedupe_preserve_order(preferred)[:6]


def _infer_domain_tags(text: str) -> list[str]:
    normalized = normalize_text(text)
    return [
        industry
        for industry, keywords in INDUSTRY_KEYWORDS.items()
        if any(keyword in normalized for keyword in keywords)
    ][:4]


def _parse_salary_range(text: str) -> str | None:
    match = re.search(r"(\$[\d,]+(?:\.\d+)?\s*(?:-|to)\s*\$[\d,]+(?:\.\d+)?)", text)
    if match:
        return match.group(1)
    return None


def _infer_visa_support(text: str) -> str | None:
    normalized = normalize_text(text)
    if "visa sponsorship" in normalized or "sponsorship available" in normalized:
        return "available"
    if "no sponsorship" in normalized or "unable to sponsor" in normalized:
        return "not available"
    return None


def normalize_job(job: JobRecord) -> NormalizedJob:
    required_skills, preferred_skills = _extract_required_and_preferred_skills(job.description)
    description_text = re.sub(r"<[^>]+>", " ", job.description)
    description_text = re.sub(r"\s+", " ", description_text).strip()
    completeness = sum(
        1
        for value in (
            job.company,
            job.location,
            description_text,
            job.employment_type,
            job.published_at,
            job.url,
        )
        if value
    )
    age_days = parse_iso_age_days(job.published_at)
    freshness_penalty = 0.0 if age_days is None else min(age_days / 60.0, 0.16)
    base_quality = _SOURCE_QUALITY.get(job.source, 0.62)
    source_quality = max(min(base_quality + completeness * 0.03 - freshness_penalty, 0.98), 0.35)
    raw_identifier = "|".join(
        [
            job.source,
            job.company,
            job.title,
            job.url or "",
            job.published_at or "",
        ]
    )
    job_id = hashlib.sha1(raw_identifier.encode("utf-8")).hexdigest()[:16]

    return NormalizedJob(
        id=job_id,
        title=job.title,
        normalized_title=_normalize_title(job.title),
        company=job.company,
        location=job.location,
        location_type=_infer_location_type(job.location, description_text),
        location_regions=_infer_location_regions(job.location, description_text),
        description_text=description_text,
        employment_type=job.employment_type,
        seniority_band=_infer_seniority_band(job.title, description_text),
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        domain_tags=_infer_domain_tags(description_text),
        salary_range=_parse_salary_range(description_text),
        visa_support=_infer_visa_support(description_text),
        published_at=job.published_at,
        job_age_days=age_days,
        source=job.source,
        source_type=job.source_type,
        source_quality=source_quality,
        apply_url=job.url,
    )


def _role_stage(
    job: NormalizedJob,
    candidate: CandidateProfile,
    plan: SearchPlan,
    preferences: CandidatePreferenceInput,
) -> int | None:
    combined = normalize_text(
        " ".join(
            [
                job.title,
                job.normalized_title,
                job.description_text,
                " ".join(job.required_skills),
                " ".join(job.preferred_skills),
            ]
        )
    )
    if any(normalize_text(role) in combined for role in preferences.excluded_roles):
        return None
    if candidate.seniority == "early-career" and job.seniority_band == "senior":
        return None

    title_text = normalize_text(f"{job.title} {job.normalized_title}")
    exact_hits = sum(1 for role in preferences.target_roles or candidate.core_roles if normalize_text(role) in title_text)
    adjacent_hits = sum(1 for role in candidate.adjacent_roles if normalize_text(role) in title_text)
    synonym_hits = sum(1 for synonym in plan.title_synonyms if normalize_text(synonym) in title_text)
    widened_hits = sum(1 for variant in plan.widened_role_queries if normalize_text(variant) in title_text)
    query_hits = sum(1 for query in plan.combined_queries if normalize_text(query) in combined)
    skill_hits = sum(
        1
        for skill in (candidate.skills_confirmed + candidate.skills_inferred + preferences.must_have_skills)
        if normalize_text(skill) in combined
    )
    title_semantic = max(
        (
            cosine_similarity(job.normalized_title or job.title, role)
            for role in preferences.target_roles + candidate.adjacent_roles + plan.title_synonyms + plan.widened_role_queries
        ),
        default=0.0,
    )
    body_semantic = cosine_similarity(_candidate_search_blob(candidate, plan), f"{job.title}\n{job.description_text}")

    if exact_hits:
        return 1
    if adjacent_hits or synonym_hits or widened_hits or title_semantic >= 0.48 or (query_hits >= 1 and skill_hits >= 1):
        return 2
    if title_semantic >= 0.20 or body_semantic >= 0.16 or skill_hits >= 2 or query_hits >= 1:
        return 3
    return None


def _job_matches_plan(
    job: NormalizedJob,
    candidate: CandidateProfile,
    plan: SearchPlan,
    preferences: CandidatePreferenceInput,
) -> bool:
    stage = _role_stage(job, candidate, plan, preferences)
    return stage is not None and stage <= 3


def _location_matches_preferences(job: NormalizedJob, preferences: CandidatePreferenceInput) -> bool:
    preferred_locations = preferences.preferred_locations
    remote_preference = preferences.remote_preference or "remote_or_hybrid"
    if job.location_type == "remote":
        return remote_preference in {"remote_or_hybrid", "hybrid_or_remote", "onsite_friendly"}
    if job.location_type == "hybrid" and remote_preference in {"remote_or_hybrid", "hybrid_or_remote"} and not preferred_locations:
        return True
    if not preferred_locations:
        return True

    job_aliases = _location_aliases(job.location)
    for region in job.location_regions:
        job_aliases.update(_location_aliases(region))
    for preferred in preferred_locations:
        preferred_aliases = _location_aliases(preferred)
        if preferred_aliases & job_aliases:
            return True
        if any(alias in normalize_text(job.location) for alias in preferred_aliases if len(alias) > 2):
            return True
    return False


def _employment_matches_preferences(job: NormalizedJob, preferences: CandidatePreferenceInput) -> bool:
    if not preferences.employment_preferences:
        return True
    employment_type = normalize_text(job.employment_type or "")
    title_text = normalize_text(job.title)
    description_text = normalize_text(job.description_text)
    combined = f"{employment_type} {title_text} {description_text}"
    for preference in preferences.employment_preferences:
        normalized = normalize_text(preference).replace("_", " ")
        if normalized in combined:
            return True
        if normalized == "new grad" and any(term in combined for term in ("new grad", "recent graduate", "graduate program")):
            return True
        if normalized == "full time" and "full-time" in combined:
            return True
    return False


def _dedupe_jobs(jobs: list[NormalizedJob]) -> list[NormalizedJob]:
    deduped: list[NormalizedJob] = []
    seen: set[tuple[str, str, str, str]] = set()
    for job in jobs:
        key = (
            job.normalized_title,
            normalize_text(job.company),
            normalize_text(job.location),
            normalize_text(job.apply_url or ""),
        )
        if key in seen:
            continue
        near_duplicate = next(
            (
                existing
                for existing in deduped
                if existing.normalized_title == job.normalized_title
                and normalize_text(existing.company) == normalize_text(job.company)
                and normalize_text(existing.location) == normalize_text(job.location)
                and existing.description_text[:220] == job.description_text[:220]
            ),
            None,
        )
        if near_duplicate is not None:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped


def _search_attempts(preferences: CandidatePreferenceInput) -> list[_SearchAttempt]:
    settings = _SEARCH_MODE_SETTINGS[_search_mode(preferences)]
    apply_location = any(
        _is_confirmed(preferences, key)
        for key in ("preferred_locations", "remote_preference")
    ) and bool(preferences.preferred_locations or preferences.remote_preference)
    apply_employment = _is_confirmed(preferences, "employment_preferences") and bool(preferences.employment_preferences)

    attempts = [
        _SearchAttempt(
            apply_location=apply_location,
            apply_employment=apply_employment,
            max_stage=settings["max_stage"],
            min_relevance_hits=settings["min_relevance_hits"],
        )
    ]
    if apply_location:
        attempts.append(
            _SearchAttempt(
                apply_location=False,
                apply_employment=apply_employment,
                max_stage=settings["max_stage"],
                min_relevance_hits=settings["min_relevance_hits"],
                relaxation_note="Relaxed location hard filter because too few jobs survived the initial funnel.",
            )
        )
    if apply_employment:
        previous = attempts[-1]
        attempts.append(
            _SearchAttempt(
                apply_location=previous.apply_location,
                apply_employment=False,
                max_stage=previous.max_stage,
                min_relevance_hits=previous.min_relevance_hits,
                relaxation_note="Relaxed employment-type hard filter because recall was still too low.",
            )
        )
    if settings["max_stage"] < 3:
        previous = attempts[-1]
        attempts.append(
            _SearchAttempt(
                apply_location=previous.apply_location,
                apply_employment=previous.apply_employment,
                max_stage=3,
                min_relevance_hits=previous.min_relevance_hits,
                relaxation_note="Relaxed title strictness to include adjacent and transferable matches.",
            )
        )
    if settings["min_relevance_hits"] > 1:
        previous = attempts[-1]
        attempts.append(
            _SearchAttempt(
                apply_location=previous.apply_location,
                apply_employment=previous.apply_employment,
                max_stage=previous.max_stage,
                min_relevance_hits=1,
                relaxation_note="Relaxed relevance threshold so plausible matches can be ranked instead of dropped.",
            )
        )
    return attempts


def apply_search_funnel(
    candidate: CandidateProfile,
    preferences: CandidatePreferenceInput | None,
    jobs: list[NormalizedJob],
    *,
    search_plan: SearchPlan | None = None,
    fetched_jobs: int | None = None,
) -> tuple[list[NormalizedJob], SearchPlan, SearchDiagnostics]:
    merged = _merge_preferences(candidate, preferences)
    plan = search_plan or build_search_plan(candidate, merged)
    settings = _SEARCH_MODE_SETTINGS[_search_mode(merged)]
    deduped_jobs = _dedupe_jobs(jobs)
    relaxation_steps: list[str] = []
    final_jobs: list[NormalizedJob] = []
    final_diagnostics = SearchDiagnostics(
        fetched_jobs=fetched_jobs or len(jobs),
        normalized_jobs=len(jobs),
        deduped_jobs=len(deduped_jobs),
        active_hard_filters=_active_hard_filters(merged),
    )

    attempts = _search_attempts(merged)
    for attempt_index, attempt in enumerate(attempts):
        role_jobs: list[NormalizedJob] = []
        location_jobs: list[NormalizedJob] = []
        employment_jobs: list[NormalizedJob] = []
        relevance_jobs: list[NormalizedJob] = []
        rejected = Counter()

        for job in deduped_jobs:
            stage = _role_stage(job, candidate, plan, merged)
            if stage is None or stage > attempt.max_stage:
                rejected["role"] += 1
                continue
            role_jobs.append(job)

            if attempt.apply_location and not _location_matches_preferences(job, merged):
                rejected["location"] += 1
                continue
            location_jobs.append(job)

            if attempt.apply_employment and not _employment_matches_preferences(job, merged):
                rejected["employment"] += 1
                continue
            employment_jobs.append(job)

            if not _looks_relevant(job, candidate, plan, merged, min_hits=attempt.min_relevance_hits):
                rejected["relevance"] += 1
                continue
            relevance_jobs.append(job)

        final_jobs = relevance_jobs
        final_diagnostics = SearchDiagnostics(
            fetched_jobs=fetched_jobs or len(jobs),
            normalized_jobs=len(jobs),
            deduped_jobs=len(deduped_jobs),
            role_filtered_jobs=len(role_jobs),
            location_filtered_jobs=len(location_jobs),
            employment_filtered_jobs=len(employment_jobs),
            relevance_filtered_jobs=len(relevance_jobs),
            final_ranked_jobs=len(relevance_jobs),
            rejected_counts={
                "role": rejected["role"],
                "location": rejected["location"],
                "employment": rejected["employment"],
                "relevance": rejected["relevance"],
            },
            relaxation_steps=relaxation_steps[:],
            active_hard_filters=_active_hard_filters(merged),
            fallback_triggered=bool(relaxation_steps),
        )
        if len(relevance_jobs) >= settings["min_results"] or attempt_index == len(attempts) - 1:
            break
        next_attempt = attempts[attempt_index + 1]
        if next_attempt.relaxation_note:
            relaxation_steps.append(next_attempt.relaxation_note)

    final_diagnostics.relaxation_steps = relaxation_steps
    final_diagnostics.fallback_triggered = bool(relaxation_steps)
    return final_jobs, plan, final_diagnostics


async def fetch_matching_jobs(
    candidate: CandidateProfile,
    preferences: CandidatePreferenceInput | None = None,
) -> JobSearchResult:
    merged = _merge_preferences(candidate, preferences)
    search_plan = build_search_plan(candidate, merged)
    settings = _SEARCH_MODE_SETTINGS[_search_mode(merged)]
    provider_statuses: list[ProviderStatus] = []
    normalized_jobs: list[NormalizedJob] = []
    fetched_jobs = 0
    timeout = httpx.Timeout(12.0, connect=6.0)
    headers = {
        "User-Agent": "JobInsightTool/0.2 (candidate-intent matching)",
    }

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        remotive_fetched = 0
        remotive_error: str | None = None
        for query in search_plan.combined_queries:
            try:
                records = await _fetch_remotive_jobs(client, query, limit=settings["remotive_limit"])
            except httpx.HTTPError as exc:
                remotive_error = str(exc)
                continue
            remotive_fetched += len(records)
            fetched_jobs += len(records)
            normalized_jobs.extend(normalize_job(record) for record in records)
        provider_statuses.append(
            ProviderStatus(
                provider="Remotive",
                status="ok" if remotive_fetched else "empty",
                fetched_jobs=remotive_fetched,
                normalized_jobs=0,
                freshness="live",
                source_quality=_SOURCE_QUALITY["Remotive"],
                error=remotive_error,
            )
        )

        try:
            remoteok_records = await _fetch_remoteok_jobs(client)
            remoteok_error: str | None = None
        except httpx.HTTPError as exc:
            remoteok_records = []
            remoteok_error = str(exc)
        remoteok_fetched = len(remoteok_records)
        fetched_jobs += remoteok_fetched
        normalized_jobs.extend(normalize_job(record) for record in remoteok_records)
        provider_statuses.append(
            ProviderStatus(
                provider="RemoteOK",
                status="ok" if remoteok_fetched else "empty",
                fetched_jobs=remoteok_fetched,
                normalized_jobs=0,
                freshness="live",
                source_quality=_SOURCE_QUALITY["RemoteOK"],
                error=remoteok_error,
            )
        )

    filtered, search_plan, diagnostics = apply_search_funnel(
        candidate,
        merged,
        normalized_jobs,
        search_plan=search_plan,
        fetched_jobs=fetched_jobs,
    )

    for status in provider_statuses:
        provider_jobs = [job for job in filtered if job.source == status.provider]
        status.normalized_jobs = len(provider_jobs)

    if not filtered:
        raise JobSearchError(
            "No matching jobs were found from the live job feeds. Try refining your target roles or must-have skills."
        )

    filtered.sort(
        key=lambda job: (
            0 if job.seniority_band == "entry-level" and candidate.seniority == "early-career" else 1,
            -(job.source_quality),
            job.job_age_days if job.job_age_days is not None else 9999,
        )
    )
    return JobSearchResult(
        jobs=filtered[:60],
        search_plan=search_plan,
        provider_statuses=provider_statuses,
        diagnostics=diagnostics,
    )

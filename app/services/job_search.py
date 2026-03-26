from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.schemas import JobRecord, ResumeProfile


class JobSearchError(ValueError):
    """Raised when live job discovery cannot produce any results."""


@dataclass
class JobSearchResult:
    jobs: list[JobRecord]
    search_terms: list[str]
    providers_used: list[str]


ROLE_HINTS = {
    "backend": "backend engineer intern",
    "data": "data analyst intern",
    "ml": "machine learning engineer intern",
    "frontend": "frontend engineer intern",
}

SKILL_ROLE_MAP = {
    "FastAPI": "backend",
    "REST APIs": "backend",
    "SQL": "data",
    "Pandas": "data",
    "Data Analysis": "data",
    "Machine Learning": "ml",
    "OpenAI API": "ml",
    "RAG": "ml",
    "NLP": "ml",
    "React": "frontend",
    "TypeScript": "frontend",
}


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        deduped.append(item.strip())
        seen.add(key)
    return deduped


def derive_search_terms(resume: ResumeProfile) -> list[str]:
    role_buckets = [
        SKILL_ROLE_MAP[skill]
        for skill in resume.skills
        if skill in SKILL_ROLE_MAP
    ]

    inferred_roles = _dedupe_preserve_order([ROLE_HINTS[bucket] for bucket in role_buckets if bucket in ROLE_HINTS])
    skill_terms = [
        f"{skill} intern"
        for skill in resume.skills[:4]
    ]

    fallback_terms = ["software engineer intern", "data analyst intern"]
    return _dedupe_preserve_order(inferred_roles + skill_terms + fallback_terms)[:6]


def _resume_keywords(resume: ResumeProfile) -> set[str]:
    keywords = {skill.lower() for skill in resume.skills}
    for term in derive_search_terms(resume):
        keywords.update(token for token in term.lower().split() if len(token) > 2)
    return keywords


def _looks_relevant(text: str, resume: ResumeProfile) -> bool:
    normalized = text.lower()
    keywords = _resume_keywords(resume)
    hits = sum(1 for keyword in keywords if keyword in normalized)
    return hits >= 2


async def _fetch_remotive_jobs(client: httpx.AsyncClient, term: str) -> list[JobRecord]:
    response = await client.get(
        "https://remotive.com/api/remote-jobs",
        params={"search": term, "limit": 20},
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
    return jobs


async def _fetch_remoteok_jobs(client: httpx.AsyncClient, resume: ResumeProfile) -> list[JobRecord]:
    response = await client.get(
        "https://remoteok.com/api",
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []

    jobs: list[JobRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = (item.get("position") or item.get("title") or "").strip()
        description = (item.get("description") or "").strip()
        if not title or not description:
            continue
        combined = f"{title}\n{description}\n{' '.join(item.get('tags') or [])}"
        if not _looks_relevant(combined, resume):
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
    return jobs


def _dedupe_jobs(jobs: list[JobRecord]) -> list[JobRecord]:
    deduped: list[JobRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for job in jobs:
        key = (
            job.title.strip().lower(),
            job.company.strip().lower(),
            (job.url or "").strip().lower(),
        )
        if key in seen:
            continue
        deduped.append(job)
        seen.add(key)
    return deduped


async def fetch_matching_jobs(resume: ResumeProfile) -> JobSearchResult:
    search_terms = derive_search_terms(resume)
    providers_used: list[str] = []
    collected: list[JobRecord] = []

    timeout = httpx.Timeout(12.0, connect=6.0)
    headers = {
        "User-Agent": "JobInsightTool/0.1 (personal project contact: local-app)",
    }

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        remotive_results: list[JobRecord] = []
        for term in search_terms[:4]:
            try:
                remotive_results.extend(await _fetch_remotive_jobs(client, term))
            except httpx.HTTPError:
                continue
        if remotive_results:
            providers_used.append("Remotive")
            collected.extend(remotive_results)

        try:
            remoteok_results = await _fetch_remoteok_jobs(client, resume)
        except httpx.HTTPError:
            remoteok_results = []
        if remoteok_results:
            providers_used.append("RemoteOK")
            collected.extend(remoteok_results)

    filtered = [
        job
        for job in _dedupe_jobs(collected)
        if _looks_relevant(f"{job.title}\n{job.description}", resume)
    ]

    if not filtered:
        raise JobSearchError(
            "No matching jobs were found from the live job feeds. Try a resume with clearer role or skill keywords."
        )

    return JobSearchResult(
        jobs=filtered[:25],
        search_terms=search_terms,
        providers_used=providers_used,
    )

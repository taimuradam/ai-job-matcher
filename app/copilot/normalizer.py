from __future__ import annotations

import hashlib

from app.copilot.schemas import OpportunityData, RawListingData
from app.schemas import JobRecord
from app.services.job_search import normalize_job
from app.services.taxonomy import normalize_text


def normalize_listing(raw_listing: RawListingData, *, raw_listing_id: str | None = None) -> OpportunityData:
    normalized = normalize_job(
        JobRecord(
            title=raw_listing.title,
            company=raw_listing.company,
            location=raw_listing.location,
            description=raw_listing.description,
            employment_type=raw_listing.employment_type,
            url=raw_listing.url,
            source=raw_listing.source,
            source_type=raw_listing.source_type,
            published_at=raw_listing.published_at,
        )
    )
    dedupe_material = "|".join(
        [
            normalized.normalized_title,
            normalize_text(normalized.company),
            normalize_text(normalized.location),
            normalize_text(normalized.apply_url or ""),
        ]
    )
    dedupe_key = hashlib.sha1(dedupe_material.encode("utf-8")).hexdigest()[:18]
    return OpportunityData(
        id=normalized.id,
        raw_listing_id=raw_listing_id,
        dedupe_key=dedupe_key,
        title=normalized.title,
        normalized_title=normalized.normalized_title,
        company=normalized.company,
        location=normalized.location,
        location_type=normalized.location_type,
        location_regions=normalized.location_regions,
        description_text=normalized.description_text,
        employment_type=normalized.employment_type,
        seniority_band=normalized.seniority_band,
        required_skills=normalized.required_skills,
        preferred_skills=normalized.preferred_skills,
        domain_tags=normalized.domain_tags,
        salary_range=normalized.salary_range,
        visa_support=normalized.visa_support,
        published_at=normalized.published_at,
        job_age_days=normalized.job_age_days,
        source=normalized.source,
        source_type=normalized.source_type or raw_listing.source_type,
        source_quality=normalized.source_quality,
        apply_url=normalized.apply_url,
    )


def dedupe_opportunities(opportunities: list[OpportunityData]) -> list[OpportunityData]:
    deduped: list[OpportunityData] = []
    seen: set[str] = set()
    for opportunity in opportunities:
        if opportunity.dedupe_key in seen:
            continue
        near_duplicate = next(
            (
                existing
                for existing in deduped
                if existing.normalized_title == opportunity.normalized_title
                and normalize_text(existing.company) == normalize_text(opportunity.company)
                and normalize_text(existing.location) == normalize_text(opportunity.location)
                and existing.description_text[:220] == opportunity.description_text[:220]
            ),
            None,
        )
        if near_duplicate is not None:
            continue
        seen.add(opportunity.dedupe_key)
        deduped.append(opportunity)
    return deduped

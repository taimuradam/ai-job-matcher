from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass

import httpx

from app.copilot.schemas import (
    ImportBatchRecord,
    ImportFormat,
    ProviderFetchStatus,
    RawListingData,
    SearchTargetData,
)
from app.services.taxonomy import dedupe_preserve_order


@dataclass
class OrchestratedListings:
    listings: list[RawListingData]
    statuses: list[ProviderFetchStatus]
    query_terms: list[str]


class ProviderAdapter:
    name = "unknown"
    source_type = "api"

    async def search(self, target: SearchTargetData) -> tuple[list[RawListingData], ProviderFetchStatus]:
        raise NotImplementedError


def query_terms_for_target(target: SearchTargetData) -> list[str]:
    seed = target.query_terms or target.target_roles or target.role_families
    return dedupe_preserve_order(seed)[:16]


class RemotiveAdapter(ProviderAdapter):
    name = "Remotive"
    source_type = "api"

    async def search(self, target: SearchTargetData) -> tuple[list[RawListingData], ProviderFetchStatus]:
        query_terms = query_terms_for_target(target)[:8]
        listings: list[RawListingData] = []
        error: str | None = None
        timeout = httpx.Timeout(12.0, connect=6.0)
        headers = {"User-Agent": "JobSearchCopilot/2.0"}
        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            for query in query_terms:
                try:
                    response = await client.get(
                        "https://remotive.com/api/remote-jobs",
                        params={"search": query, "limit": 24},
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    error = str(exc)
                    continue
                payload = response.json()
                for item in payload.get("jobs", []):
                    title = (item.get("title") or "").strip()
                    description = (item.get("description") or "").strip()
                    if not title or not description:
                        continue
                    listings.append(
                        RawListingData(
                            external_id=str(item.get("id") or ""),
                            title=title,
                            company=(item.get("company_name") or "Unknown").strip(),
                            location=(item.get("candidate_required_location") or "Remote").strip(),
                            description=description,
                            employment_type=(item.get("job_type") or "").strip() or None,
                            url=(item.get("url") or "").strip() or None,
                            source=self.name,
                            source_type=self.source_type,
                            published_at=(item.get("publication_date") or "").strip() or None,
                            payload=item,
                        )
                    )
        status = ProviderFetchStatus(
            provider=self.name,
            source_type=self.source_type,
            status="ok" if listings else "empty",
            fetched_count=len(listings),
            query_terms=query_terms,
            error=error,
        )
        return listings, status


class RemoteOKAdapter(ProviderAdapter):
    name = "RemoteOK"
    source_type = "api"

    async def search(self, target: SearchTargetData) -> tuple[list[RawListingData], ProviderFetchStatus]:
        timeout = httpx.Timeout(12.0, connect=6.0)
        headers = {"User-Agent": "JobSearchCopilot/2.0", "Accept": "application/json"}
        listings: list[RawListingData] = []
        error: str | None = None
        query_terms = query_terms_for_target(target)
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
                response = await client.get("https://remoteok.com/api")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            error = str(exc)
            response = None
        if response is not None:
            payload = response.json()
            if isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    title = (item.get("position") or item.get("title") or "").strip()
                    description = (item.get("description") or "").strip()
                    if not title or not description:
                        continue
                    combined = f"{title} {description}".lower()
                    if query_terms and not any(term.lower() in combined for term in query_terms[:10]):
                        continue
                    listings.append(
                        RawListingData(
                            external_id=str(item.get("id") or ""),
                            title=title,
                            company=(item.get("company") or "Unknown").strip(),
                            location=(item.get("location") or "Remote").strip(),
                            description=description,
                            employment_type=(item.get("employment_type") or "").strip() or None,
                            url=(item.get("url") or item.get("apply_url") or "").strip() or None,
                            source=self.name,
                            source_type=self.source_type,
                            published_at=(item.get("date") or "").strip() or None,
                            payload=item,
                        )
                    )
        status = ProviderFetchStatus(
            provider=self.name,
            source_type=self.source_type,
            status="ok" if listings else "empty",
            fetched_count=len(listings),
            query_terms=query_terms[:10],
            error=error,
        )
        return listings, status


def parse_import_content(content: str, format_name: ImportFormat) -> list[RawListingData]:
    if format_name == "json":
        payload = json.loads(content)
        if isinstance(payload, dict):
            payload = payload.get("jobs", [])
        if not isinstance(payload, list):
            raise ValueError("JSON imports must be a list of job-like objects.")
        items = payload
    elif format_name == "csv":
        reader = csv.DictReader(io.StringIO(content))
        items = list(reader)
    else:
        items = [{"url": line.strip()} for line in content.splitlines() if line.strip()]

    listings: list[RawListingData] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or item.get("apply_url") or "").strip() or None
        title = (item.get("title") or "").strip()
        if not title and url:
            title = url.rstrip("/").split("/")[-1].replace("-", " ").title() or f"Imported Job {index}"
        description = (item.get("description") or item.get("summary") or "").strip()
        if not description:
            description = "Imported listing with limited structured detail."
        listings.append(
            RawListingData(
                external_id=str(item.get("id") or index),
                title=title or f"Imported Job {index}",
                company=(item.get("company") or "Imported").strip(),
                location=(item.get("location") or "Not specified").strip(),
                description=description,
                employment_type=(item.get("employment_type") or item.get("job_type") or "").strip() or None,
                url=url,
                source="Imported",
                source_type="import",
                published_at=(item.get("published_at") or item.get("date") or "").strip() or None,
                payload=item,
            )
        )
    if not listings:
        raise ValueError("The import did not contain any usable listings.")
    return listings


async def collect_live_listings(target: SearchTargetData) -> OrchestratedListings:
    adapters: list[ProviderAdapter] = []
    if target.providers.remotive:
        adapters.append(RemotiveAdapter())
    if target.providers.remoteok:
        adapters.append(RemoteOKAdapter())

    all_listings: list[RawListingData] = []
    statuses: list[ProviderFetchStatus] = []
    for adapter in adapters:
        listings, status = await adapter.search(target)
        all_listings.extend(listings)
        statuses.append(status)

    return OrchestratedListings(
        listings=all_listings,
        statuses=statuses,
        query_terms=query_terms_for_target(target),
    )

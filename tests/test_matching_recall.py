from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.copilot.schemas import ProviderFetchStatus, RawListingData
from app.copilot.source_orchestrator import OrchestratedListings


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JOB_MATCHER_DB_PATH", str(tmp_path / "copilot.sqlite3"))
    import app.main as main_module

    main_module = importlib.reload(main_module)
    with TestClient(main_module.app) as test_client:
        yield test_client, main_module


def _save_default_profile(test_client: TestClient) -> None:
    response = test_client.put(
        "/api/profile",
        json={
            "profile": {
                "filename": "resume.txt",
                "summary": "Targeting backend internships.",
                "skills_confirmed": ["Python", "FastAPI", "SQL"],
                "skills_inferred": ["Docker"],
                "core_roles": ["backend engineer"],
                "adjacent_roles": ["software engineer", "platform engineer"],
                "seniority": "early-career",
                "industries": ["developer tools"],
                "preferred_locations": ["Chicago, IL"],
                "remote_preference": "remote_or_hybrid",
                "employment_preferences": ["internship"],
                "education_level": ["Bachelor's"],
                "years_experience": 1,
                "projects": [
                    {
                        "title": "Platform Tooling",
                        "summary": "Built backend APIs with Python, FastAPI, SQL, and Docker for internal tooling.",
                        "related_skills": ["Python", "FastAPI", "SQL", "Docker"],
                        "confidence": 0.85,
                    }
                ],
                "evidence": [
                    {
                        "label": "Project",
                        "detail": "Built backend APIs with Python and SQL for internal tooling.",
                        "confidence": 0.8,
                    }
                ],
                "confidence": {"core_roles": 0.83},
                "signals": ["Built backend APIs for product teams."],
                "llm_summary": "Targeting backend internships."
            },
            "target": {
                "target_roles": ["backend engineer"],
                "role_families": ["backend engineer", "software engineer", "platform engineer"],
                "query_terms": ["backend engineer intern", "software engineer intern", "python backend engineer"],
                "preferred_locations": ["Chicago, IL"],
                "work_modes": ["remote", "hybrid"],
                "employment_preferences": ["internship"],
                "must_have_skills": ["Python", "FastAPI", "SQL"],
                "excluded_keywords": ["sales"],
                "seniority_ceiling": "entry-level",
                "search_mode": "balanced",
                "strict_location": False,
                "strict_work_mode": False,
                "strict_employment": False,
                "strict_must_have": False,
                "providers": {"remotive": True, "remoteok": True, "imports": True}
            }
        },
    )
    assert response.status_code == 200


def test_search_run_uses_imports_and_live_sources_through_same_pipeline(client, monkeypatch) -> None:
    test_client, _ = client
    _save_default_profile(test_client)

    def fake_collect_live_listings(_target):
        return OrchestratedListings(
            listings=[
                RawListingData(
                    title="Backend Engineer Intern",
                    company="Harbor Apps",
                    location="Hybrid - Chicago, IL",
                    description="Required: Python, FastAPI, SQL. Build APIs for internal tooling.",
                    employment_type="Internship",
                    url="https://example.com/backend-intern",
                    source="Remotive",
                    source_type="api",
                ),
                RawListingData(
                    title="Backend Engineer Intern",
                    company="Harbor Apps",
                    location="Hybrid - Chicago, IL",
                    description="Required: Python, FastAPI, SQL. Build APIs for internal tooling.",
                    employment_type="Internship",
                    url="https://example.com/backend-intern",
                    source="RemoteOK",
                    source_type="api",
                ),
            ],
            statuses=[
                ProviderFetchStatus(provider="Remotive", source_type="api", status="ok", fetched_count=1),
                ProviderFetchStatus(provider="RemoteOK", source_type="api", status="ok", fetched_count=1),
            ],
            query_terms=["backend engineer intern", "python backend engineer"],
        )

    async def fake_collect(_target):
        return fake_collect_live_listings(_target)

    monkeypatch.setattr("app.copilot.workflow.collect_live_listings", fake_collect)

    import_response = test_client.post(
        "/api/imports",
        json={
            "format": "json",
            "content": """
            [
              {
                "title": "Platform Engineer Intern",
                "company": "Infra Labs",
                "location": "Remote",
                "description": "Required: Python, SQL, Docker. Build backend platform tooling.",
                "employment_type": "Internship",
                "url": "https://example.com/platform-intern"
              }
            ]
            """,
        },
    )
    assert import_response.status_code == 200

    run_response = test_client.post("/api/search-runs", json={"refresh_action_plans": True})

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["run"]["diagnostics"]["fetched_listings"] == 3
    assert payload["run"]["diagnostics"]["deduped_opportunities"] == 2
    assert {item["provider"] for item in payload["run"]["provider_statuses"]} == {"Remotive", "RemoteOK", "Imports"}
    assert payload["results"][0]["assessment"]["triage_decision"] in {"apply", "tailor"}
    assert payload["results"][0]["action_plan"] is not None


def test_feedback_changes_future_ranking_for_similar_opportunities(client, monkeypatch) -> None:
    test_client, _ = client
    _save_default_profile(test_client)

    async def fake_collect(_target):
        return OrchestratedListings(
            listings=[
                RawListingData(
                    title="Backend Engineer Intern",
                    company="Harbor Apps",
                    location="Remote",
                    description="Required: Python, FastAPI, SQL. Build APIs for internal tools and product teams.",
                    employment_type="Internship",
                    url="https://example.com/job-a",
                    source="Remotive",
                    source_type="api",
                ),
                RawListingData(
                    title="Platform Engineer Intern",
                    company="Northfield Infra",
                    location="Remote",
                    description="Required: Python, FastAPI, SQL, Docker. Build backend platform services, APIs, and tooling.",
                    employment_type="Internship",
                    url="https://example.com/job-b",
                    source="Remotive",
                    source_type="api",
                ),
            ],
            statuses=[ProviderFetchStatus(provider="Remotive", source_type="api", status="ok", fetched_count=2)],
            query_terms=["backend engineer intern", "platform engineer intern"],
        )

    monkeypatch.setattr("app.copilot.workflow.collect_live_listings", fake_collect)

    first_run = test_client.post("/api/search-runs", json={})
    first_payload = first_run.json()
    assert first_payload["results"][0]["opportunity"]["title"] == "Backend Engineer Intern"

    feedback = test_client.post(
        f"/api/opportunities/{first_payload['results'][0]['opportunity']['id']}/feedback",
        json={"run_id": first_payload["run"]["id"], "label": "wrong_stack"},
    )
    assert feedback.status_code == 200
    assert feedback.json()["saved"] is True

    second_run = test_client.post("/api/search-runs", json={})
    second_payload = second_run.json()

    assert second_payload["results"][0]["opportunity"]["title"] == "Platform Engineer Intern"

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.taxonomy import extract_location_mentions, extract_years_of_experience


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JOB_MATCHER_DB_PATH", str(tmp_path / "copilot.sqlite3"))
    import app.main as main_module

    main_module = importlib.reload(main_module)
    with TestClient(main_module.app) as test_client:
        yield test_client, main_module


def test_index_page_renders_workspace_shell(client) -> None:
    test_client, _ = client

    response = test_client.get("/")

    assert response.status_code == 200
    assert "Job Search Copilot" in response.text
    assert 'id="root"' in response.text


def test_profile_ingest_returns_draft_and_suggested_target(client) -> None:
    test_client, _ = client
    resume_text = """
    Backend-focused student building Python APIs with FastAPI and SQL.
    Built Dockerized services and internal dashboards in Chicago, Illinois.
    Looking for remote or hybrid internships.
    """

    response = test_client.post(
        "/api/profile/ingest",
        files={"resume": ("resume.txt", resume_text, "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "backend engineer" in payload["profile"]["core_roles"]
    assert payload["suggested_target"]["target_roles"]
    assert payload["llm_status"]["mode"] in {"disabled", "fallback", "enriched", "failed"}


def test_profile_save_persists_versioned_profile_and_target(client) -> None:
    test_client, _ = client
    profile_payload = {
        "profile": {
            "filename": "resume.txt",
            "summary": "Targeting backend internships.",
            "skills_confirmed": ["Python", "FastAPI", "SQL"],
            "skills_inferred": ["Docker"],
            "core_roles": ["backend engineer"],
            "adjacent_roles": ["software engineer"],
            "seniority": "early-career",
            "industries": ["developer tools"],
            "preferred_locations": ["Chicago, IL"],
            "remote_preference": "remote_or_hybrid",
            "employment_preferences": ["internship"],
            "education_level": ["Bachelor's"],
            "years_experience": 1,
            "projects": [],
            "evidence": [],
            "confidence": {"core_roles": 0.8},
            "signals": ["Built APIs for internal tools."],
            "llm_summary": "Targeting backend internships."
        },
        "target": {
            "target_roles": ["backend engineer"],
            "role_families": ["backend engineer", "software engineer"],
            "query_terms": ["backend engineer intern", "junior backend engineer"],
            "preferred_locations": ["Chicago, IL"],
            "work_modes": ["remote", "hybrid"],
            "employment_preferences": ["internship"],
            "must_have_skills": ["Python", "FastAPI", "SQL"],
            "excluded_keywords": [],
            "seniority_ceiling": "entry-level",
            "search_mode": "balanced",
            "strict_location": False,
            "strict_work_mode": False,
            "strict_employment": False,
            "strict_must_have": False,
            "providers": {"remotive": True, "remoteok": True, "imports": True}
        }
    }

    response = test_client.put("/api/profile", json=profile_payload)

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["version"] == 1
    assert payload["target"]["version"] == 1

    workspace = test_client.get("/api/workspace").json()
    assert workspace["profile"]["profile"]["skills_confirmed"] == ["Python", "FastAPI", "SQL"]
    assert workspace["target"]["target"]["target_roles"] == ["backend engineer"]


def test_workspace_reset_clears_saved_state(client) -> None:
    test_client, _ = client
    profile_payload = {
        "profile": {
            "filename": "resume.txt",
            "summary": "Targeting backend internships.",
            "skills_confirmed": ["Python", "FastAPI", "SQL"],
            "skills_inferred": [],
            "core_roles": ["backend engineer"],
            "adjacent_roles": ["software engineer"],
            "seniority": "early-career",
            "industries": [],
            "preferred_locations": ["Brisbane"],
            "remote_preference": "remote_or_hybrid",
            "employment_preferences": ["internship"],
            "education_level": ["Bachelor's"],
            "years_experience": 1,
            "projects": [],
            "evidence": [],
            "confidence": {"core_roles": 0.8},
            "signals": [],
            "llm_summary": "Targeting backend internships."
        }
    }

    save_response = test_client.put("/api/profile", json=profile_payload)
    assert save_response.status_code == 200

    reset_response = test_client.delete("/api/workspace")
    assert reset_response.status_code == 204

    workspace = test_client.get("/api/workspace").json()
    assert workspace["profile"] is None
    assert workspace["target"] is None
    assert workspace["latest_run"] is None
    assert workspace["imports"] == []


def test_location_extraction_ignores_common_words_that_match_state_codes() -> None:
    text = """
    Based in Brisbane and looking for remote or hybrid software roles.
    Interested in backend work or AI product roles.
    """

    locations = extract_location_mentions(text)

    assert "Indiana" not in locations
    assert "Oregon" not in locations


def test_year_extraction_ignores_education_years_without_work_experience_context() -> None:
    text = """
    Bachelor of Computer Science
    University of Somewhere
    2022 - 2026
    Projects: Built Python and FastAPI applications.
    """

    years = extract_years_of_experience(text)

    assert years is None

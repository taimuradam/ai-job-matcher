from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.schemas import JobRecord
from app.services.job_search import JobSearchResult

client = TestClient(app)


def test_index_page_renders() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Job Insight Tool" in response.text
    assert "No job description upload is required" in response.text


def test_resume_analysis_fetches_live_jobs_and_ranks_backend_role_first(monkeypatch) -> None:
    resume_text = """
    Taimur Adam
    Python developer building FastAPI tools for job analysis.
    Projects include SQL dashboards, Dockerized APIs, pandas data analysis,
    scikit-learn prototypes, and LLM workflow experiments using OpenAI APIs.
    2 years experience building backend services.
    """

    async def fake_fetch_matching_jobs(_resume_profile):
        return JobSearchResult(
            jobs=[
                JobRecord(
                    title="Backend Engineer Intern",
                    company="Example Systems",
                    location="Remote",
                    description="Build Python and FastAPI APIs with SQL, Docker, REST integrations, and Git.",
                    url="https://example.com/backend",
                    source="Remotive",
                    source_type="api",
                ),
                JobRecord(
                    title="Frontend Engineer Intern",
                    company="Example Interface",
                    location="Remote",
                    description="Build React and TypeScript user interfaces with strong accessibility practices.",
                    url="https://example.com/frontend",
                    source="RemoteOK",
                    source_type="api",
                ),
            ],
            search_terms=["backend engineer intern", "python intern"],
            providers_used=["Remotive", "RemoteOK"],
        )

    monkeypatch.setattr(main_module, "fetch_matching_jobs", fake_fetch_matching_jobs)

    response = client.post(
        "/api/analyze",
        files={"resume": ("resume.txt", resume_text, "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobs_analyzed"] == 2
    assert payload["summary"]["providers_used"] == ["Remotive", "RemoteOK"]
    assert payload["summary"]["search_terms"] == ["backend engineer intern", "python intern"]
    assert payload["matches"][0]["job"]["title"] == "Backend Engineer Intern"
    assert payload["matches"][0]["score"] > payload["matches"][1]["score"]
    assert "Python" in payload["matches"][0]["matched_skills"]

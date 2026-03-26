from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.schemas import CandidatePreferenceInput, NormalizedJob, ProviderStatus, SearchPlan
from app.services.job_search import JobSearchResult
from app.services.profile_extraction import build_candidate_profile
from app.services.scoring import analyze_search_results

client = TestClient(app)


def test_index_page_renders() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Job Insight Tool" in response.text
    assert "Review search intent" in response.text


def test_profile_extract_builds_candidate_profile() -> None:
    resume_text = """
    Alex Example
    Python developer building FastAPI APIs, SQL dashboards, and Dockerized services.
    Built machine learning prototypes with scikit-learn and OpenAI APIs.
    2 years experience through projects and internships.
    """

    response = client.post(
        "/api/profile/extract",
        files={"resume": ("resume.txt", resume_text, "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "backend engineer" in payload["candidate"]["core_roles"]
    assert "Python" in payload["candidate"]["skills_confirmed"]
    assert payload["candidate"]["confidence"]["core_roles"] > 0.5


def test_resume_analysis_fetches_live_jobs_and_ranks_backend_role_first(monkeypatch) -> None:
    async def fake_fetch_matching_jobs(_candidate, _preferences: CandidatePreferenceInput | None = None):
        return JobSearchResult(
            jobs=[
                NormalizedJob(
                    id="backend-1",
                    title="Backend Engineer Intern",
                    normalized_title="backend engineer",
                    company="Example Systems",
                    location="Remote",
                    location_type="remote",
                    location_regions=["Remote", "United States"],
                    description_text="Build Python and FastAPI APIs with SQL, Docker, REST integrations, and Git.",
                    employment_type="Internship",
                    seniority_band="entry-level",
                    required_skills=["Python", "FastAPI", "SQL", "Docker"],
                    preferred_skills=["REST APIs", "Git"],
                    domain_tags=["developer tools"],
                    salary_range=None,
                    visa_support=None,
                    published_at="2026-03-20T12:00:00+00:00",
                    job_age_days=1,
                    source="Remotive",
                    source_type="api",
                    source_quality=0.8,
                    apply_url="https://example.com/backend",
                ),
                NormalizedJob(
                    id="frontend-1",
                    title="Senior Frontend Engineer",
                    normalized_title="frontend engineer",
                    company="Example Interface",
                    location="Remote",
                    location_type="remote",
                    location_regions=["Remote"],
                    description_text="Build React and TypeScript user interfaces with 6+ years ownership.",
                    employment_type="Full-time",
                    seniority_band="senior",
                    required_skills=["React", "TypeScript"],
                    preferred_skills=["JavaScript"],
                    domain_tags=[],
                    salary_range=None,
                    visa_support=None,
                    published_at="2026-03-20T12:00:00+00:00",
                    job_age_days=1,
                    source="RemoteOK",
                    source_type="api",
                    source_quality=0.72,
                    apply_url="https://example.com/frontend",
                ),
            ],
            search_plan=SearchPlan(
                exact_role_queries=["backend engineer intern"],
                adjacent_role_queries=["software engineer intern"],
                stack_queries=["Python backend engineer"],
                title_synonyms=["python developer"],
                excluded_roles=[],
                combined_queries=["backend engineer intern", "software engineer intern", "Python backend engineer"],
            ),
            provider_statuses=[
                ProviderStatus(provider="Remotive", status="ok", fetched_jobs=1, normalized_jobs=1, freshness="live", source_quality=0.8),
                ProviderStatus(provider="RemoteOK", status="ok", fetched_jobs=1, normalized_jobs=1, freshness="live", source_quality=0.72),
            ],
        )

    monkeypatch.setattr(main_module, "fetch_matching_jobs", fake_fetch_matching_jobs)

    resume_text = """
    Taimur Adam
    Python developer building FastAPI tools for job analysis.
    Projects include SQL dashboards, Dockerized APIs, pandas data analysis,
    scikit-learn prototypes, and LLM workflow experiments using OpenAI APIs.
    2 years experience building backend services.
    """

    response = client.post(
        "/api/analyze",
        files={"resume": ("resume.txt", resume_text, "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobs_analyzed"] == 2
    assert payload["summary"]["providers_used"] == ["Remotive", "RemoteOK"]
    assert payload["summary"]["search_terms"][0] == "backend engineer intern"
    assert payload["matches"][0]["job"]["title"] == "Backend Engineer Intern"
    assert payload["matches"][0]["score"] > payload["matches"][1]["score"]
    assert payload["matches"][0]["recommendation_tier"] == "Apply now"
    assert "Python" in payload["matches"][0]["hard_requirements_met"]


def test_feedback_endpoint_saves_feedback(monkeypatch) -> None:
    async def fake_fetch_matching_jobs(_candidate, _preferences: CandidatePreferenceInput | None = None):
        return JobSearchResult(
            jobs=[
                NormalizedJob(
                    id="backend-2",
                    title="Backend Engineer Intern",
                    normalized_title="backend engineer",
                    company="Example Systems",
                    location="Remote",
                    location_type="remote",
                    location_regions=["Remote"],
                    description_text="Required: Python, FastAPI, SQL.",
                    employment_type="Internship",
                    seniority_band="entry-level",
                    required_skills=["Python", "FastAPI", "SQL"],
                    preferred_skills=[],
                    domain_tags=[],
                    salary_range=None,
                    visa_support=None,
                    published_at="2026-03-20T12:00:00+00:00",
                    job_age_days=1,
                    source="Remotive",
                    source_type="api",
                    source_quality=0.8,
                    apply_url="https://example.com/backend-2",
                ),
            ],
            search_plan=SearchPlan(
                exact_role_queries=["backend engineer intern"],
                adjacent_role_queries=[],
                stack_queries=[],
                title_synonyms=[],
                excluded_roles=[],
                combined_queries=["backend engineer intern"],
            ),
            provider_statuses=[
                ProviderStatus(provider="Remotive", status="ok", fetched_jobs=1, normalized_jobs=1, freshness="live", source_quality=0.8),
            ],
        )

    monkeypatch.setattr(main_module, "fetch_matching_jobs", fake_fetch_matching_jobs)

    resume_text = """
    Backend-focused student building Python APIs with FastAPI and SQL.
    """
    analysis = client.post(
        "/api/analyze",
        files={"resume": ("resume.txt", resume_text, "text/plain")},
    )
    payload = analysis.json()
    feedback = client.post(
        "/api/feedback",
        json={
            "session_id": payload["session_id"],
            "job_id": payload["matches"][0]["job"]["id"],
            "label": "relevant",
        },
    )

    assert feedback.status_code == 200
    assert feedback.json()["saved"] is True
    assert feedback.json()["total_feedback"] == 1


def test_jobs_search_endpoint_honors_session_feedback_on_rerun(monkeypatch) -> None:
    async def fake_fetch_matching_jobs(_candidate, preferences: CandidatePreferenceInput | None = None):
        return JobSearchResult(
            jobs=[
                NormalizedJob(
                    id="job-a",
                    title="Backend Engineer Intern",
                    normalized_title="backend engineer",
                    company="Phoenix Apps",
                    location="Hybrid - Phoenix, AZ",
                    location_type="hybrid",
                    location_regions=["Arizona", "United States"],
                    description_text="Required: Python, FastAPI, SQL. Build APIs for internal tools.",
                    employment_type="Internship",
                    seniority_band="entry-level",
                    required_skills=["Python", "FastAPI", "SQL"],
                    preferred_skills=["Docker"],
                    domain_tags=[],
                    salary_range=None,
                    visa_support=None,
                    published_at="2026-03-20T12:00:00+00:00",
                    job_age_days=1,
                    source="Remotive",
                    source_type="api",
                    source_quality=0.8,
                    apply_url="https://example.com/job-a",
                ),
                NormalizedJob(
                    id="job-b",
                    title="Backend Platform Intern",
                    normalized_title="backend platform",
                    company="Desert Infra",
                    location="Hybrid - Phoenix, AZ",
                    location_type="hybrid",
                    location_regions=["Arizona", "United States"],
                    description_text="Required: Python, FastAPI, SQL, AWS. Build platform services.",
                    employment_type="Internship",
                    seniority_band="entry-level",
                    required_skills=["Python", "FastAPI", "SQL", "AWS"],
                    preferred_skills=["Docker"],
                    domain_tags=[],
                    salary_range=None,
                    visa_support=None,
                    published_at="2026-03-20T12:00:00+00:00",
                    job_age_days=1,
                    source="Remotive",
                    source_type="api",
                    source_quality=0.8,
                    apply_url="https://example.com/job-b",
                ),
            ],
            search_plan=SearchPlan(
                exact_role_queries=["backend engineer intern"],
                adjacent_role_queries=["platform engineer intern"],
                stack_queries=["Python backend engineer"],
                title_synonyms=["python developer"],
                excluded_roles=[],
                combined_queries=["backend engineer intern", "platform engineer intern", "Python backend engineer"],
            ),
            provider_statuses=[
                ProviderStatus(provider="Remotive", status="ok", fetched_jobs=2, normalized_jobs=2, freshness="live", source_quality=0.8),
            ],
        )

    monkeypatch.setattr(main_module, "fetch_matching_jobs", fake_fetch_matching_jobs)

    resume_text = """
    Backend-focused student building Python APIs with FastAPI and SQL.
    Built Dockerized tools and internal dashboards in Phoenix.
    """
    extract_response = client.post(
        "/api/profile/extract",
        files={"resume": ("resume.txt", resume_text, "text/plain")},
    )
    assert extract_response.status_code == 200
    candidate = extract_response.json()["candidate"]

    search_request = {
        "candidate": candidate,
        "preferences": {
            "target_roles": ["backend engineer"],
            "preferred_locations": ["Phoenix, AZ"],
            "remote_preference": "hybrid_or_remote",
            "employment_preferences": ["internship"],
            "must_have_skills": ["Python", "FastAPI", "SQL"],
            "excluded_roles": [],
            "ranking_mode": "balanced",
        },
    }

    first_search = client.post("/api/jobs/search", json=search_request)
    assert first_search.status_code == 200
    first_payload = first_search.json()
    first_session = first_payload["session_id"]
    first_titles = [match["job"]["title"] for match in first_payload["matches"]]

    feedback = client.post(
        "/api/feedback",
        json={
            "session_id": first_session,
            "job_id": "job-a",
            "label": "wrong_stack",
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["saved"] is True

    search_request["session_id"] = first_session
    second_search = client.post("/api/jobs/search", json=search_request)
    assert second_search.status_code == 200
    second_payload = second_search.json()
    second_titles = [match["job"]["title"] for match in second_payload["matches"]]

    assert first_titles[0] == "Backend Engineer Intern"
    assert second_titles[0] == "Backend Platform Intern"


def test_ranking_demotes_senior_roles_and_wrong_locations_for_early_career() -> None:
    candidate = build_candidate_profile(
        "resume.txt",
        """
        Backend-focused student building Python APIs with FastAPI and SQL.
        Built Dockerized services and analytics tools during internships.
        1 year experience.
        """
    )
    preferences = CandidatePreferenceInput(
        target_roles=["backend engineer"],
        preferred_locations=["Phoenix, AZ"],
        remote_preference="onsite_friendly",
        must_have_skills=["Python", "FastAPI", "SQL"],
    )
    jobs = [
        NormalizedJob(
            id="fit-job",
            title="Backend Engineer Intern",
            normalized_title="backend engineer",
            company="Desert Systems",
            location="Hybrid - Phoenix, AZ",
            location_type="hybrid",
            location_regions=["Arizona", "United States"],
            description_text="Required: Python, FastAPI, SQL. Build internal APIs for product teams.",
            employment_type="Internship",
            seniority_band="entry-level",
            required_skills=["Python", "FastAPI", "SQL"],
            preferred_skills=["Docker"],
            domain_tags=[],
            salary_range=None,
            visa_support=None,
            published_at="2026-03-20T12:00:00+00:00",
            job_age_days=1,
            source="Fixture",
            source_type="fixture",
            source_quality=0.85,
            apply_url=None,
        ),
        NormalizedJob(
            id="bad-job",
            title="Senior Backend Engineer",
            normalized_title="backend engineer",
            company="Atlantic Systems",
            location="Onsite - New York, NY",
            location_type="onsite",
            location_regions=["New York", "United States"],
            description_text="Required: Python, FastAPI, SQL, leadership, architecture, 6+ years experience.",
            employment_type="Full-time",
            seniority_band="senior",
            required_skills=["Python", "FastAPI", "SQL", "AWS"],
            preferred_skills=["Docker"],
            domain_tags=[],
            salary_range=None,
            visa_support=None,
            published_at="2026-03-20T12:00:00+00:00",
            job_age_days=1,
            source="Fixture",
            source_type="fixture",
            source_quality=0.85,
            apply_url=None,
        ),
    ]

    response = analyze_search_results(
        candidate=candidate,
        preferences=preferences,
        jobs=jobs,
        search_plan=SearchPlan(
            exact_role_queries=["backend engineer intern"],
            adjacent_role_queries=[],
            stack_queries=["Python backend engineer"],
            title_synonyms=["python developer"],
            excluded_roles=[],
            combined_queries=["backend engineer intern", "Python backend engineer"],
        ),
        provider_statuses=[
            ProviderStatus(provider="Fixture", status="ok", fetched_jobs=2, normalized_jobs=2, freshness="fixture", source_quality=0.85),
        ],
        session_id="ranking-regression",
    )

    assert response.matches[0].job.id == "fit-job"
    assert response.matches[0].recommendation_tier == "Apply now"
    assert response.matches[1].score < response.matches[0].score
    assert "Experience gap is likely the blocker" == response.matches[1].likely_rejection_driver

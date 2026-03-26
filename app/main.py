from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.schemas import (
    FeedbackResponse,
    ProfileExtractionResponse,
    SearchFeedbackRequest,
    SearchRequest,
    SearchResponse,
)
from app.services.job_search import JobSearchError, fetch_matching_jobs
from app.services.profile_extraction import build_candidate_profile
from app.services.scoring import analyze_search_results, record_feedback
from app.services.text_parser import extract_text_from_upload

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(
    title="AI-Assisted Job Application Insight Tool",
    version="0.2.0",
    description=(
        "Upload a resume, confirm a draft candidate profile, fetch matching jobs from public job feeds, "
        "and rank them with transparent early-career-aware reasoning."
    ),
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "app_title": "Job Insight Tool",
        },
    )


@app.post("/api/profile/extract", response_model=ProfileExtractionResponse)
async def extract_candidate_profile(
    resume: UploadFile = File(...),
) -> ProfileExtractionResponse:
    try:
        resume_text = await extract_text_from_upload(resume)
        candidate = build_candidate_profile(
            resume.filename or "resume.txt",
            resume_text,
        )
        return ProfileExtractionResponse(candidate=candidate, generated_at=datetime.now(UTC))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guard for UI stability
        raise HTTPException(
            status_code=500,
            detail="The resume could not be profiled. Please try again.",
        ) from exc


@app.post("/api/jobs/search", response_model=SearchResponse)
async def search_jobs(request: SearchRequest) -> SearchResponse:
    try:
        search_result = await fetch_matching_jobs(request.candidate, request.preferences)
        return analyze_search_results(
            candidate=request.candidate,
            preferences=request.preferences,
            jobs=search_result.jobs,
            search_plan=search_result.search_plan,
            provider_statuses=search_result.provider_statuses,
            diagnostics=search_result.diagnostics,
            session_id=request.session_id,
        )
    except JobSearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guard for the UI
        raise HTTPException(
            status_code=500,
            detail="The job search failed unexpectedly. Please try again.",
        ) from exc


@app.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: SearchFeedbackRequest) -> FeedbackResponse:
    return record_feedback(request)


@app.post(
    "/api/analyze",
    response_model=SearchResponse,
    deprecated=True,
)
async def analyze(
    resume: UploadFile = File(...),
) -> SearchResponse:
    try:
        resume_text = await extract_text_from_upload(resume)
        candidate = build_candidate_profile(
            resume.filename or "resume.txt",
            resume_text,
        )
        search_result = await fetch_matching_jobs(candidate)
        return analyze_search_results(
            candidate=candidate,
            preferences=SearchRequest(candidate=candidate).preferences,
            jobs=search_result.jobs,
            search_plan=search_result.search_plan,
            provider_statuses=search_result.provider_statuses,
            diagnostics=search_result.diagnostics,
        )
    except JobSearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guard for the UI
        raise HTTPException(
            status_code=500,
            detail="The analysis failed unexpectedly. Please try again.",
        ) from exc

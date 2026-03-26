from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.schemas import AnalysisResponse
from app.services.job_search import JobSearchError, fetch_matching_jobs
from app.services.scoring import analyze_resume_against_jobs
from app.services.scoring import build_resume_profile
from app.services.text_parser import extract_text_from_upload

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(
    title="AI-Assisted Job Application Insight Tool",
    version="0.1.0",
    description=(
        "Upload a resume, fetch matching jobs from public job feeds, and get "
        "transparent match scores with practical skill-gap insights."
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


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze(
    resume: UploadFile = File(...),
) -> AnalysisResponse:
    try:
        resume_text = await extract_text_from_upload(resume)
        resume_profile = build_resume_profile(
            resume.filename or "resume.txt",
            resume_text,
        )
        search_result = await fetch_matching_jobs(resume_profile)
        return analyze_resume_against_jobs(
            resume_filename=resume.filename or "resume.txt",
            resume_text=resume_text,
            jobs=search_result.jobs,
            search_terms=search_result.search_terms,
            providers_used=search_result.providers_used,
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

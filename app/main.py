from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.copilot.fit_engine import assess_opportunity, build_action_plan
from app.copilot.profile_ingestion import build_ingest_response
from app.copilot.schemas import (
    ActionPlanRequest,
    ActionPlanResponse,
    FeedbackRequest,
    FeedbackResponse,
    ImportRequest,
    ImportResponse,
    SaveProfileRequest,
    SaveProfileResponse,
    SearchRunDetailResponse,
    SearchRunRequest,
    WorkspaceSnapshotResponse,
)
from app.copilot.source_orchestrator import parse_import_content
from app.copilot.storage import SQLiteStore
from app.copilot.target_builder import build_search_target
from app.copilot.workflow import run_search
from app.services.text_parser import extract_text_from_upload

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(application: FastAPI):
    default_db_path = Path(tempfile.gettempdir()) / "ai-job-matcher-session.sqlite3"
    db_path = os.getenv("JOB_MATCHER_DB_PATH", str(default_db_path))
    store = SQLiteStore(db_path)
    store.reset()
    application.state.store = store
    application.state.llm_client = None
    yield


app = FastAPI(
    title="Candidate-Centric Job Search Copilot",
    version="2.0.0",
    description=(
        "Stateful single-user job search copilot for early-career technical candidates. "
        "It ingests a resume, persists a target profile, runs pluggable searches, scores opportunities, "
        "and tracks feedback and action plans."
    ),
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def get_store(request: Request) -> SQLiteStore:
    return request.app.state.store


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    get_store(request).reset()
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "app_title": "Job Search Copilot",
        },
    )


@app.get("/api/workspace", response_model=WorkspaceSnapshotResponse)
async def workspace(request: Request) -> WorkspaceSnapshotResponse:
    return get_store(request).workspace_snapshot()


@app.post("/api/profile/ingest")
async def ingest_profile(
    request: Request,
    resume: UploadFile = File(...),
):
    try:
        resume_text = await extract_text_from_upload(resume)
        return build_ingest_response(
            filename=resume.filename or "resume.txt",
            resume_text=resume_text,
            llm_client=request.app.state.llm_client,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive UI guard
        raise HTTPException(status_code=500, detail="The resume could not be ingested.") from exc


@app.put("/api/profile", response_model=SaveProfileResponse)
async def save_profile(request: Request, payload: SaveProfileRequest) -> SaveProfileResponse:
    store = get_store(request)
    profile_record = store.save_profile(profile=payload.profile, llm_status=payload.llm_status)
    target_record = store.save_target(
        profile_record=profile_record,
        target=payload.target or build_search_target(payload.profile),
    )
    return SaveProfileResponse(
        saved_at=profile_record.created_at,
        profile=profile_record,
        target=target_record,
    )


@app.post("/api/search-runs", response_model=SearchRunDetailResponse)
async def create_search_run(request: Request, payload: SearchRunRequest) -> SearchRunDetailResponse:
    store = get_store(request)
    profile_record = store.latest_profile()
    target_record = store.latest_target()
    if profile_record is None or target_record is None:
        raise HTTPException(status_code=400, detail="Save a canonical profile and target before running search.")
    return await run_search(
        store=store,
        profile_record=profile_record,
        target_record=target_record,
        refresh_action_plans=payload.refresh_action_plans,
        llm_client=request.app.state.llm_client,
    )


@app.get("/api/search-runs/{run_id}", response_model=SearchRunDetailResponse)
async def get_search_run(request: Request, run_id: str) -> SearchRunDetailResponse:
    try:
        return get_store(request).search_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/imports", response_model=ImportResponse)
async def create_import(request: Request, payload: ImportRequest) -> ImportResponse:
    try:
        listings = parse_import_content(payload.content, payload.format)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    batch = get_store(request).save_import_batch(
        format_name=payload.format,
        label=payload.label or f"Imported {payload.format} jobs",
        content=payload.content,
        listings=listings,
    )
    return ImportResponse(imported_at=batch.created_at, batch=batch)


@app.post("/api/opportunities/{opportunity_id}/feedback", response_model=FeedbackResponse)
async def save_feedback(
    request: Request,
    opportunity_id: str,
    payload: FeedbackRequest,
) -> FeedbackResponse:
    feedback = get_store(request).save_feedback(
        opportunity_id=opportunity_id,
        label=payload.label,
        note=payload.note,
        run_id=payload.run_id,
    )
    return FeedbackResponse(saved=feedback is not None, feedback=feedback)


@app.post("/api/opportunities/{opportunity_id}/action-plan", response_model=ActionPlanResponse)
async def refresh_action_plan(
    request: Request,
    opportunity_id: str,
    payload: ActionPlanRequest,
) -> ActionPlanResponse:
    store = get_store(request)
    run_id = payload.run_id or store.latest_run_id()
    if run_id is None:
        raise HTTPException(status_code=400, detail="No search run is available yet.")
    if not payload.force_refresh:
        existing = store.action_plan(run_id=run_id, opportunity_id=opportunity_id)
        if existing is not None:
            return ActionPlanResponse(opportunity_id=opportunity_id, action_plan=existing)

    try:
        run = store.search_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = next((item for item in run.results if item.opportunity.id == opportunity_id), None)
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found in the selected run.")

    assessment = assess_opportunity(
        run.profile.profile,
        run.target.target,
        result.opportunity,
        feedback_events=store.feedback_events(run_id=run_id, opportunity_id=opportunity_id),
    )
    plan = build_action_plan(
        run.profile.profile,
        run.target.target,
        result.opportunity,
        assessment,
        llm_client=request.app.state.llm_client,
    )
    if plan is None:
        raise HTTPException(status_code=400, detail="This opportunity is not in an actionable state.")
    store.save_action_plan(run_id=run_id, opportunity_id=opportunity_id, plan=plan)
    return ActionPlanResponse(opportunity_id=opportunity_id, action_plan=plan)


@app.post(
    "/api/analyze",
    response_model=SearchRunDetailResponse,
    deprecated=True,
)
async def analyze(
    request: Request,
    resume: UploadFile = File(...),
) -> SearchRunDetailResponse:
    try:
        resume_text = await extract_text_from_upload(resume)
        ingest_response = build_ingest_response(
            filename=resume.filename or "resume.txt",
            resume_text=resume_text,
            llm_client=request.app.state.llm_client,
        )
        store = get_store(request)
        profile_record = store.save_profile(
            profile=ingest_response.profile,
            llm_status=ingest_response.llm_status,
        )
        target_record = store.save_target(
            profile_record=profile_record,
            target=ingest_response.suggested_target,
        )
        return await run_search(
            store=store,
            profile_record=profile_record,
            target_record=target_record,
            llm_client=request.app.state.llm_client,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive UI guard
        raise HTTPException(status_code=500, detail="The compatibility analysis flow failed.") from exc

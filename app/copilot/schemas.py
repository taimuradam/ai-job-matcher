from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


TriageDecision = Literal["apply", "tailor", "monitor", "skip"]
FeedbackLabel = Literal[
    "apply",
    "tailor",
    "monitor",
    "skip",
    "relevant",
    "wrong_stack",
    "wrong_location",
    "too_senior",
]
ImportFormat = Literal["json", "csv", "urls"]
LLMMode = Literal["disabled", "enriched", "fallback", "failed"]


class EvidenceItem(BaseModel):
    label: str
    detail: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ProjectSignal(BaseModel):
    title: str
    summary: str
    related_skills: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class LLMStatus(BaseModel):
    mode: LLMMode = "disabled"
    provider: str | None = None
    detail: str | None = None


class CandidateProfileData(BaseModel):
    filename: str
    summary: str | None = None
    skills_confirmed: list[str] = Field(default_factory=list)
    skills_inferred: list[str] = Field(default_factory=list)
    core_roles: list[str] = Field(default_factory=list)
    adjacent_roles: list[str] = Field(default_factory=list)
    seniority: str = "early-career"
    industries: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    remote_preference: str = "remote_or_hybrid"
    employment_preferences: list[str] = Field(default_factory=list)
    education_level: list[str] = Field(default_factory=list)
    years_experience: float | None = None
    projects: list[ProjectSignal] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    signals: list[str] = Field(default_factory=list)
    llm_summary: str | None = None


class SourceSelection(BaseModel):
    remotive: bool = True
    remoteok: bool = True
    imports: bool = True


class SearchTargetData(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    role_families: list[str] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    work_modes: list[str] = Field(default_factory=list)
    employment_preferences: list[str] = Field(default_factory=list)
    must_have_skills: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    seniority_ceiling: str = "mid-level"
    search_mode: str = "balanced"
    strict_location: bool = False
    strict_work_mode: bool = False
    strict_employment: bool = False
    strict_must_have: bool = False
    providers: SourceSelection = Field(default_factory=SourceSelection)


class CandidateProfileRecord(BaseModel):
    id: str
    version: int
    created_at: datetime
    profile: CandidateProfileData
    llm_status: LLMStatus = Field(default_factory=LLMStatus)


class SearchTargetRecord(BaseModel):
    id: str
    profile_id: str
    profile_version: int
    version: int
    created_at: datetime
    target: SearchTargetData


class ProviderFetchStatus(BaseModel):
    provider: str
    source_type: str
    status: str
    fetched_count: int = 0
    normalized_count: int = 0
    query_terms: list[str] = Field(default_factory=list)
    error: str | None = None


class SearchRunDiagnostics(BaseModel):
    fetched_listings: int = 0
    normalized_opportunities: int = 0
    deduped_opportunities: int = 0
    eligible_opportunities: int = 0
    actionable_opportunities: int = 0
    provider_failures: int = 0
    excluded_counts: dict[str, int] = Field(default_factory=dict)
    active_filters: list[str] = Field(default_factory=list)
    query_plan: list[str] = Field(default_factory=list)


class RawListingData(BaseModel):
    external_id: str | None = None
    title: str
    company: str = "Unknown"
    location: str = "Not specified"
    description: str
    employment_type: str | None = None
    url: str | None = None
    source: str
    source_type: str
    published_at: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class OpportunityData(BaseModel):
    id: str
    raw_listing_id: str | None = None
    dedupe_key: str
    title: str
    normalized_title: str
    company: str = "Unknown"
    location: str = "Not specified"
    location_type: str = "unknown"
    location_regions: list[str] = Field(default_factory=list)
    description_text: str
    employment_type: str | None = None
    seniority_band: str = "unknown"
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    domain_tags: list[str] = Field(default_factory=list)
    salary_range: str | None = None
    visa_support: str | None = None
    published_at: str | None = None
    job_age_days: int | None = None
    source: str
    source_type: str
    source_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    apply_url: str | None = None


class FitFeatureScores(BaseModel):
    role_alignment: int = 0
    skills_alignment: int = 0
    seniority_alignment: int = 0
    location_alignment: int = 0
    evidence_strength: int = 0
    freshness: int = 0
    source_quality: int = 0
    feedback_adjustment: int = 0
    total: int = 0


class FitAssessmentData(BaseModel):
    eligible: bool
    ineligibility_reasons: list[str] = Field(default_factory=list)
    matched_signals: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)
    scores: FitFeatureScores = Field(default_factory=FitFeatureScores)
    triage_decision: TriageDecision = "skip"


class ActionPlanData(BaseModel):
    generated_by: str = "deterministic"
    summary: str
    missing_requirements: list[str] = Field(default_factory=list)
    strongest_evidence: list[str] = Field(default_factory=list)
    resume_tailoring_steps: list[str] = Field(default_factory=list)


class FeedbackEventData(BaseModel):
    label: FeedbackLabel
    note: str | None = None
    created_at: datetime
    normalized_title: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    location_type: str | None = None


class SearchRunRecord(BaseModel):
    id: str
    profile_id: str
    profile_version: int
    target_id: str
    target_version: int
    created_at: datetime
    diagnostics: SearchRunDiagnostics = Field(default_factory=SearchRunDiagnostics)
    provider_statuses: list[ProviderFetchStatus] = Field(default_factory=list)


class OpportunityResult(BaseModel):
    opportunity: OpportunityData
    assessment: FitAssessmentData
    action_plan: ActionPlanData | None = None
    feedback: list[FeedbackEventData] = Field(default_factory=list)


class ImportBatchRecord(BaseModel):
    id: str
    label: str
    format: ImportFormat
    item_count: int
    created_at: datetime


class WorkspaceSnapshotResponse(BaseModel):
    profile: CandidateProfileRecord | None = None
    target: SearchTargetRecord | None = None
    imports: list[ImportBatchRecord] = Field(default_factory=list)
    latest_run: "SearchRunDetailResponse | None" = None


class ProfileIngestResponse(BaseModel):
    generated_at: datetime
    profile: CandidateProfileData
    suggested_target: SearchTargetData
    llm_status: LLMStatus = Field(default_factory=LLMStatus)


class SaveProfileRequest(BaseModel):
    profile: CandidateProfileData
    target: SearchTargetData | None = None
    llm_status: LLMStatus | None = None


class SaveProfileResponse(BaseModel):
    saved_at: datetime
    profile: CandidateProfileRecord
    target: SearchTargetRecord


class SearchRunRequest(BaseModel):
    profile_id: str | None = None
    target_id: str | None = None
    refresh_action_plans: bool = True


class SearchRunDetailResponse(BaseModel):
    run: SearchRunRecord
    profile: CandidateProfileRecord
    target: SearchTargetRecord
    results: list[OpportunityResult] = Field(default_factory=list)


class ImportRequest(BaseModel):
    format: ImportFormat
    content: str
    label: str | None = None


class ImportResponse(BaseModel):
    imported_at: datetime
    batch: ImportBatchRecord


class FeedbackRequest(BaseModel):
    run_id: str | None = None
    label: FeedbackLabel
    note: str | None = None


class FeedbackResponse(BaseModel):
    saved: bool
    feedback: FeedbackEventData | None = None


class ActionPlanRequest(BaseModel):
    run_id: str | None = None
    force_refresh: bool = False


class ActionPlanResponse(BaseModel):
    opportunity_id: str
    action_plan: ActionPlanData


WorkspaceSnapshotResponse.model_rebuild()

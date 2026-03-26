from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class JobRecord(BaseModel):
    title: str
    company: str = "Unknown"
    location: str = "Not specified"
    description: str
    employment_type: str | None = None
    url: str | None = None
    source: str = "uploaded"
    source_type: str | None = None
    published_at: str | None = None


class CandidateEvidence(BaseModel):
    label: str
    snippet: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class CandidateProject(BaseModel):
    title: str
    summary: str
    related_skills: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class CandidateProfile(BaseModel):
    filename: str
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
    projects: list[CandidateProject] = Field(default_factory=list)
    evidence_snippets: list[CandidateEvidence] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    signals: list[str] = Field(default_factory=list)


class CandidatePreferenceInput(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    remote_preference: str | None = None
    employment_preferences: list[str] = Field(default_factory=list)
    must_have_skills: list[str] = Field(default_factory=list)
    excluded_roles: list[str] = Field(default_factory=list)
    ranking_mode: str = "balanced"
    search_mode: str = "broad_recall"
    confirmed_preferences: dict[str, bool] = Field(default_factory=dict)


class SearchPlan(BaseModel):
    exact_role_queries: list[str] = Field(default_factory=list)
    adjacent_role_queries: list[str] = Field(default_factory=list)
    stack_queries: list[str] = Field(default_factory=list)
    title_synonyms: list[str] = Field(default_factory=list)
    widened_role_queries: list[str] = Field(default_factory=list)
    excluded_roles: list[str] = Field(default_factory=list)
    combined_queries: list[str] = Field(default_factory=list)
    search_mode: str = "broad_recall"
    active_filters: list[str] = Field(default_factory=list)


class SearchDiagnostics(BaseModel):
    fetched_jobs: int = 0
    normalized_jobs: int = 0
    deduped_jobs: int = 0
    role_filtered_jobs: int = 0
    location_filtered_jobs: int = 0
    employment_filtered_jobs: int = 0
    relevance_filtered_jobs: int = 0
    final_ranked_jobs: int = 0
    rejected_counts: dict[str, int] = Field(default_factory=dict)
    relaxation_steps: list[str] = Field(default_factory=list)
    active_hard_filters: list[str] = Field(default_factory=list)
    fallback_triggered: bool = False


class ProviderStatus(BaseModel):
    provider: str
    status: str
    fetched_jobs: int = 0
    normalized_jobs: int = 0
    freshness: str = "live"
    source_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    error: str | None = None


class NormalizedJob(BaseModel):
    id: str
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
    source: str = "unknown"
    source_type: str | None = None
    source_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    apply_url: str | None = None


class RankingBreakdown(BaseModel):
    role_fit: int
    required_skills_fit: int
    adjacent_fit: int
    seniority_fit: int
    location_fit: int
    project_fit: int
    source_quality_fit: int
    semantic_signal: float = Field(default=0.0, ge=0.0, le=1.0)
    feedback_adjustment: int = 0
    explanation: str


class JobMatch(BaseModel):
    job: NormalizedJob
    score: int
    score_label: str
    recommendation_tier: str
    surfaced_reasons: list[str] = Field(default_factory=list)
    hard_requirements_met: list[str] = Field(default_factory=list)
    hard_requirements_missing: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    transferable_evidence: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    likely_rejection_driver: str
    why_this_is_still_worth_applying: str
    reasoning: str
    breakdown: RankingBreakdown


class SkillGap(BaseModel):
    skill: str
    frequency: int


class FocusRecommendation(BaseModel):
    title: str
    detail: str


class AnalysisSummary(BaseModel):
    strongest_fit: str | None = None
    top_missing_skills: list[SkillGap] = Field(default_factory=list)
    external_factor_roles: list[str] = Field(default_factory=list)
    focus_areas: list[FocusRecommendation] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    providers_used: list[str] = Field(default_factory=list)
    narrative: str


class ProfileExtractionResponse(BaseModel):
    generated_at: datetime
    candidate: CandidateProfile


class SearchRequest(BaseModel):
    candidate: CandidateProfile
    preferences: CandidatePreferenceInput = Field(default_factory=CandidatePreferenceInput)
    session_id: str | None = None


class SearchResponse(BaseModel):
    generated_at: datetime
    session_id: str
    jobs_analyzed: int
    candidate: CandidateProfile
    resume: CandidateProfile
    preferences: CandidatePreferenceInput
    search_plan: SearchPlan
    provider_statuses: list[ProviderStatus] = Field(default_factory=list)
    diagnostics: SearchDiagnostics = Field(default_factory=SearchDiagnostics)
    matches: list[JobMatch] = Field(default_factory=list)
    summary: AnalysisSummary


class SearchFeedbackRequest(BaseModel):
    session_id: str
    job_id: str
    label: str


class SearchFeedback(BaseModel):
    session_id: str
    job_id: str
    label: str
    normalized_title: str
    seniority_band: str
    location_type: str
    required_skills: list[str] = Field(default_factory=list)
    domain_tags: list[str] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    saved: bool
    total_feedback: int

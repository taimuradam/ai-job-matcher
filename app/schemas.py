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


class ResumeProfile(BaseModel):
    filename: str
    skills: list[str] = Field(default_factory=list)
    experience_years: float | None = None
    education: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)


class MatchBreakdown(BaseModel):
    skill_score: int
    title_score: int
    experience_score: int
    context_score: int
    explanation: str


class JobMatch(BaseModel):
    job: JobRecord
    score: int
    score_label: str
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    likely_rejection_driver: str
    reasoning: str
    breakdown: MatchBreakdown


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


class AnalysisResponse(BaseModel):
    generated_at: datetime
    jobs_analyzed: int
    resume: ResumeProfile
    matches: list[JobMatch]
    summary: AnalysisSummary

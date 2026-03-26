from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from uuid import uuid4

from app.schemas import (
    AnalysisSummary,
    CandidatePreferenceInput,
    CandidateProfile,
    FeedbackResponse,
    FocusRecommendation,
    JobMatch,
    NormalizedJob,
    ProviderStatus,
    RankingBreakdown,
    SearchFeedback,
    SearchFeedbackRequest,
    SearchDiagnostics,
    SearchPlan,
    SearchResponse,
    SkillGap,
)
from app.services.taxonomy import cosine_similarity, dedupe_preserve_order, meaningful_tokens, normalize_text

_SESSION_JOBS: dict[str, dict[str, NormalizedJob]] = {}
_SESSION_FEEDBACK: dict[str, list[SearchFeedback]] = defaultdict(list)


def _candidate_blob(candidate: CandidateProfile) -> str:
    parts = [
        " ".join(candidate.core_roles),
        " ".join(candidate.skills_confirmed),
        " ".join(candidate.skills_inferred),
        " ".join(candidate.signals),
        " ".join(project.summary for project in candidate.projects),
        " ".join(evidence.snippet for evidence in candidate.evidence_snippets),
    ]
    return "\n".join(part for part in parts if part)


def _score_label(score: int) -> str:
    if score >= 78:
        return "Exact fit"
    if score >= 64:
        return "Strong fit"
    if score >= 46:
        return "Apply with tailoring"
    return "Stretch"


def _recommendation_tier(score: int, missing_requirements: list[str]) -> str:
    if score >= 78 and len(missing_requirements) <= 1:
        return "Apply now"
    if score >= 56:
        return "Apply with tailoring"
    return "Stretch but viable"


def _likely_rejection_driver(score: int, missing_requirements: list[str], seniority_fit: int) -> str:
    if seniority_fit <= 3:
        return "Experience gap is likely the blocker"
    if score >= 74 and len(missing_requirements) <= 1:
        return "External factors may matter more"
    if len(missing_requirements) >= 4:
        return "Missing skills are the main risk"
    return "Mixed signal"


def _role_fit(
    candidate: CandidateProfile,
    preferences: CandidatePreferenceInput,
    search_plan: SearchPlan,
    job: NormalizedJob,
) -> tuple[int, list[str]]:
    normalized_title = normalize_text(f"{job.title} {job.normalized_title}")
    target_roles = preferences.target_roles or candidate.core_roles
    adjacent_roles = candidate.adjacent_roles
    surfaced_reasons: list[str] = []

    for role in target_roles:
        if normalize_text(role) in normalized_title:
            surfaced_reasons.append(f"Title aligns directly with your target role: {role}.")
            return 25, surfaced_reasons
    for role in adjacent_roles:
        if normalize_text(role) in normalized_title:
            surfaced_reasons.append(f"Title maps to an adjacent role you can credibly target: {role}.")
            return 21, surfaced_reasons
    for synonym in search_plan.title_synonyms + search_plan.widened_role_queries:
        if normalize_text(synonym) in normalized_title:
            surfaced_reasons.append(f"Title matches a search synonym: {synonym}.")
            return 18, surfaced_reasons
    semantic = max(
        (
            cosine_similarity(job.title, role)
            for role in target_roles + adjacent_roles + search_plan.title_synonyms + search_plan.widened_role_queries
        ),
        default=0.0,
    )
    score = round(max(semantic * 18, 0))
    if score >= 6:
        surfaced_reasons.append("Role similarity stayed relevant even without an exact title match.")
    return score, surfaced_reasons


def _required_skills_fit(
    candidate: CandidateProfile,
    preferences: CandidatePreferenceInput,
    job: NormalizedJob,
) -> tuple[int, list[str], list[str], list[str]]:
    candidate_skills = set(candidate.skills_confirmed) | set(candidate.skills_inferred) | set(preferences.must_have_skills)
    required = job.required_skills or job.preferred_skills
    matched = sorted(candidate_skills & set(required))
    missing = sorted(set(required) - candidate_skills)
    preferred_overlap = len(candidate_skills & set(job.preferred_skills)) / max(len(job.preferred_skills), 1)
    ratio = len(matched) / max(len(required), 1)
    score = round(((ratio * 0.82) + (preferred_overlap * 0.18)) * 25)
    if matched and missing:
        score = max(score, 11)
    if len(matched) >= 2:
        score = max(score, 14)
    return min(score, 25), matched, missing, sorted(candidate_skills & set(job.preferred_skills))


def _adjacent_fit(
    candidate: CandidateProfile,
    preferences: CandidatePreferenceInput,
    job: NormalizedJob,
) -> tuple[int, float]:
    candidate_skills = set(candidate.skills_confirmed) | set(candidate.skills_inferred)
    preferred_overlap = len(candidate_skills & set(job.preferred_skills)) / max(len(job.preferred_skills), 1)
    domain_overlap = len(set(candidate.industries) & set(job.domain_tags)) / max(len(job.domain_tags), 1)
    semantic = cosine_similarity(_candidate_blob(candidate), f"{job.title}\n{job.description_text}")
    must_have_bonus = 0.0
    if preferences.must_have_skills:
        must_have_bonus = len(set(preferences.must_have_skills) & (set(job.required_skills) | set(job.preferred_skills))) / max(len(preferences.must_have_skills), 1)
    total_signal = min((preferred_overlap * 0.2) + (domain_overlap * 0.15) + (semantic * 0.45) + (must_have_bonus * 0.2), 1.0)
    return round(total_signal * 15), semantic


def _seniority_fit(candidate: CandidateProfile, job: NormalizedJob) -> tuple[int, list[str]]:
    risks: list[str] = []
    years = candidate.years_experience or 0.0
    if candidate.seniority == "early-career":
        if job.seniority_band == "entry-level":
            return 10, risks
        if job.seniority_band == "mid-level":
            risks.append("Role looks more mid-level than your current profile.")
            return 6 if years >= 2 else 4, risks
        risks.append("Posting appears clearly senior for an early-career candidate.")
        return 1 if years < 4 else 3, risks
    if candidate.seniority == "mid-level":
        return (8 if job.seniority_band in {"entry-level", "mid-level"} else 5), risks
    return (9 if job.seniority_band == "senior" else 7), risks


def _location_fit(candidate: CandidateProfile, preferences: CandidatePreferenceInput, job: NormalizedJob) -> tuple[int, list[str]]:
    remote_preference = preferences.remote_preference or candidate.remote_preference
    preferred_locations = preferences.preferred_locations or candidate.preferred_locations
    confirmed_locations = bool((preferences.confirmed_preferences or {}).get("preferred_locations"))
    confirmed_remote = bool((preferences.confirmed_preferences or {}).get("remote_preference"))
    surfaced: list[str] = []
    score = 6
    if remote_preference in {"remote_or_hybrid", "hybrid_or_remote"}:
        if job.location_type == "remote":
            score = 10
            surfaced.append("Remote work-mode lines up well with your preference.")
        elif job.location_type == "hybrid":
            score = 8
            surfaced.append("Hybrid work-mode still fits your current preference.")
        else:
            score = 5 if confirmed_remote else 6
    elif remote_preference == "onsite_friendly":
        score = 8 if job.location_type in {"onsite", "hybrid"} else 5

    if preferred_locations:
        normalized_preferences = [normalize_text(item) for item in preferred_locations]
        location_text = normalize_text(f"{job.location} {' '.join(job.location_regions)}")
        if any(
            preference in location_text or location_text in preference
            for preference in normalized_preferences
        ):
            score = min(score + 3, 10)
            surfaced.append("Location overlaps with your stated preference.")
        elif confirmed_locations and job.location_type not in {"remote", "hybrid"}:
            score = max(score - 4, 0)
            surfaced.append("This location is outside the places you asked the search to prioritize.")
    return score, surfaced


def _eligibility_penalty(
    candidate: CandidateProfile,
    preferences: CandidatePreferenceInput,
    job: NormalizedJob,
    role_score: int,
    seniority_score: int,
    location_score: int,
    missing_required: list[str],
) -> int:
    penalty = 0
    if candidate.seniority == "early-career":
        if job.seniority_band == "senior":
            penalty -= 18
        elif job.seniority_band == "mid-level" and (candidate.years_experience or 0) < 2:
            penalty -= 6
    required_count = len(job.required_skills)
    if missing_required and required_count:
        gap_ratio = len(missing_required) / max(required_count, 1)
        if gap_ratio >= 0.6:
            penalty -= 8
        elif gap_ratio >= 0.4:
            penalty -= 4
    if role_score <= 6:
        penalty -= 5
    if (
        (preferences.confirmed_preferences or {}).get("preferred_locations")
        and preferences.preferred_locations
        and location_score <= 2
        and job.location_type not in {"remote", "hybrid"}
    ):
        penalty -= 5
    return penalty


def _project_fit(candidate: CandidateProfile, job: NormalizedJob) -> tuple[int, list[str]]:
    evidence_pairs: list[tuple[float, str]] = []
    for project in candidate.projects:
        similarity = cosine_similarity(project.summary, job.description_text)
        if similarity > 0:
            evidence_pairs.append((similarity, project.summary))
    for evidence in candidate.evidence_snippets:
        similarity = cosine_similarity(evidence.snippet, job.description_text)
        if similarity > 0:
            evidence_pairs.append((similarity, evidence.snippet))
    evidence_pairs.sort(key=lambda item: item[0], reverse=True)
    transferable = [snippet for _, snippet in evidence_pairs[:3]]
    top_signal = evidence_pairs[0][0] if evidence_pairs else 0.0
    return round(min(top_signal, 1.0) * 10), transferable


def _source_quality_fit(job: NormalizedJob) -> int:
    freshness_bonus = 1.0
    if job.job_age_days is not None:
        freshness_bonus = max(0.25, 1 - min(job.job_age_days, 30) / 40)
    return round(min(job.source_quality * freshness_bonus, 1.0) * 5)


def _feedback_adjustment(job: NormalizedJob, feedback: list[SearchFeedback]) -> int:
    adjustment = 0
    for item in feedback:
        shared_skills = len(set(item.required_skills) & set(job.required_skills))
        same_job = item.job_id == job.id
        same_title = item.normalized_title == job.normalized_title
        same_location_type = item.location_type == job.location_type
        if item.label == "relevant":
            if same_job:
                adjustment += 12
            elif same_title or shared_skills >= 3:
                adjustment += 3
        elif item.label == "good_stretch":
            if same_job:
                adjustment += 6
            elif same_title:
                adjustment += 1
        elif item.label == "irrelevant":
            if same_job:
                adjustment -= 18
            elif same_title:
                adjustment -= 4
        elif item.label == "too_senior":
            if same_job:
                adjustment -= 20
            elif same_title and job.seniority_band in {"mid-level", "senior"}:
                adjustment -= 6
        elif item.label == "wrong_stack":
            if same_job:
                adjustment -= 18
            elif same_title and shared_skills >= 3:
                adjustment -= 4
        elif item.label == "wrong_location":
            if same_job:
                adjustment -= 18
            elif same_location_type and job.location_type != "remote":
                adjustment -= 4
    return max(min(adjustment, 12), -20)


def score_job(
    candidate: CandidateProfile,
    preferences: CandidatePreferenceInput,
    search_plan: SearchPlan,
    job: NormalizedJob,
    feedback: list[SearchFeedback] | None = None,
) -> JobMatch:
    feedback = feedback or []
    role_score, surfaced_reasons = _role_fit(candidate, preferences, search_plan, job)
    required_score, matched_required, missing_required, matched_preferred = _required_skills_fit(candidate, preferences, job)
    adjacent_score, semantic_signal = _adjacent_fit(candidate, preferences, job)
    seniority_score, seniority_risks = _seniority_fit(candidate, job)
    location_score, location_reasons = _location_fit(candidate, preferences, job)
    project_score, transferable = _project_fit(candidate, job)
    source_score = _source_quality_fit(job)
    feedback_adjustment = _feedback_adjustment(job, feedback)
    eligibility_penalty = _eligibility_penalty(
        candidate,
        preferences,
        job,
        role_score,
        seniority_score,
        location_score,
        missing_required,
    )
    total_score = max(
        min(
            role_score
            + required_score
            + adjacent_score
            + seniority_score
            + location_score
            + project_score
            + source_score
            + eligibility_penalty
            + feedback_adjustment,
            100,
        ),
        0,
    )

    matched_skills = dedupe_preserve_order(matched_required + matched_preferred)
    missing_skills = dedupe_preserve_order(missing_required + [skill for skill in job.preferred_skills if skill not in matched_skills])
    score_label = _score_label(total_score)
    recommendation_tier = _recommendation_tier(total_score, missing_required)
    risks = seniority_risks[:]
    if missing_required:
        risks.append(f"Missing hard requirements: {', '.join(missing_required[:3])}.")
    if location_score <= 5:
        risks.append("Location or work-mode fit is weaker than the role fit.")
    if eligibility_penalty <= -12:
        risks.append("Core eligibility signals still look weak for this posting.")
    likely_rejection_driver = _likely_rejection_driver(total_score, missing_required, seniority_score)

    why_apply = (
        "Even if this is a stretch, the role still matches your projects and adjacent skill pattern."
        if recommendation_tier == "Stretch but viable"
        else "This role clears enough of the hard filters to justify a serious application."
    )
    reasoning = (
        f"{score_label}: role fit {role_score}/25, required skills {required_score}/25, "
        f"transferable fit {adjacent_score}/15, seniority {seniority_score}/10, "
        f"location {location_score}/10, projects {project_score}/10, source quality {source_score}/5."
    )

    surfaced_reasons.extend(location_reasons)
    if matched_required:
        surfaced_reasons.append(f"You already cover hard requirements such as {', '.join(matched_required[:3])}.")
    if transferable:
        surfaced_reasons.append("Your project evidence overlaps with the job's real day-to-day work.")
    surfaced_reasons = dedupe_preserve_order(surfaced_reasons)[:4]

    return JobMatch(
        job=job,
        score=total_score,
        score_label=score_label,
        recommendation_tier=recommendation_tier,
        surfaced_reasons=surfaced_reasons,
        hard_requirements_met=matched_required,
        hard_requirements_missing=missing_required,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        transferable_evidence=transferable[:3],
        risk_flags=risks[:4],
        likely_rejection_driver=likely_rejection_driver,
        why_this_is_still_worth_applying=why_apply,
        reasoning=reasoning,
        breakdown=RankingBreakdown(
            role_fit=role_score,
            required_skills_fit=required_score,
            adjacent_fit=adjacent_score,
            seniority_fit=seniority_score,
            location_fit=location_score,
            project_fit=project_score,
            source_quality_fit=source_score,
            semantic_signal=semantic_signal,
            feedback_adjustment=feedback_adjustment + eligibility_penalty,
            explanation=(
                "The final score blends target-role alignment, hard-skill coverage, transferable evidence, "
                "early-career seniority fit, work-mode fit, and job quality signals."
            ),
        ),
    )


def _build_focus_areas(matches: list[JobMatch]) -> list[FocusRecommendation]:
    missing_counter = Counter(
        skill
        for match in matches[:6]
        for skill in match.hard_requirements_missing[:3]
    )
    focus_areas = [
        FocusRecommendation(
            title=f"Strengthen {skill}",
            detail=(
                f"{skill} keeps appearing in your strongest target roles. Add one project bullet or concrete result "
                "using that skill to improve both search recall and ranking strength."
            ),
        )
        for skill, _ in missing_counter.most_common(3)
    ]
    if any(match.recommendation_tier == "Apply now" for match in matches[:5]):
        focus_areas.append(
            FocusRecommendation(
                title="Press on strong-fit roles",
                detail="You already have several roles that look viable enough to apply without major resume changes.",
            )
        )
    return focus_areas[:4]


def _build_narrative(matches: list[JobMatch], candidate: CandidateProfile) -> str:
    if not matches:
        return "No ranked jobs are available yet."
    strongest = matches[0]
    average_score = sum(match.score for match in matches[:10]) // max(min(len(matches), 10), 1)
    strengths = ", ".join(candidate.skills_confirmed[:4] or candidate.core_roles[:2] or ["general engineering potential"])
    return (
        f"Your current profile aligns best with {strongest.job.title} roles. "
        f"Across the top {min(len(matches), 10)} jobs, the average score is {average_score}. "
        f"Current strengths showing up most often: {strengths}."
    )


def analyze_search_results(
    candidate: CandidateProfile,
    preferences: CandidatePreferenceInput,
    jobs: list[NormalizedJob],
    search_plan: SearchPlan,
    provider_statuses: list[ProviderStatus],
    diagnostics: SearchDiagnostics | None = None,
    session_id: str | None = None,
) -> SearchResponse:
    if not jobs:
        raise ValueError("At least one job is required for ranking.")

    session_id = session_id or str(uuid4())
    feedback = _SESSION_FEEDBACK.get(session_id, [])
    matches = sorted(
        [score_job(candidate, preferences, search_plan, job, feedback) for job in jobs],
        key=lambda item: (
            item.score,
            item.breakdown.feedback_adjustment,
            item.breakdown.role_fit,
            item.breakdown.required_skills_fit,
            -(item.job.job_age_days or 9999),
        ),
        reverse=True,
    )

    _SESSION_JOBS[session_id] = {match.job.id: match.job for match in matches}

    missing_counter = Counter(
        skill
        for match in matches[:5]
        for skill in match.hard_requirements_missing[:3]
    )
    top_missing_skills = [
        SkillGap(skill=skill, frequency=count)
        for skill, count in missing_counter.most_common(5)
    ]
    external_factor_roles = [
        match.job.title
        for match in matches[:5]
        if match.likely_rejection_driver == "External factors may matter more"
    ][:3]

    summary = AnalysisSummary(
        strongest_fit=matches[0].job.title if matches else None,
        top_missing_skills=top_missing_skills,
        external_factor_roles=external_factor_roles,
        focus_areas=_build_focus_areas(matches),
        search_terms=search_plan.combined_queries,
        providers_used=dedupe_preserve_order([status.provider for status in provider_statuses if status.fetched_jobs]),
        narrative=_build_narrative(matches, candidate),
    )

    return SearchResponse(
        generated_at=datetime.now(UTC),
        session_id=session_id,
        jobs_analyzed=len(jobs),
        candidate=candidate,
        resume=candidate,
        preferences=preferences,
        search_plan=search_plan,
        provider_statuses=provider_statuses,
        diagnostics=diagnostics or SearchDiagnostics(final_ranked_jobs=len(matches)),
        matches=matches,
        summary=summary,
    )


def record_feedback(request: SearchFeedbackRequest) -> FeedbackResponse:
    job = _SESSION_JOBS.get(request.session_id, {}).get(request.job_id)
    if job is None:
        return FeedbackResponse(saved=False, total_feedback=0)

    feedback = SearchFeedback(
        session_id=request.session_id,
        job_id=request.job_id,
        label=request.label,
        normalized_title=job.normalized_title,
        seniority_band=job.seniority_band,
        location_type=job.location_type,
        required_skills=job.required_skills,
        domain_tags=job.domain_tags,
    )
    _SESSION_FEEDBACK[request.session_id].append(feedback)
    return FeedbackResponse(saved=True, total_feedback=len(_SESSION_FEEDBACK[request.session_id]))

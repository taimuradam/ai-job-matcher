from __future__ import annotations

from collections import Counter

from app.copilot.llm import StructuredLLMClient, maybe_generate_action_plan
from app.copilot.schemas import (
    ActionPlanData,
    CandidateProfileData,
    FeedbackEventData,
    FitAssessmentData,
    FitFeatureScores,
    OpportunityData,
    SearchTargetData,
    TriageDecision,
)
from app.services.taxonomy import cosine_similarity, expand_role_aliases, meaningful_tokens, normalize_text

_SENIORITY_ORDER = {
    "entry-level": 1,
    "mid-level": 2,
    "senior": 3,
    "unknown": 2,
}


def _target_role_terms(target: SearchTargetData) -> list[str]:
    role_terms: list[str] = []
    for role in target.target_roles + target.role_families:
        role_terms.extend(expand_role_aliases(role))
    return list(dict.fromkeys(role_terms))


def _matches_location(target: SearchTargetData, opportunity: OpportunityData) -> bool:
    if not target.preferred_locations:
        return True
    location_text = normalize_text(f"{opportunity.location} {' '.join(opportunity.location_regions)}")
    for preferred in target.preferred_locations:
        normalized = normalize_text(preferred)
        if normalized in location_text or location_text in normalized:
            return True
    return False


def _matches_work_mode(target: SearchTargetData, opportunity: OpportunityData) -> bool:
    if not target.work_modes:
        return True
    return opportunity.location_type in set(target.work_modes) or (
        opportunity.location_type == "remote" and "remote" in target.work_modes
    )


def _matches_employment(target: SearchTargetData, opportunity: OpportunityData) -> bool:
    if not target.employment_preferences:
        return True
    combined = normalize_text(
        " ".join(
            [
                opportunity.title,
                opportunity.employment_type or "",
                opportunity.description_text,
            ]
        )
    )
    return any(normalize_text(item).replace("_", " ") in combined for item in target.employment_preferences)


def _employment_adjustment(target: SearchTargetData, opportunity: OpportunityData) -> tuple[int, list[str]]:
    if not target.employment_preferences:
        return 0, []
    if _matches_employment(target, opportunity):
        return 0, ["Employment type aligns with the current target."]

    combined = normalize_text(
        " ".join(
            [
                opportunity.employment_type or "",
                opportunity.title,
                opportunity.description_text,
            ]
        )
    )
    if combined:
        return -6, ["Employment type is outside the target you configured."]
    return -3, ["Employment type is unclear, so the opportunity is harder to trust."]


def _role_score(target: SearchTargetData, opportunity: OpportunityData) -> tuple[int, list[str]]:
    title_text = normalize_text(f"{opportunity.title} {opportunity.normalized_title}")
    signals: list[str] = []
    for role in target.target_roles:
        if normalize_text(role) in title_text:
            signals.append(f"Direct title match for {role}.")
            return 30, signals
    for family in target.role_families:
        if normalize_text(family) in title_text:
            signals.append(f"Role family alignment with {family}.")
            return 24, signals

    semantic = max(
        (cosine_similarity(opportunity.title, role) for role in _target_role_terms(target)),
        default=0.0,
    )
    token_hits = sum(
        1
        for token in meaningful_tokens(" ".join(target.query_terms))
        if token in title_text
    )
    score = min(20, round((semantic * 16) + token_hits * 2))
    if score:
        signals.append("Title is a plausible adjacent or transferable match.")
    return score, signals


def _skills_score(
    profile: CandidateProfileData,
    target: SearchTargetData,
    opportunity: OpportunityData,
) -> tuple[int, list[str], list[str]]:
    candidate_skills = set(profile.skills_confirmed) | set(profile.skills_inferred) | set(target.must_have_skills)
    required = opportunity.required_skills or opportunity.preferred_skills
    matched = sorted(candidate_skills & set(required))
    missing = sorted(set(required) - candidate_skills)
    preferred_overlap = len(candidate_skills & set(opportunity.preferred_skills))
    score = 0
    if required:
        score = round((len(matched) / len(required)) * 22)
    if preferred_overlap:
        score += min(preferred_overlap, 3)
    return min(score, 25), matched, missing


def _seniority_score(target: SearchTargetData, opportunity: OpportunityData) -> tuple[int, list[str]]:
    risks: list[str] = []
    ceiling = _SENIORITY_ORDER.get(target.seniority_ceiling, 2)
    opportunity_level = _SENIORITY_ORDER.get(opportunity.seniority_band, 2)
    if opportunity_level > ceiling:
        risks.append("Posting exceeds the configured seniority ceiling.")
        return 0, risks
    if opportunity.seniority_band == "entry-level":
        return 15, risks
    if opportunity.seniority_band == "mid-level":
        if ceiling == 1:
            risks.append("This looks slightly above the preferred seniority range.")
            return 7, risks
        return 11, risks
    return 8, risks


def _location_score(target: SearchTargetData, opportunity: OpportunityData) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 10
    if target.work_modes:
        if opportunity.location_type in target.work_modes:
            reasons.append("Work mode aligns with the current target.")
        elif target.strict_work_mode:
            score = 0
            reasons.append("Work mode is outside the strict target settings.")
        else:
            score = 4
            reasons.append("Work mode is workable but not preferred.")

    if target.preferred_locations:
        if _matches_location(target, opportunity):
            score = min(score + 2, 10)
            reasons.append("Location overlaps with the stated target region.")
        elif target.strict_location and opportunity.location_type not in {"remote", "hybrid"}:
            score = 0
            reasons.append("Location is outside the strict target region.")
        else:
            score = min(score, 5)
    return score, reasons


def _evidence_score(profile: CandidateProfileData, opportunity: OpportunityData) -> tuple[int, list[str]]:
    evidence_pairs: list[tuple[float, str]] = []
    for project in profile.projects:
        similarity = cosine_similarity(project.summary, opportunity.description_text)
        if similarity > 0:
            evidence_pairs.append((similarity, project.summary))
    for evidence in profile.evidence:
        similarity = cosine_similarity(evidence.detail, opportunity.description_text)
        if similarity > 0:
            evidence_pairs.append((similarity, evidence.detail))
    evidence_pairs.sort(key=lambda item: item[0], reverse=True)
    top = [detail for _, detail in evidence_pairs[:3]]
    top_signal = evidence_pairs[0][0] if evidence_pairs else 0.0
    return round(min(top_signal, 1.0) * 10), top


def _freshness_score(opportunity: OpportunityData) -> int:
    if opportunity.job_age_days is None:
        return 3
    return max(1, min(5, 5 - (opportunity.job_age_days // 7)))


def _source_quality_score(opportunity: OpportunityData) -> int:
    return max(1, min(5, round(opportunity.source_quality * 5)))


def _feedback_adjustment(opportunity: OpportunityData, feedback_events: list[FeedbackEventData]) -> int:
    adjustment = 0
    for event in feedback_events:
        shared_skills = len(set(event.required_skills) & set(opportunity.required_skills))
        same_title = event.normalized_title == opportunity.normalized_title
        same_location = event.location_type == opportunity.location_type
        if same_title:
            relevance = 1.0
        elif shared_skills >= 2:
            relevance = 0.25 if event.label == "wrong_stack" else 0.5
        elif same_location and event.label == "wrong_location":
            relevance = 0.5
        else:
            continue

        if event.label in {"apply", "relevant"}:
            adjustment += round(6 * relevance)
        elif event.label == "tailor":
            adjustment += round(3 * relevance)
        elif event.label == "monitor":
            adjustment += round(1 * relevance)
        elif event.label in {"skip", "wrong_stack", "wrong_location", "too_senior"}:
            adjustment -= round(8 * relevance)
    return max(-10, min(10, adjustment))


def _eligible(
    profile: CandidateProfileData,
    target: SearchTargetData,
    opportunity: OpportunityData,
    *,
    role_score: int,
    matched_skills: list[str],
    missing_skills: list[str],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    combined = normalize_text(f"{opportunity.title} {opportunity.description_text}")
    if target.excluded_keywords and any(normalize_text(term) in combined for term in target.excluded_keywords):
        reasons.append("Matched an excluded keyword.")
    if role_score < 8:
        reasons.append("Role family alignment is too weak.")
    if _SENIORITY_ORDER.get(opportunity.seniority_band, 2) > _SENIORITY_ORDER.get(target.seniority_ceiling, 2):
        reasons.append("Opportunity exceeds the target seniority ceiling.")
    if target.strict_location and not _matches_location(target, opportunity) and opportunity.location_type not in {"remote", "hybrid"}:
        reasons.append("Opportunity is outside the strict location filter.")
    if target.strict_work_mode and not _matches_work_mode(target, opportunity):
        reasons.append("Opportunity is outside the strict work-mode filter.")
    if target.strict_employment and not _matches_employment(target, opportunity):
        reasons.append("Opportunity does not match the strict employment filter.")
    if target.strict_must_have and target.must_have_skills:
        covered = len(set(target.must_have_skills) & set(matched_skills))
        if covered < min(len(target.must_have_skills), 2):
            reasons.append("Must-have skills coverage is too weak for strict mode.")
    return not reasons, reasons


def _triage_decision(eligible: bool, total_score: int, missing_skills: list[str]) -> TriageDecision:
    if not eligible:
        return "skip"
    if total_score >= 78 and len(missing_skills) <= 1:
        return "apply"
    if total_score >= 60:
        return "tailor"
    if total_score >= 42:
        return "monitor"
    return "skip"


def assess_opportunity(
    profile: CandidateProfileData,
    target: SearchTargetData,
    opportunity: OpportunityData,
    *,
    feedback_events: list[FeedbackEventData] | None = None,
) -> FitAssessmentData:
    feedback_events = feedback_events or []
    role_score, role_signals = _role_score(target, opportunity)
    skills_score, matched_skills, missing_skills = _skills_score(profile, target, opportunity)
    seniority_score, seniority_risks = _seniority_score(target, opportunity)
    location_score, location_reasons = _location_score(target, opportunity)
    evidence_score, evidence = _evidence_score(profile, opportunity)
    freshness_score = _freshness_score(opportunity)
    source_score = _source_quality_score(opportunity)
    employment_adjustment, employment_reasons = _employment_adjustment(target, opportunity)
    feedback_score = _feedback_adjustment(opportunity, feedback_events)
    eligible, ineligibility_reasons = _eligible(
        profile,
        target,
        opportunity,
        role_score=role_score,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
    )
    total = max(
        0,
        min(
            100,
            role_score
            + skills_score
            + seniority_score
            + location_score
            + evidence_score
            + freshness_score
            + source_score
            + employment_adjustment
            + feedback_score,
        ),
    )
    triage = _triage_decision(eligible, total, missing_skills)
    risks = seniority_risks[:]
    if missing_skills:
        risks.append(f"Missing requirements: {', '.join(missing_skills[:3])}.")
    if not evidence:
        risks.append("The job description has limited overlap with existing project evidence.")
    if employment_adjustment < 0:
        risks.extend(employment_reasons)
    explanation = [
        f"Role alignment {role_score}/30 and skills alignment {skills_score}/25 are driving the current fit.",
        f"Seniority {seniority_score}/15, location {location_score}/10, evidence {evidence_score}/10, freshness {freshness_score}/5, source quality {source_score}/5.",
    ]
    if employment_reasons:
        explanation.append(employment_reasons[0])
    if feedback_score:
        explanation.append(f"Feedback history adjusted the score by {feedback_score}.")
    return FitAssessmentData(
        eligible=eligible,
        ineligibility_reasons=ineligibility_reasons,
        matched_signals=(role_signals + location_reasons)[:5],
        missing_requirements=missing_skills,
        risk_flags=risks[:4],
        evidence=evidence,
        explanation=explanation,
        scores=FitFeatureScores(
            role_alignment=role_score,
            skills_alignment=skills_score,
            seniority_alignment=seniority_score,
            location_alignment=location_score,
            evidence_strength=evidence_score,
            freshness=freshness_score,
            source_quality=source_score,
            feedback_adjustment=feedback_score,
            total=total,
        ),
        triage_decision=triage,
    )


def build_action_plan(
    profile: CandidateProfileData,
    target: SearchTargetData,
    opportunity: OpportunityData,
    assessment: FitAssessmentData,
    *,
    llm_client: StructuredLLMClient | None = None,
) -> ActionPlanData | None:
    if assessment.triage_decision not in {"apply", "tailor"}:
        return None

    strongest_evidence = assessment.evidence[:3] or [
        f"Confirmed skills include {', '.join(profile.skills_confirmed[:3])}."
    ]
    missing = assessment.missing_requirements[:4]
    tailoring_steps = []
    if strongest_evidence:
        tailoring_steps.append("Move the most relevant project or work sample into the top half of the resume.")
    if missing:
        tailoring_steps.append(
            f"Address the gap around {', '.join(missing[:2])} with one concrete project bullet or coursework example."
        )
    if target.must_have_skills:
        tailoring_steps.append(
            f"Reinforce target stack terms such as {', '.join(target.must_have_skills[:3])} in the summary and skills sections."
        )
    tailoring_steps.append("Mirror the posting language in one or two resume bullets without copying whole sentences.")

    default_plan = ActionPlanData(
        generated_by="deterministic",
        summary=(
            "High-confidence application target."
            if assessment.triage_decision == "apply"
            else "Worth tailoring before applying."
        ),
        missing_requirements=missing,
        strongest_evidence=strongest_evidence,
        resume_tailoring_steps=tailoring_steps[:4],
    )
    assessment_summary = " ".join(assessment.explanation + assessment.risk_flags)
    return maybe_generate_action_plan(
        default_plan=default_plan,
        profile=profile,
        opportunity_title=opportunity.title,
        assessment_summary=assessment_summary,
        llm_client=llm_client,
    )


def summarize_feedback(labels: list[str]) -> dict[str, int]:
    return dict(Counter(labels))

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import UTC, datetime

from app.schemas import (
    AnalysisResponse,
    AnalysisSummary,
    FocusRecommendation,
    JobMatch,
    JobRecord,
    MatchBreakdown,
    ResumeProfile,
    SkillGap,
)

SKILL_ALIASES: dict[str, set[str]] = {
    "Python": {"python"},
    "FastAPI": {"fastapi"},
    "SQL": {"sql", "postgresql", "mysql", "sqlite"},
    "Pandas": {"pandas"},
    "NumPy": {"numpy"},
    "scikit-learn": {"scikit-learn", "sklearn"},
    "PyTorch": {"pytorch"},
    "TensorFlow": {"tensorflow"},
    "OpenAI API": {"openai api", "openai", "gpt-4", "gpt-4o", "gpt", "llm", "llms"},
    "LangChain": {"langchain"},
    "RAG": {"rag", "retrieval augmented generation", "retrieval-augmented generation"},
    "Docker": {"docker", "containerization"},
    "Kubernetes": {"kubernetes", "k8s"},
    "Git": {"git", "github", "gitlab"},
    "JavaScript": {"javascript", "js"},
    "TypeScript": {"typescript", "ts"},
    "React": {"react", "next.js", "nextjs"},
    "Node.js": {"node.js", "nodejs", "node"},
    "REST APIs": {"rest", "restful", "api design", "apis"},
    "Machine Learning": {"machine learning", "ml"},
    "Data Analysis": {"data analysis", "analytics", "analysis"},
    "Data Visualization": {"data visualization", "tableau", "power bi", "matplotlib", "seaborn"},
    "A/B Testing": {"a/b testing", "experimentation"},
    "NLP": {"nlp", "natural language processing"},
    "AWS": {"aws", "amazon web services", "s3", "ec2", "lambda"},
    "Azure": {"azure"},
    "GCP": {"gcp", "google cloud"},
    "CI/CD": {"ci/cd", "continuous integration", "continuous delivery", "github actions"},
}

CLUSTER_KEYWORDS: dict[str, set[str]] = {
    "backend": {"Python", "FastAPI", "SQL", "Docker", "REST APIs", "AWS"},
    "data": {"Python", "SQL", "Pandas", "NumPy", "Data Analysis", "Data Visualization"},
    "ml": {"Python", "Machine Learning", "PyTorch", "TensorFlow", "scikit-learn", "NLP", "RAG", "OpenAI API"},
    "frontend": {"JavaScript", "TypeScript", "React"},
}

DEGREE_PATTERNS = {
    "Bachelor's": r"\b(bachelor|b\.s\.|bs|b\.a\.|ba)\b",
    "Master's": r"\b(master|m\.s\.|ms|m\.eng)\b",
    "PhD": r"\b(phd|doctorate)\b",
    "Bootcamp": r"\bbootcamp\b",
}

STOP_WORDS = {
    "and",
    "for",
    "with",
    "the",
    "that",
    "this",
    "from",
    "into",
    "role",
    "intern",
    "internship",
    "engineer",
    "engineering",
    "developer",
    "analyst",
    "scientist",
    "you",
    "your",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def extract_skills(text: str) -> list[str]:
    normalized = normalize_text(text)
    found = {
        canonical
        for canonical, aliases in SKILL_ALIASES.items()
        if any(re.search(rf"(?<!\w){re.escape(alias.lower())}(?!\w)", normalized) for alias in aliases)
    }
    return sorted(found)


def extract_years_of_experience(text: str) -> float | None:
    normalized = normalize_text(text)
    explicit_years = [
        int(match.group(1))
        for match in re.finditer(r"(\d{1,2})\+?\s+(?:years|yrs)\b", normalized)
    ]
    if explicit_years:
        return float(max(explicit_years))

    year_values = [
        int(match.group(0))
        for match in re.finditer(r"\b(20\d{2}|19\d{2})\b", normalized)
    ]
    current_year = datetime.now().year
    plausible_years = [year for year in year_values if 1995 <= year <= current_year]
    if plausible_years:
        return float(max(current_year - min(plausible_years), 0))
    return None


def extract_education(text: str) -> list[str]:
    normalized = normalize_text(text)
    findings = [label for label, pattern in DEGREE_PATTERNS.items() if re.search(pattern, normalized)]
    return findings


def extract_resume_signals(text: str) -> list[str]:
    signals: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) > 120:
            stripped = stripped[:117] + "..."
        if "@" in stripped or stripped.startswith(("http", "www.")):
            continue
        signals.append(stripped)
        if len(signals) == 4:
            break
    return signals


def build_resume_profile(filename: str, resume_text: str) -> ResumeProfile:
    return ResumeProfile(
        filename=filename,
        skills=extract_skills(resume_text),
        experience_years=extract_years_of_experience(resume_text),
        education=extract_education(resume_text),
        signals=extract_resume_signals(resume_text),
    )


def infer_clusters(skills: list[str], text: str) -> set[str]:
    inferred = {
        cluster
        for cluster, cluster_skills in CLUSTER_KEYWORDS.items()
        if set(skills) & cluster_skills
    }
    normalized = normalize_text(text)
    if "dashboard" in normalized or "analytics" in normalized:
        inferred.add("data")
    if "api" in normalized or "microservice" in normalized:
        inferred.add("backend")
    if "model" in normalized or "llm" in normalized:
        inferred.add("ml")
    if "frontend" in normalized or "ui" in normalized:
        inferred.add("frontend")
    return inferred


def _meaningful_tokens(text: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z\-\+\.#]+", text.lower())
        if token not in STOP_WORDS and len(token) > 2
    }
    return tokens


def _title_score(resume_text: str, job: JobRecord) -> tuple[int, float]:
    title_tokens = _meaningful_tokens(job.title)
    if not title_tokens:
        return 0, 0.0
    resume_tokens = _meaningful_tokens(resume_text)
    overlap = len(title_tokens & resume_tokens) / len(title_tokens)
    return round(overlap * 15), overlap


def _experience_score(resume_years: float | None, job_text: str) -> tuple[int, float]:
    match = re.findall(r"(\d{1,2})\+?\s+(?:years|yrs)\b", normalize_text(job_text))
    if not match:
        return 12, 0.8
    required_years = max(int(value) for value in match)
    if resume_years is None:
        return 8, 0.55
    ratio = min(resume_years / required_years, 1.0)
    return round(ratio * 15), ratio


def _context_score(resume_skills: list[str], resume_text: str, job_text: str) -> tuple[int, float]:
    resume_clusters = infer_clusters(resume_skills, resume_text)
    job_skills = extract_skills(job_text)
    job_clusters = infer_clusters(job_skills, job_text)
    if not job_clusters:
        return 10, 0.66
    overlap = len(resume_clusters & job_clusters) / len(job_clusters)
    return round(overlap * 15), overlap


def _score_label(score: int) -> str:
    if score >= 80:
        return "Strong fit"
    if score >= 65:
        return "Promising fit"
    if score >= 50:
        return "Stretch fit"
    return "Low fit"


def _rejection_driver(score: int, missing_skills: list[str], experience_ratio: float) -> str:
    if score >= 72 and len(missing_skills) <= 2:
        return "External factors may matter more"
    if score < 60 and len(missing_skills) >= 3:
        return "Missing skills are the main risk"
    if experience_ratio < 0.5:
        return "Experience gap is likely the blocker"
    return "Mixed signal"


def _reasoning(
    matched_skills: list[str],
    missing_skills: list[str],
    score_label: str,
    driver: str,
) -> str:
    matched = ", ".join(matched_skills[:4]) if matched_skills else "limited overlap"
    missing = ", ".join(missing_skills[:3]) if missing_skills else "no major missing skills"
    return (
        f"{score_label}: matched on {matched}. "
        f"Main gap signal: {missing}. "
        f"Assessment: {driver.lower()}."
    )


def score_job(resume_profile: ResumeProfile, resume_text: str, job: JobRecord) -> JobMatch:
    job_text = f"{job.title}\n{job.description}"
    job_skills = extract_skills(job_text)
    resume_skill_set = set(resume_profile.skills)
    matched_skills = sorted(resume_skill_set & set(job_skills))
    missing_skills = sorted(set(job_skills) - resume_skill_set)

    skill_ratio = len(matched_skills) / max(len(job_skills), 1)
    skill_score = round(skill_ratio * 55)
    title_score, _ = _title_score(resume_text, job)
    experience_score, experience_ratio = _experience_score(
        resume_profile.experience_years,
        job_text,
    )
    context_score, context_ratio = _context_score(
        resume_profile.skills,
        resume_text,
        job_text,
    )
    total_score = min(skill_score + title_score + experience_score + context_score, 100)
    score_label = _score_label(total_score)
    driver = _rejection_driver(total_score, missing_skills, experience_ratio)
    explanation = (
        f"Skills overlap drives {skill_score}/55. "
        f"Title alignment adds {title_score}/15, "
        f"experience fit adds {experience_score}/15, and "
        f"context alignment adds {context_score}/15."
    )

    return JobMatch(
        job=job,
        score=total_score,
        score_label=score_label,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        likely_rejection_driver=driver,
        reasoning=_reasoning(matched_skills, missing_skills, score_label, driver),
        breakdown=MatchBreakdown(
            skill_score=skill_score,
            title_score=title_score,
            experience_score=experience_score,
            context_score=context_score,
            explanation=explanation,
        ),
    )


def _build_focus_areas(matches: list[JobMatch]) -> list[FocusRecommendation]:
    top_matches = matches[:5]
    missing_counter = Counter(
        skill
        for match in top_matches
        for skill in match.missing_skills[:4]
    )
    focus_areas: list[FocusRecommendation] = []
    for skill, frequency in missing_counter.most_common(3):
        focus_areas.append(
            FocusRecommendation(
                title=f"Close the {skill} gap",
                detail=(
                    f"{skill} appears in {frequency} of your top target roles. "
                    "Adding one concrete project or internship bullet for it would "
                    "improve future match quality."
                ),
            )
        )

    strong_roles = [match.job.title for match in top_matches if match.score >= 72]
    if strong_roles:
        focus_areas.append(
            FocusRecommendation(
                title="Keep applying to adjacent roles",
                detail=(
                    "Several roles already show strong overlap. Rejections in this range "
                    "are more likely to include competition, timing, or applicant volume."
                ),
            )
        )
    return focus_areas[:4]


def _build_narrative(matches: list[JobMatch], resume: ResumeProfile) -> str:
    if not matches:
        return "No jobs were available for analysis."

    strongest = matches[0]
    avg_score = math.floor(sum(match.score for match in matches) / len(matches))
    return (
        f"Your resume currently aligns best with {strongest.job.title} roles. "
        f"Across {len(matches)} jobs, the average fit score is {avg_score}. "
        f"Core strengths detected: {', '.join(resume.skills[:5]) or 'not enough structured skills yet'}. "
        "Use the missing-skill patterns to decide which projects or learning sprints "
        "will create the biggest lift in future applications."
    )


def analyze_resume_against_jobs(
    resume_filename: str,
    resume_text: str,
    jobs: list[JobRecord],
    search_terms: list[str] | None = None,
    providers_used: list[str] | None = None,
) -> AnalysisResponse:
    if not resume_text.strip():
        raise ValueError("The resume did not contain any readable text.")
    if not jobs:
        raise ValueError("At least one job description is required for scoring.")

    resume_profile = build_resume_profile(resume_filename, resume_text)
    matches = sorted(
        [score_job(resume_profile, resume_text, job) for job in jobs],
        key=lambda item: item.score,
        reverse=True,
    )

    missing_counter = Counter(
        skill
        for match in matches[:5]
        for skill in match.missing_skills[:4]
    )
    top_missing_skills = [
        SkillGap(skill=skill, frequency=count)
        for skill, count in missing_counter.most_common(5)
    ]
    external_factor_roles = [
        match.job.title
        for match in matches
        if match.likely_rejection_driver == "External factors may matter more"
    ][:3]

    return AnalysisResponse(
        generated_at=datetime.now(UTC),
        jobs_analyzed=len(jobs),
        resume=resume_profile,
        matches=matches,
        summary=AnalysisSummary(
            strongest_fit=matches[0].job.title if matches else None,
            top_missing_skills=top_missing_skills,
            external_factor_roles=external_factor_roles,
            focus_areas=_build_focus_areas(matches),
            search_terms=search_terms or [],
            providers_used=providers_used or [],
            narrative=_build_narrative(matches, resume_profile),
        ),
    )

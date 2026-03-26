from __future__ import annotations

import json
from pathlib import Path

from app.schemas import CandidatePreferenceInput, JobRecord, ProviderStatus
from app.services.job_search import apply_search_funnel, build_search_plan, normalize_job
from app.services.profile_extraction import build_candidate_profile
from app.services.scoring import analyze_search_results


def run_benchmark_suite(path: Path) -> dict[str, float]:
    cases = json.loads(path.read_text())
    total_cases = len(cases)
    precision_scores: list[float] = []
    reciprocal_ranks: list[float] = []
    relevant_result_rates: list[float] = []
    too_senior_rates: list[float] = []

    for case in cases:
        candidate = build_candidate_profile(case["resume_filename"], case["resume_text"])
        preferences = CandidatePreferenceInput(**case.get("preferences", {}))
        jobs = [normalize_job(JobRecord(**job)) for job in case["jobs"]]
        response = analyze_search_results(
            candidate=candidate,
            preferences=preferences,
            jobs=jobs,
            search_plan=build_search_plan(candidate, preferences),
            provider_statuses=[ProviderStatus(provider="Benchmark", status="ok", fetched_jobs=len(jobs), normalized_jobs=len(jobs), freshness="fixture", source_quality=1.0)],
            session_id=f"benchmark-{case['name']}",
        )

        expected_titles = [title.lower() for title in case["expected_top_titles"]]
        top_matches = response.matches[:5]
        relevant_hits = [
            index + 1
            for index, match in enumerate(top_matches)
            if any(expected in match.job.title.lower() for expected in expected_titles)
        ]
        precision_scores.append(len(relevant_hits) / max(len(top_matches), 1))
        relevant_result_rates.append(1.0 if relevant_hits else 0.0)
        reciprocal_ranks.append(1 / relevant_hits[0] if relevant_hits else 0.0)
        top_window = response.matches[:2]
        too_senior_rates.append(
            sum(1 for match in top_window if match.job.seniority_band == "senior") / max(len(top_window), 1)
        )

    return {
        "cases": float(total_cases),
        "precision_at_5": sum(precision_scores) / max(total_cases, 1),
        "mrr": sum(reciprocal_ranks) / max(total_cases, 1),
        "relevant_result_rate": sum(relevant_result_rates) / max(total_cases, 1),
        "too_senior_rate": sum(too_senior_rates) / max(total_cases, 1),
    }


def evaluate_saved_search_case(path: Path) -> dict[str, object]:
    case = json.loads(path.read_text())
    candidate = build_candidate_profile(case["resume_filename"], case["resume_text"])
    preferences = CandidatePreferenceInput(**case.get("preferences", {}))
    raw_jobs = [JobRecord(**job) for job in case["jobs"]]
    jobs = [normalize_job(job) for job in raw_jobs]
    filtered_jobs, search_plan, diagnostics = apply_search_funnel(
        candidate=candidate,
        preferences=preferences,
        jobs=jobs,
        search_plan=build_search_plan(candidate, preferences),
        fetched_jobs=len(raw_jobs),
    )
    response = analyze_search_results(
        candidate=candidate,
        preferences=preferences,
        jobs=filtered_jobs,
        search_plan=search_plan,
        provider_statuses=[
            ProviderStatus(
                provider="Snapshot",
                status="ok",
                fetched_jobs=len(raw_jobs),
                normalized_jobs=len(filtered_jobs),
                freshness="fixture",
                source_quality=1.0,
            )
        ],
        diagnostics=diagnostics,
        session_id=f"saved-case-{case['name']}",
    )
    top_titles = [match.job.title for match in response.matches[:5]]
    role_hits = sum(
        1
        for title in top_titles
        if any(expected in title.lower() for expected in case.get("expected_top_titles", []))
    )
    return {
        "jobs_after_funnel": diagnostics.final_ranked_jobs,
        "top_5_role_hits": role_hits,
        "top_titles": top_titles,
        "diagnostics": diagnostics.model_dump(),
    }

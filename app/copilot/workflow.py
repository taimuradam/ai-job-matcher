from __future__ import annotations

from collections import Counter

from app.copilot.fit_engine import assess_opportunity, build_action_plan
from app.copilot.llm import StructuredLLMClient
from app.copilot.normalizer import dedupe_opportunities, normalize_listing
from app.copilot.schemas import (
    ActionPlanData,
    CandidateProfileRecord,
    OpportunityData,
    ProviderFetchStatus,
    RawListingData,
    SearchRunDetailResponse,
    SearchRunDiagnostics,
    SearchRunRecord,
    SearchTargetRecord,
)
from app.copilot.source_orchestrator import collect_live_listings
from app.copilot.storage import SQLiteStore


def _active_filters(target_record: SearchTargetRecord) -> list[str]:
    target = target_record.target
    filters: list[str] = []
    if target.strict_location and target.preferred_locations:
        filters.append("strict_location")
    if target.strict_work_mode and target.work_modes:
        filters.append("strict_work_mode")
    if target.strict_employment and target.employment_preferences:
        filters.append("strict_employment")
    if target.strict_must_have and target.must_have_skills:
        filters.append("strict_must_have")
    if target.excluded_keywords:
        filters.append("excluded_keywords")
    return filters


async def run_search(
    *,
    store: SQLiteStore,
    profile_record: CandidateProfileRecord,
    target_record: SearchTargetRecord,
    refresh_action_plans: bool = True,
    llm_client: StructuredLLMClient | None = None,
) -> SearchRunDetailResponse:
    run = store.create_search_run(profile_record=profile_record, target_record=target_record)
    live = await collect_live_listings(target_record.target)
    live_pairs = store.save_run_raw_listings(run_id=run.id, listings=live.listings)
    imported_pairs = store.list_imported_raw_listings() if target_record.target.providers.imports else []

    normalized: list[OpportunityData] = [
        normalize_listing(listing, raw_listing_id=raw_listing_id)
        for raw_listing_id, listing in [*live_pairs, *imported_pairs]
    ]
    deduped = dedupe_opportunities(normalized)

    statuses = live.statuses[:]
    if target_record.target.providers.imports:
        statuses.append(
            ProviderFetchStatus(
                provider="Imports",
                source_type="import",
                status="ok" if imported_pairs else "empty",
                fetched_count=len(imported_pairs),
                query_terms=[],
            )
        )
    for status in statuses:
        status.normalized_count = sum(
            1
            for opportunity in deduped
            if (
                status.provider == "Imports"
                and opportunity.source_type == "import"
            )
            or opportunity.source == status.provider
        )

    excluded_counts: Counter[str] = Counter()
    assessments = {}
    action_plans: dict[str, ActionPlanData] = {}
    all_feedback_events = store.feedback_events()
    for opportunity in deduped:
        assessment = assess_opportunity(
            profile_record.profile,
            target_record.target,
            opportunity,
            feedback_events=all_feedback_events,
        )
        assessments[opportunity.id] = assessment
        if not assessment.eligible:
            for reason in assessment.ineligibility_reasons:
                excluded_counts[reason] += 1
        if refresh_action_plans:
            plan = build_action_plan(
                profile_record.profile,
                target_record.target,
                opportunity,
                assessment,
                llm_client=llm_client,
            )
            if plan is not None:
                action_plans[opportunity.id] = plan

    actionable = sum(
        1
        for assessment in assessments.values()
        if assessment.triage_decision in {"apply", "tailor"}
    )
    diagnostics = SearchRunDiagnostics(
        fetched_listings=len(live.listings) + len(imported_pairs),
        normalized_opportunities=len(normalized),
        deduped_opportunities=len(deduped),
        eligible_opportunities=sum(1 for assessment in assessments.values() if assessment.eligible),
        actionable_opportunities=actionable,
        provider_failures=sum(1 for status in statuses if status.error),
        excluded_counts=dict(excluded_counts),
        active_filters=_active_filters(target_record),
        query_plan=live.query_terms,
    )
    run.diagnostics = diagnostics
    run.provider_statuses = statuses
    run = store.finalize_search_run(
        run=run,
        diagnostics=diagnostics,
        provider_statuses=statuses,
        opportunities=deduped,
        assessments=assessments,
        action_plans=action_plans,
    )
    return store.search_run(run.id)

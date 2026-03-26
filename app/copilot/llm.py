from __future__ import annotations

from typing import Protocol

from pydantic import ValidationError

from app.copilot.schemas import ActionPlanData, CandidateProfileData, LLMStatus


class StructuredLLMClient(Protocol):
    provider_name: str

    def profile_grounding(self, *, resume_text: str, profile: CandidateProfileData) -> dict:
        ...

    def action_plan(
        self,
        *,
        profile: CandidateProfileData,
        opportunity_title: str,
        assessment_summary: str,
    ) -> dict:
        ...


def maybe_enrich_profile(
    *,
    resume_text: str,
    profile: CandidateProfileData,
    llm_client: StructuredLLMClient | None = None,
) -> tuple[CandidateProfileData, LLMStatus]:
    if llm_client is None:
        return profile, LLMStatus(mode="disabled", detail="No LLM client configured.")

    try:
        payload = llm_client.profile_grounding(resume_text=resume_text, profile=profile)
        enriched = CandidateProfileData.model_validate(payload)
        return enriched, LLMStatus(mode="enriched", provider=llm_client.provider_name)
    except (ValidationError, TypeError, ValueError) as exc:
        return profile, LLMStatus(
            mode="fallback",
            provider=llm_client.provider_name,
            detail=f"LLM output was invalid and deterministic fallback was used: {exc}",
        )
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        return profile, LLMStatus(
            mode="failed",
            provider=llm_client.provider_name,
            detail=f"LLM enrichment failed and deterministic fallback was used: {exc}",
        )


def maybe_generate_action_plan(
    *,
    default_plan: ActionPlanData,
    profile: CandidateProfileData,
    opportunity_title: str,
    assessment_summary: str,
    llm_client: StructuredLLMClient | None = None,
) -> ActionPlanData:
    if llm_client is None:
        return default_plan

    try:
        payload = llm_client.action_plan(
            profile=profile,
            opportunity_title=opportunity_title,
            assessment_summary=assessment_summary,
        )
        plan = ActionPlanData.model_validate(payload)
        plan.generated_by = llm_client.provider_name
        return plan
    except (ValidationError, TypeError, ValueError):
        return default_plan
    except Exception:  # pragma: no cover - defensive runtime guard
        return default_plan

import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type WizardStep = 1 | 2 | 3 | 4;
type ImportFormat = "json" | "csv" | "urls";
type TriageDecision = "apply" | "tailor" | "monitor" | "skip";
type FeedbackLabel =
  | "apply"
  | "tailor"
  | "monitor"
  | "skip"
  | "relevant"
  | "wrong_stack"
  | "wrong_location"
  | "too_senior";

interface LLMStatus {
  mode: "disabled" | "enriched" | "fallback" | "failed";
  provider: string | null;
  detail: string | null;
}

interface EvidenceItem {
  label: string;
  detail: string;
  confidence: number;
}

interface ProjectSignal {
  title: string;
  summary: string;
  related_skills: string[];
  confidence: number;
}

interface CandidateProfileData {
  filename: string;
  summary: string | null;
  skills_confirmed: string[];
  skills_inferred: string[];
  core_roles: string[];
  adjacent_roles: string[];
  seniority: string;
  industries: string[];
  preferred_locations: string[];
  remote_preference: string;
  employment_preferences: string[];
  education_level: string[];
  years_experience: number | null;
  projects: ProjectSignal[];
  evidence: EvidenceItem[];
  confidence: Record<string, number>;
  signals: string[];
  llm_summary: string | null;
}

interface SourceSelection {
  remotive: boolean;
  remoteok: boolean;
  imports: boolean;
}

interface SearchTargetData {
  target_roles: string[];
  role_families: string[];
  query_terms: string[];
  preferred_locations: string[];
  work_modes: string[];
  employment_preferences: string[];
  must_have_skills: string[];
  excluded_keywords: string[];
  seniority_ceiling: string;
  search_mode: string;
  strict_location: boolean;
  strict_work_mode: boolean;
  strict_employment: boolean;
  strict_must_have: boolean;
  providers: SourceSelection;
}

interface CandidateProfileRecord {
  id: string;
  version: number;
  created_at: string;
  profile: CandidateProfileData;
  llm_status: LLMStatus;
}

interface SearchTargetRecord {
  id: string;
  profile_id: string;
  profile_version: number;
  version: number;
  created_at: string;
  target: SearchTargetData;
}

interface ProviderFetchStatus {
  provider: string;
  source_type: string;
  status: string;
  fetched_count: number;
  normalized_count: number;
  query_terms: string[];
  error: string | null;
}

interface SearchRunDiagnostics {
  fetched_listings: number;
  normalized_opportunities: number;
  deduped_opportunities: number;
  eligible_opportunities: number;
  actionable_opportunities: number;
  provider_failures: number;
  excluded_counts: Record<string, number>;
  active_filters: string[];
  query_plan: string[];
}

interface SearchRunRecord {
  id: string;
  profile_id: string;
  profile_version: number;
  target_id: string;
  target_version: number;
  created_at: string;
  diagnostics: SearchRunDiagnostics;
  provider_statuses: ProviderFetchStatus[];
}

interface OpportunityData {
  id: string;
  raw_listing_id: string | null;
  dedupe_key: string;
  title: string;
  normalized_title: string;
  company: string;
  location: string;
  location_type: string;
  location_regions: string[];
  description_text: string;
  employment_type: string | null;
  seniority_band: string;
  required_skills: string[];
  preferred_skills: string[];
  domain_tags: string[];
  salary_range: string | null;
  visa_support: string | null;
  published_at: string | null;
  job_age_days: number | null;
  source: string;
  source_type: string;
  source_quality: number;
  apply_url: string | null;
}

interface FitScores {
  role_alignment: number;
  skills_alignment: number;
  seniority_alignment: number;
  location_alignment: number;
  evidence_strength: number;
  freshness: number;
  source_quality: number;
  feedback_adjustment: number;
  total: number;
}

interface FitAssessmentData {
  eligible: boolean;
  ineligibility_reasons: string[];
  matched_signals: string[];
  missing_requirements: string[];
  risk_flags: string[];
  evidence: string[];
  explanation: string[];
  scores: FitScores;
  triage_decision: TriageDecision;
}

interface ActionPlanData {
  generated_by: string;
  summary: string;
  missing_requirements: string[];
  strongest_evidence: string[];
  resume_tailoring_steps: string[];
}

interface FeedbackEventData {
  label: FeedbackLabel;
  note: string | null;
  created_at: string;
  normalized_title: string | null;
  required_skills: string[];
  location_type: string | null;
}

interface OpportunityResult {
  opportunity: OpportunityData;
  assessment: FitAssessmentData;
  action_plan: ActionPlanData | null;
  feedback: FeedbackEventData[];
}

interface SearchRunDetailResponse {
  run: SearchRunRecord;
  profile: CandidateProfileRecord;
  target: SearchTargetRecord;
  results: OpportunityResult[];
}

interface ImportBatchRecord {
  id: string;
  label: string;
  format: ImportFormat;
  item_count: number;
  created_at: string;
}

interface WorkspaceSnapshotResponse {
  profile: CandidateProfileRecord | null;
  target: SearchTargetRecord | null;
  imports: ImportBatchRecord[];
  latest_run: SearchRunDetailResponse | null;
}

interface ProfileIngestResponse {
  generated_at: string;
  profile: CandidateProfileData;
  suggested_target: SearchTargetData;
  llm_status: LLMStatus;
}

interface SaveProfileResponse {
  saved_at: string;
  profile: CandidateProfileRecord;
  target: SearchTargetRecord;
}

interface ImportResponse {
  imported_at: string;
  batch: ImportBatchRecord;
}

interface AppState {
  workspaceLoading: boolean;
  busy:
    | "ingest"
    | "save-profile"
    | "search"
    | "import"
    | "reset-workspace"
    | "feedback"
    | "action-plan"
    | null;
  error: string | null;
  notice: string | null;
  draftProfile: CandidateProfileData | null;
  draftTarget: SearchTargetData | null;
  savedProfile: CandidateProfileRecord | null;
  savedTarget: SearchTargetRecord | null;
  llmStatus: LLMStatus | null;
  imports: ImportBatchRecord[];
  run: SearchRunDetailResponse | null;
  selectedOpportunityId: string | null;
  importFormat: ImportFormat;
  importContent: string;
}

const initialState: AppState = {
  workspaceLoading: true,
  busy: null,
  error: null,
  notice: null,
  draftProfile: null,
  draftTarget: null,
  savedProfile: null,
  savedTarget: null,
  llmStatus: null,
  imports: [],
  run: null,
  selectedOpportunityId: null,
  importFormat: "json",
  importContent: "",
};

const stepLabels: Array<{ step: WizardStep; title: string; eyebrow: string }> = [
  { step: 1, title: "Upload Resume", eyebrow: "Step 1" },
  { step: 2, title: "Confirm Details", eyebrow: "Step 2" },
  { step: 3, title: "Run Search", eyebrow: "Step 3" },
  { step: 4, title: "Review Jobs", eyebrow: "Step 4" },
];

const remotePreferenceOptions = [
  { value: "remote_only", label: "Remote only" },
  { value: "remote_or_hybrid", label: "Remote or hybrid" },
  { value: "hybrid_only", label: "Hybrid only" },
  { value: "onsite_ok", label: "Onsite is okay" },
];

const workModeOptions = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "Onsite" },
];

const seniorityOptions = [
  { value: "intern", label: "Intern" },
  { value: "entry-level", label: "Entry-level" },
  { value: "mid-level", label: "Mid-level" },
  { value: "senior", label: "Senior" },
];

const feedbackOptions: FeedbackLabel[] = [
  "apply",
  "tailor",
  "monitor",
  "skip",
  "wrong_stack",
  "wrong_location",
  "too_senior",
];

function listToText(items: string[]): string {
  return items.join("\n");
}

function textToList(value: string): string[] {
  return value
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toggleListValue(items: string[], value: string, checked: boolean): string[] {
  if (checked) {
    return items.includes(value) ? items : [...items, value];
  }
  return items.filter((item) => item !== value);
}

function formatVisaSupport(value: string | null | undefined): string {
  if (value === "available") return "Visa support available";
  if (value === "not available") return "No visa support";
  return "Visa support not specified";
}

function decisionTone(decision: TriageDecision): "good" | "warning" | "neutral" | "muted" {
  switch (decision) {
    case "apply":
      return "good";
    case "tailor":
      return "warning";
    case "monitor":
      return "neutral";
    default:
      return "muted";
  }
}

async function jsonFetch<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const text = await response.text();
  const payload = text ? (JSON.parse(text) as T | { detail?: string }) : (null as T);
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
    throw new Error(typeof detail === "string" ? detail : "Request failed.");
  }
  return payload as T;
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function previousStep(step: WizardStep): WizardStep {
  if (step === 4) return 3;
  if (step === 3) return 2;
  if (step === 2) return 1;
  return 1;
}

function nextStep(step: WizardStep): WizardStep {
  if (step === 1) return 2;
  if (step === 2) return 3;
  if (step === 3) return 4;
  return 4;
}

function App(): JSX.Element {
  const [state, setState] = useState<AppState>(initialState);
  const [currentStep, setCurrentStep] = useState<WizardStep>(1);

  useEffect(() => {
    void (async () => {
      try {
        const workspace = await jsonFetch<WorkspaceSnapshotResponse>("/api/workspace");
        let step: WizardStep = 1;
        if (workspace.latest_run) {
          step = 4;
        } else if (workspace.profile && workspace.target) {
          step = 3;
        } else if (workspace.profile || workspace.target) {
          step = 2;
        }
        setState((current) => ({
          ...current,
          workspaceLoading: false,
          savedProfile: workspace.profile ?? null,
          savedTarget: workspace.target ?? null,
          draftProfile: workspace.profile?.profile ?? null,
          draftTarget: workspace.target?.target ?? null,
          llmStatus: workspace.profile?.llm_status ?? null,
          imports: workspace.imports,
          run: workspace.latest_run ?? null,
          selectedOpportunityId: workspace.latest_run?.results[0]?.opportunity.id ?? null,
        }));
        setCurrentStep(step);
      } catch (error) {
        setState((current) => ({
          ...current,
          workspaceLoading: false,
          error: error instanceof Error ? error.message : "Could not load the workspace.",
        }));
      }
    })();
  }, []);

  const selectedResult = useMemo(() => {
    return (
      state.run?.results.find((item) => item.opportunity.id === state.selectedOpportunityId) ??
      state.run?.results[0] ??
      null
    );
  }, [state.run, state.selectedOpportunityId]);

  const maxUnlockedStep: WizardStep = useMemo(() => {
    if (state.run) return 4;
    if (state.savedProfile && state.savedTarget) return 3;
    if (state.draftProfile && state.draftTarget) return 2;
    return 1;
  }, [state.draftProfile, state.draftTarget, state.savedProfile, state.savedTarget, state.run]);

  function goToStep(step: WizardStep): void {
    if (step <= maxUnlockedStep) {
      setCurrentStep(step);
    }
  }

  function goNext(): void {
    const candidate = nextStep(currentStep);
    setCurrentStep(candidate <= maxUnlockedStep ? candidate : currentStep);
  }

  function goBack(): void {
    setCurrentStep(previousStep(currentStep));
  }

  async function handleResumeIngest(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    if (!formData.get("resume")) {
      setState((current) => ({ ...current, error: "Choose a resume file first.", notice: null }));
      return;
    }
    setState((current) => ({ ...current, busy: "ingest", error: null, notice: null }));
    try {
      const response = await fetch("/api/profile/ingest", {
        method: "POST",
        body: formData,
      });
      const payload = (await response.json()) as ProfileIngestResponse | { detail?: string };
      if (!response.ok) {
        throw new Error(
          typeof payload === "object" && payload && "detail" in payload
            ? payload.detail || "Could not ingest the resume."
            : "Could not ingest the resume.",
        );
      }
      const parsed = payload as ProfileIngestResponse;
      setState((current) => ({
        ...current,
        busy: null,
        draftProfile: parsed.profile,
        draftTarget: parsed.suggested_target,
        llmStatus: parsed.llm_status,
        error: null,
        notice: "Resume uploaded. Please confirm your details before saving.",
      }));
      setCurrentStep(2);
      form.reset();
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Could not ingest the resume.",
      }));
    }
  }

  async function handleSaveProfile(): Promise<void> {
    if (!state.draftProfile || !state.draftTarget) {
      setState((current) => ({ ...current, error: "Create or load a draft profile first." }));
      return;
    }
    setState((current) => ({ ...current, busy: "save-profile", error: null, notice: null }));
    try {
      const payload = await jsonFetch<SaveProfileResponse>("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile: state.draftProfile,
          target: state.draftTarget,
          llm_status: state.llmStatus,
        }),
      });
      setState((current) => ({
        ...current,
        busy: null,
        savedProfile: payload.profile,
        savedTarget: payload.target,
        notice: `Details saved. Profile v${payload.profile.version} and target v${payload.target.version} are ready for search.`,
        error: null,
      }));
      setCurrentStep(3);
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Could not save the profile.",
      }));
    }
  }

  async function handleSearch(): Promise<void> {
    setState((current) => ({ ...current, busy: "search", error: null, notice: null }));
    try {
      const payload = await jsonFetch<SearchRunDetailResponse>("/api/search-runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_action_plans: true }),
      });
      setState((current) => ({
        ...current,
        busy: null,
        run: payload,
        selectedOpportunityId: payload.results[0]?.opportunity.id ?? null,
        notice: `Completed search run ${payload.run.id.slice(0, 8)} with ${payload.results.length} ranked opportunities.`,
      }));
      setCurrentStep(4);
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Search run failed.",
      }));
    }
  }

  async function handleImport(): Promise<void> {
    if (!state.importContent.trim()) {
      setState((current) => ({ ...current, error: "Paste import content first." }));
      return;
    }
    setState((current) => ({ ...current, busy: "import", error: null, notice: null }));
    try {
      const payload = await jsonFetch<ImportResponse>("/api/imports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          format: state.importFormat,
          content: state.importContent,
        }),
      });
      setState((current) => ({
        ...current,
        busy: null,
        imports: [payload.batch, ...current.imports],
        importContent: "",
        notice: `Imported ${payload.batch.item_count} jobs into ${payload.batch.label}.`,
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Import failed.",
      }));
    }
  }

  async function handleResetWorkspace(): Promise<void> {
    setState((current) => ({ ...current, busy: "reset-workspace", error: null, notice: null }));
    try {
      const response = await fetch("/api/workspace", { method: "DELETE" });
      if (!response.ok) {
        throw new Error("Could not reset the workspace.");
      }
      setState({
        ...initialState,
        workspaceLoading: false,
        notice: "Workspace reset. Old saved profiles, targets, imports, and runs were cleared.",
      });
      setCurrentStep(1);
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Could not reset the workspace.",
      }));
    }
  }

  async function submitFeedback(label: FeedbackLabel): Promise<void> {
    if (!selectedResult || !state.run) return;
    setState((current) => ({ ...current, busy: "feedback", error: null, notice: null }));
    try {
      await jsonFetch("/api/opportunities/" + selectedResult.opportunity.id + "/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_id: state.run.run.id,
          label,
        }),
      });
      const refreshed = await jsonFetch<SearchRunDetailResponse>(
        "/api/search-runs/" + state.run.run.id,
      );
      setState((current) => ({
        ...current,
        busy: null,
        run: refreshed,
        notice: `Saved feedback: ${label.replace(/_/g, " ")}.`,
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Could not save feedback.",
      }));
    }
  }

  async function refreshActionPlan(): Promise<void> {
    if (!selectedResult || !state.run) return;
    setState((current) => ({ ...current, busy: "action-plan", error: null, notice: null }));
    try {
      await jsonFetch("/api/opportunities/" + selectedResult.opportunity.id + "/action-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_id: state.run.run.id,
          force_refresh: true,
        }),
      });
      const refreshed = await jsonFetch<SearchRunDetailResponse>(
        "/api/search-runs/" + state.run.run.id,
      );
      setState((current) => ({
        ...current,
        busy: null,
        run: refreshed,
        notice: "Action plan refreshed.",
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Could not refresh the action plan.",
      }));
    }
  }

  function updateDraftProfile<K extends keyof CandidateProfileData>(
    key: K,
    value: CandidateProfileData[K],
  ): void {
    setState((current) => ({
      ...current,
      draftProfile: current.draftProfile ? { ...current.draftProfile, [key]: value } : null,
    }));
  }

  function updateDraftTarget<K extends keyof SearchTargetData>(
    key: K,
    value: SearchTargetData[K],
  ): void {
    setState((current) => ({
      ...current,
      draftTarget: current.draftTarget ? { ...current.draftTarget, [key]: value } : null,
    }));
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Personal Job Wizard</p>
          <h1>Find jobs that actually fit your life.</h1>
          <p className="header-copy">
            The flow now starts with your resume, then moves into confirmation, search setup,
            and final review one screen at a time.
          </p>
        </div>
        <div className="header-meta">
          <span className="meta-pill">
            {state.savedProfile ? `Profile v${state.savedProfile.version}` : "No saved profile"}
          </span>
          <span className="meta-pill">
            {state.run ? `${state.run.results.length} ranked jobs` : "No search run yet"}
          </span>
          <button
            type="button"
            onClick={handleResetWorkspace}
            disabled={state.busy === "reset-workspace"}
          >
            {state.busy === "reset-workspace" ? "Resetting..." : "Reset workspace"}
          </button>
        </div>
      </header>

      {(state.error || state.notice) && (
        <div className={`banner ${state.error ? "banner-error" : "banner-success"}`}>
          {state.error || state.notice}
        </div>
      )}

      <nav className="wizard-steps" aria-label="Wizard steps">
        {stepLabels.map((item) => {
          const locked = item.step > maxUnlockedStep;
          const active = item.step === currentStep;
          return (
            <button
              key={item.step}
              type="button"
              className={`wizard-step ${active ? "wizard-step-active" : ""} ${
                locked ? "wizard-step-locked" : ""
              }`}
              disabled={locked}
              onClick={() => goToStep(item.step)}
            >
              <span className="wizard-step-index">{item.eyebrow}</span>
              <strong>{item.title}</strong>
            </button>
          );
        })}
      </nav>

      <main className="workspace wizard-layout">
        {currentStep === 1 && (
          <section className="panel wizard-panel hero-panel">
            <div className="panel-header panel-header-stack">
              <div>
                <p className="section-kicker">Step 1</p>
                <h2>Please upload your resume</h2>
                <p className="section-copy">
                  Start here. Once your resume is uploaded, the app will extract a draft profile
                  and move you straight into the confirmation step.
                </p>
              </div>
              {state.llmStatus && <span className="muted-text">LLM mode: {state.llmStatus.mode}</span>}
            </div>

            <form onSubmit={handleResumeIngest} className="stack wizard-upload-form">
              <label className="field">
                <span>Resume upload</span>
                <input name="resume" type="file" accept=".txt,.md,.doc,.docx,.rtf,.pdf" />
              </label>
              <div className="wizard-actions wizard-actions-end">
                <button type="submit" disabled={state.busy === "ingest"}>
                  {state.busy === "ingest" ? "Uploading..." : "Upload resume"}
                </button>
              </div>
            </form>

            {state.draftProfile && (
              <div className="wizard-grid wizard-grid-two">
                <article className="compact-card">
                  <p className="section-kicker">Draft ready</p>
                  <h3>{state.draftProfile.filename}</h3>
                  <p className="section-copy">
                    {state.draftProfile.summary || "A draft profile is ready for confirmation."}
                  </p>
                </article>
                <article className="compact-card">
                  <p className="section-kicker">Next screen</p>
                  <h3>Please confirm your details</h3>
                  <p className="section-copy">
                    Review the extracted roles, skills, locations, and search target before saving.
                  </p>
                  <div className="wizard-actions wizard-actions-end">
                    <button type="button" onClick={goNext} disabled={maxUnlockedStep < 2}>
                      Next
                    </button>
                  </div>
                </article>
              </div>
            )}
          </section>
        )}

        {currentStep === 2 && (
          <section className="panel wizard-panel">
            <div className="panel-header panel-header-stack">
              <div>
                <p className="section-kicker">Step 2</p>
                <h2>Please confirm your details</h2>
                <p className="section-copy">
                  Make sure the extracted profile is actually yours, then tighten the target so the
                  search matches your real preferences.
                </p>
              </div>
              {state.savedProfile && state.savedTarget && (
                <span className="muted-text">
                  Saved as profile v{state.savedProfile.version} and target v{state.savedTarget.version}
                </span>
              )}
            </div>

            {!state.draftProfile || !state.draftTarget ? (
              <div className="empty-block">
                Upload a resume first so the app has something real to confirm.
              </div>
            ) : (
              <>
                <div className="wizard-grid wizard-grid-two">
                  <section className="stack">
                    <div className="compact-card">
                      <p className="section-kicker">Profile</p>
                      <h3>Who you are</h3>
                    </div>

                    <label className="field">
                      <span>Summary</span>
                      <textarea
                        rows={4}
                        value={state.draftProfile.summary ?? ""}
                        onChange={(event) => updateDraftProfile("summary", event.target.value)}
                      />
                    </label>

                    <div className="field-grid">
                      <label className="field">
                        <span>Target roles</span>
                        <textarea
                          rows={5}
                          value={listToText(state.draftProfile.core_roles)}
                          onChange={(event) =>
                            updateDraftProfile("core_roles", textToList(event.target.value))
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Confirmed skills</span>
                        <textarea
                          rows={5}
                          value={listToText(state.draftProfile.skills_confirmed)}
                          onChange={(event) =>
                            updateDraftProfile("skills_confirmed", textToList(event.target.value))
                          }
                        />
                      </label>
                    </div>

                    <div className="field-grid">
                      <label className="field">
                        <span>Preferred locations</span>
                        <textarea
                          rows={4}
                          value={listToText(state.draftProfile.preferred_locations)}
                          onChange={(event) =>
                            updateDraftProfile(
                              "preferred_locations",
                              textToList(event.target.value),
                            )
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Employment preferences</span>
                        <textarea
                          rows={4}
                          value={listToText(state.draftProfile.employment_preferences)}
                          onChange={(event) =>
                            updateDraftProfile(
                              "employment_preferences",
                              textToList(event.target.value),
                            )
                          }
                        />
                      </label>
                    </div>

                    <div className="field-grid">
                      <label className="field">
                        <span>Remote preference</span>
                        <select
                          value={state.draftProfile.remote_preference}
                          onChange={(event) =>
                            updateDraftProfile("remote_preference", event.target.value)
                          }
                        >
                          {remotePreferenceOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="compact-card">
                        <p className="section-kicker">Resume snapshot</p>
                        <h3>{state.draftProfile.filename}</h3>
                        <p className="section-copy">
                          {state.draftProfile.years_experience !== null
                            ? `${state.draftProfile.years_experience.toFixed(1)} years detected`
                            : "No years of experience detected"}
                        </p>
                        {state.llmStatus && (
                          <p className="muted-text">
                            {state.llmStatus.provider
                              ? `${state.llmStatus.mode} via ${state.llmStatus.provider}`
                              : state.llmStatus.mode}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="stack">
                      <div className="compact-card">
                        <p className="section-kicker">Evidence</p>
                        <h3>Why the parser chose these details</h3>
                      </div>
                      <div className="evidence-list">
                        {state.draftProfile.evidence.length ? (
                          state.draftProfile.evidence.slice(0, 6).map((item) => (
                            <article className="evidence-item" key={item.label + item.detail}>
                              <strong>{item.label}</strong>
                              <p>{item.detail}</p>
                            </article>
                          ))
                        ) : (
                          <div className="empty-block">No evidence snippets were generated.</div>
                        )}
                      </div>
                    </div>
                  </section>

                  <section className="stack">
                    <div className="compact-card">
                      <p className="section-kicker">Target</p>
                      <h3>What you want</h3>
                    </div>

                    <label className="field">
                      <span>Target roles</span>
                      <textarea
                        rows={4}
                        value={listToText(state.draftTarget.target_roles)}
                        onChange={(event) =>
                          updateDraftTarget("target_roles", textToList(event.target.value))
                        }
                      />
                    </label>

                    <div className="field-grid">
                      <label className="field">
                        <span>Role families</span>
                        <textarea
                          rows={4}
                          value={listToText(state.draftTarget.role_families)}
                          onChange={(event) =>
                            updateDraftTarget("role_families", textToList(event.target.value))
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Query terms</span>
                        <textarea
                          rows={4}
                          value={listToText(state.draftTarget.query_terms)}
                          onChange={(event) =>
                            updateDraftTarget("query_terms", textToList(event.target.value))
                          }
                        />
                      </label>
                    </div>

                    <div className="field-grid">
                      <label className="field">
                        <span>Preferred locations</span>
                        <textarea
                          rows={4}
                          value={listToText(state.draftTarget.preferred_locations)}
                          onChange={(event) =>
                            updateDraftTarget(
                              "preferred_locations",
                              textToList(event.target.value),
                            )
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Employment preferences</span>
                        <textarea
                          rows={4}
                          value={listToText(state.draftTarget.employment_preferences)}
                          onChange={(event) =>
                            updateDraftTarget(
                              "employment_preferences",
                              textToList(event.target.value),
                            )
                          }
                        />
                      </label>
                    </div>

                    <label className="field">
                      <span>Work modes</span>
                      <div className="check-grid">
                        {workModeOptions.map((option) => (
                          <label key={option.value}>
                            <input
                              type="checkbox"
                              checked={state.draftTarget!.work_modes.includes(option.value)}
                              onChange={(event) =>
                                updateDraftTarget(
                                  "work_modes",
                                  toggleListValue(
                                    state.draftTarget!.work_modes,
                                    option.value,
                                    event.target.checked,
                                  ),
                                )
                              }
                            />
                            {option.label}
                          </label>
                        ))}
                      </div>
                    </label>

                    <div className="field-grid">
                      <label className="field">
                        <span>Must-have skills</span>
                        <textarea
                          rows={4}
                          value={listToText(state.draftTarget.must_have_skills)}
                          onChange={(event) =>
                            updateDraftTarget("must_have_skills", textToList(event.target.value))
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Excluded keywords</span>
                        <textarea
                          rows={4}
                          value={listToText(state.draftTarget.excluded_keywords)}
                          onChange={(event) =>
                            updateDraftTarget("excluded_keywords", textToList(event.target.value))
                          }
                        />
                      </label>
                    </div>

                    <label className="field">
                      <span>Seniority ceiling</span>
                      <select
                        value={state.draftTarget.seniority_ceiling}
                        onChange={(event) =>
                          updateDraftTarget("seniority_ceiling", event.target.value)
                        }
                      >
                        {seniorityOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </section>
                </div>

                <div className="wizard-actions">
                  <button type="button" onClick={goBack}>
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={handleSaveProfile}
                    disabled={state.busy === "save-profile"}
                  >
                    {state.busy === "save-profile" ? "Saving..." : "Save profile + target"}
                  </button>
                  <button type="button" onClick={goNext} disabled={maxUnlockedStep < 3}>
                    Next
                  </button>
                </div>
              </>
            )}
          </section>
        )}

        {currentStep === 3 && (
          <section className="panel wizard-panel">
            <div className="panel-header panel-header-stack">
              <div>
                <p className="section-kicker">Step 3</p>
                <h2>Run your search</h2>
                <p className="section-copy">
                  Choose how strict the filtering should be, decide which sources to include, add
                  any imported jobs, and then run the search.
                </p>
              </div>
              {state.savedProfile && state.savedTarget && (
                <span className="muted-text">
                  Ready with profile v{state.savedProfile.version} and target v{state.savedTarget.version}
                </span>
              )}
            </div>

            {!state.savedProfile || !state.savedTarget || !state.draftTarget ? (
              <div className="empty-block">
                Save your confirmed profile and target first to unlock the search step.
              </div>
            ) : (
              <>
                <div className="wizard-grid wizard-grid-two">
                  <section className="stack">
                    <div className="compact-card">
                      <p className="section-kicker">Search rules</p>
                      <h3>How strict should matching be?</h3>
                    </div>

                    <div className="check-grid">
                      <label>
                        <input
                          type="checkbox"
                          checked={state.draftTarget.strict_location}
                          onChange={(event) =>
                            updateDraftTarget("strict_location", event.target.checked)
                          }
                        />
                        Strict location
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={state.draftTarget.strict_work_mode}
                          onChange={(event) =>
                            updateDraftTarget("strict_work_mode", event.target.checked)
                          }
                        />
                        Strict work mode
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={state.draftTarget.strict_employment}
                          onChange={(event) =>
                            updateDraftTarget("strict_employment", event.target.checked)
                          }
                        />
                        Strict employment
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={state.draftTarget.strict_must_have}
                          onChange={(event) =>
                            updateDraftTarget("strict_must_have", event.target.checked)
                          }
                        />
                        Strict must-haves
                      </label>
                    </div>

                    <div className="compact-card">
                      <p className="section-kicker">Sources</p>
                      <h3>Where jobs should come from</h3>
                    </div>

                    <div className="check-grid">
                      <label>
                        <input
                          type="checkbox"
                          checked={state.draftTarget!.providers.remotive}
                          onChange={(event) =>
                            updateDraftTarget("providers", {
                              ...state.draftTarget!.providers,
                              remotive: event.target.checked,
                            })
                          }
                        />
                        Remotive
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={state.draftTarget!.providers.remoteok}
                          onChange={(event) =>
                            updateDraftTarget("providers", {
                              ...state.draftTarget!.providers,
                              remoteok: event.target.checked,
                            })
                          }
                        />
                        RemoteOK
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={state.draftTarget!.providers.imports}
                          onChange={(event) =>
                            updateDraftTarget("providers", {
                              ...state.draftTarget!.providers,
                              imports: event.target.checked,
                            })
                          }
                        />
                        Imports
                      </label>
                    </div>

                    <div className="compact-card">
                      <p className="section-kicker">Search target</p>
                      <h3>Current focus</h3>
                      <p className="section-copy">
                        {state.draftTarget.target_roles.join(", ") || "No target roles set yet."}
                      </p>
                    </div>
                  </section>

                  <section className="stack">
                    <div className="compact-card">
                      <p className="section-kicker">Optional imports</p>
                      <h3>Add jobs from other places</h3>
                      <p className="section-copy">
                        Paste listings from boards you trust if you want them ranked with the live feeds.
                      </p>
                    </div>

                    <label className="field">
                      <span>Import format</span>
                      <select
                        value={state.importFormat}
                        onChange={(event) =>
                          setState((current) => ({
                            ...current,
                            importFormat: event.target.value as ImportFormat,
                          }))
                        }
                      >
                        <option value="json">JSON</option>
                        <option value="csv">CSV</option>
                        <option value="urls">URL list</option>
                      </select>
                    </label>

                    <label className="field">
                      <span>Import content</span>
                      <textarea
                        rows={10}
                        value={state.importContent}
                        onChange={(event) =>
                          setState((current) => ({ ...current, importContent: event.target.value }))
                        }
                      />
                    </label>

                    <div className="wizard-actions wizard-actions-end">
                      <button type="button" onClick={handleImport} disabled={state.busy === "import"}>
                        {state.busy === "import" ? "Importing..." : "Save import"}
                      </button>
                    </div>

                    <div className="import-list">
                      {state.imports.length ? (
                        state.imports.map((item) => (
                          <div className="import-row" key={item.id}>
                            <strong>{item.label}</strong>
                            <span>
                              {item.item_count} items | {item.format.toUpperCase()} |{" "}
                              {formatTimestamp(item.created_at)}
                            </span>
                          </div>
                        ))
                      ) : (
                        <div className="empty-block">No saved imports yet.</div>
                      )}
                    </div>
                  </section>
                </div>

                <div className="wizard-actions">
                  <button type="button" onClick={goBack}>
                    Back
                  </button>
                  <button type="button" onClick={handleSearch} disabled={state.busy === "search"}>
                    {state.busy === "search" ? "Running..." : "Run search"}
                  </button>
                  <button type="button" onClick={goNext} disabled={maxUnlockedStep < 4}>
                    Next
                  </button>
                </div>
              </>
            )}
          </section>
        )}

        {currentStep === 4 && (
          <section className="panel wizard-panel">
            <div className="panel-header panel-header-stack">
              <div>
                <p className="section-kicker">Step 4</p>
                <h2>Review your ranked jobs</h2>
                <p className="section-copy">
                  Compare the top matches, inspect the fit and risks, and decide if a listing is
                  actually worth your time.
                </p>
              </div>
              <button
                type="button"
                onClick={refreshActionPlan}
                disabled={!selectedResult || state.busy === "action-plan"}
              >
                {state.busy === "action-plan" ? "Refreshing..." : "Refresh action plan"}
              </button>
            </div>

            {!state.run?.results.length ? (
              <div className="empty-block">
                Run a search first so there is a ranked list to review here.
              </div>
            ) : (
              <>
                <div className="wizard-grid wizard-grid-results">
                  <section className="stack">
                    <div className="compact-card">
                      <p className="section-kicker">Results</p>
                      <h3>{state.run.results.length} jobs ranked for you</h3>
                      <p className="section-copy">
                        Search run {state.run.run.id.slice(0, 8)} created {formatTimestamp(state.run.run.created_at)}
                      </p>
                    </div>

                    <div className="result-list">
                      {state.run.results.map((item) => (
                        <button
                          key={item.opportunity.id}
                          type="button"
                          className={`result-row ${
                            state.selectedOpportunityId === item.opportunity.id
                              ? "result-row-active"
                              : ""
                          }`}
                          onClick={() =>
                            setState((current) => ({
                              ...current,
                              selectedOpportunityId: item.opportunity.id,
                            }))
                          }
                        >
                          <div className="result-row-top">
                            <strong>{item.opportunity.title}</strong>
                            <span
                              className={`decision decision-${decisionTone(
                                item.assessment.triage_decision,
                              )}`}
                            >
                              {item.assessment.triage_decision}
                            </span>
                          </div>
                          <div className="result-row-meta">
                            <span>{item.opportunity.company}</span>
                            <span>{item.opportunity.location}</span>
                            <span>{item.assessment.scores.total}/100</span>
                          </div>
                          <p>{item.assessment.explanation[0] || "No explanation generated yet."}</p>
                        </button>
                      ))}
                    </div>
                  </section>

                  <section className="stack">
                    {selectedResult ? (
                      <>
                        <div className="detail-head">
                          <div>
                            <h3>{selectedResult.opportunity.title}</h3>
                            <p>
                              {selectedResult.opportunity.company} | {selectedResult.opportunity.location} |{" "}
                              {selectedResult.opportunity.source}
                            </p>
                          </div>
                          <div className="score-box">{selectedResult.assessment.scores.total}</div>
                        </div>

                        <div className="metric-grid">
                          <div>
                            <span>Role</span>
                            <strong>{selectedResult.assessment.scores.role_alignment}/30</strong>
                          </div>
                          <div>
                            <span>Skills</span>
                            <strong>{selectedResult.assessment.scores.skills_alignment}/25</strong>
                          </div>
                          <div>
                            <span>Seniority</span>
                            <strong>{selectedResult.assessment.scores.seniority_alignment}/15</strong>
                          </div>
                          <div>
                            <span>Location</span>
                            <strong>{selectedResult.assessment.scores.location_alignment}/10</strong>
                          </div>
                        </div>

                        <section className="detail-section">
                          <h4>Life fit</h4>
                          <div className="chip-row">
                            <span className="chip">{selectedResult.opportunity.location_type}</span>
                            <span className="chip">{selectedResult.opportunity.seniority_band}</span>
                            <span className="chip">
                              {selectedResult.opportunity.employment_type || "Employment not specified"}
                            </span>
                            <span className="chip">
                              {selectedResult.opportunity.salary_range || "Salary not listed"}
                            </span>
                            <span className="chip">
                              {formatVisaSupport(selectedResult.opportunity.visa_support)}
                            </span>
                          </div>
                        </section>

                        <section className="detail-section">
                          <h4>Assessment</h4>
                          <ul>
                            {(selectedResult.assessment.eligible
                              ? [
                                  ...selectedResult.assessment.matched_signals,
                                  ...selectedResult.assessment.explanation,
                                ]
                              : selectedResult.assessment.ineligibility_reasons
                            ).map((line) => (
                              <li key={line}>{line}</li>
                            ))}
                          </ul>
                        </section>

                        <section className="detail-section">
                          <h4>Gaps and risks</h4>
                          <div className="chip-row">
                            {selectedResult.assessment.missing_requirements.length ? (
                              selectedResult.assessment.missing_requirements.map((item) => (
                                <span className="chip chip-warning" key={item}>
                                  {item}
                                </span>
                              ))
                            ) : (
                              <span className="chip">No major gaps surfaced</span>
                            )}
                          </div>
                          <ul>
                            {selectedResult.assessment.risk_flags.length ? (
                              selectedResult.assessment.risk_flags.map((line) => (
                                <li key={line}>{line}</li>
                              ))
                            ) : (
                              <li>No significant risks were called out.</li>
                            )}
                          </ul>
                        </section>

                        <section className="detail-section">
                          <h4>Action plan</h4>
                          {selectedResult.action_plan ? (
                            <>
                              <p>{selectedResult.action_plan.summary}</p>
                              <ul>
                                {selectedResult.action_plan.resume_tailoring_steps.map((line) => (
                                  <li key={line}>{line}</li>
                                ))}
                              </ul>
                            </>
                          ) : (
                            <div className="empty-block">
                              No action plan yet. Apply or tailor candidates get one automatically.
                            </div>
                          )}
                        </section>

                        <div className="feedback-bar">
                          {feedbackOptions.map((label) => (
                            <button
                              key={label}
                              type="button"
                              className="feedback-button"
                              onClick={() => void submitFeedback(label)}
                              disabled={state.busy === "feedback"}
                            >
                              {label.replace(/_/g, " ")}
                            </button>
                          ))}
                        </div>

                        {selectedResult.opportunity.apply_url && (
                          <a
                            className="apply-link"
                            href={selectedResult.opportunity.apply_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open listing
                          </a>
                        )}
                      </>
                    ) : (
                      <div className="empty-block">
                        Select a ranked opportunity to inspect the fit and action plan.
                      </div>
                    )}
                  </section>
                </div>

                <details className="panel details-panel">
                  <summary>Developer details</summary>
                  <div className="stack">
                    <div className="meta-table">
                      <div>
                        <span>Fetched</span>
                        <strong>{state.run.run.diagnostics.fetched_listings}</strong>
                      </div>
                      <div>
                        <span>Normalized</span>
                        <strong>{state.run.run.diagnostics.normalized_opportunities}</strong>
                      </div>
                      <div>
                        <span>Deduped</span>
                        <strong>{state.run.run.diagnostics.deduped_opportunities}</strong>
                      </div>
                      <div>
                        <span>Eligible</span>
                        <strong>{state.run.run.diagnostics.eligible_opportunities}</strong>
                      </div>
                    </div>

                    <div className="chip-row">
                      {state.run.run.diagnostics.query_plan.map((item) => (
                        <span className="chip" key={item}>
                          {item}
                        </span>
                      ))}
                    </div>

                    <ul>
                      {state.run.run.provider_statuses.map((item) => (
                        <li key={item.provider}>
                          {item.provider}: {item.status} | fetched {item.fetched_count} | normalized{" "}
                          {item.normalized_count}
                        </li>
                      ))}
                    </ul>
                  </div>
                </details>

                <div className="wizard-actions">
                  <button type="button" onClick={goBack}>
                    Back
                  </button>
                </div>
              </>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

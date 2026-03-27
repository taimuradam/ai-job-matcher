import React, { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type LLMStatus = {
  mode: string;
  provider?: string | null;
  detail?: string | null;
};

type EvidenceItem = {
  label: string;
  detail: string;
  confidence: number;
};

type ProjectSignal = {
  title: string;
  summary: string;
  related_skills: string[];
  confidence: number;
};

type CandidateProfileData = {
  filename: string;
  summary?: string | null;
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
  years_experience?: number | null;
  projects: ProjectSignal[];
  evidence: EvidenceItem[];
  confidence: Record<string, number>;
  signals: string[];
  llm_summary?: string | null;
};

type SourceSelection = {
  remotive: boolean;
  remoteok: boolean;
  imports: boolean;
};

type SearchTargetData = {
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
};

type CandidateProfileRecord = {
  id: string;
  version: number;
  created_at: string;
  profile: CandidateProfileData;
  llm_status: LLMStatus;
};

type SearchTargetRecord = {
  id: string;
  profile_id: string;
  profile_version: number;
  version: number;
  created_at: string;
  target: SearchTargetData;
};

type ProviderFetchStatus = {
  provider: string;
  source_type: string;
  status: string;
  fetched_count: number;
  normalized_count: number;
  query_terms: string[];
  error?: string | null;
};

type SearchRunDiagnostics = {
  fetched_listings: number;
  normalized_opportunities: number;
  deduped_opportunities: number;
  eligible_opportunities: number;
  actionable_opportunities: number;
  provider_failures: number;
  excluded_counts: Record<string, number>;
  active_filters: string[];
  query_plan: string[];
};

type SearchRunRecord = {
  id: string;
  profile_id: string;
  profile_version: number;
  target_id: string;
  target_version: number;
  created_at: string;
  diagnostics: SearchRunDiagnostics;
  provider_statuses: ProviderFetchStatus[];
};

type OpportunityData = {
  id: string;
  title: string;
  company: string;
  location: string;
  location_type: string;
  seniority_band: string;
  description_text: string;
  required_skills: string[];
  preferred_skills: string[];
  domain_tags: string[];
  salary_range?: string | null;
  visa_support?: string | null;
  employment_type?: string | null;
  published_at?: string | null;
  job_age_days?: number | null;
  apply_url?: string | null;
  source: string;
};

type FitScores = {
  role_alignment: number;
  skills_alignment: number;
  seniority_alignment: number;
  location_alignment: number;
  evidence_strength: number;
  freshness: number;
  source_quality: number;
  feedback_adjustment: number;
  total: number;
};

type FitAssessmentData = {
  eligible: boolean;
  ineligibility_reasons: string[];
  matched_signals: string[];
  missing_requirements: string[];
  risk_flags: string[];
  evidence: string[];
  explanation: string[];
  scores: FitScores;
  triage_decision: "apply" | "tailor" | "monitor" | "skip";
};

type ActionPlanData = {
  generated_by: string;
  summary: string;
  missing_requirements: string[];
  strongest_evidence: string[];
  resume_tailoring_steps: string[];
};

type FeedbackEventData = {
  label: string;
  note?: string | null;
  created_at: string;
};

type OpportunityResult = {
  opportunity: OpportunityData;
  assessment: FitAssessmentData;
  action_plan?: ActionPlanData | null;
  feedback: FeedbackEventData[];
};

type SearchRunDetailResponse = {
  run: SearchRunRecord;
  profile: CandidateProfileRecord;
  target: SearchTargetRecord;
  results: OpportunityResult[];
};

type ImportBatchRecord = {
  id: string;
  label: string;
  format: "json" | "csv" | "urls";
  item_count: number;
  created_at: string;
};

type WorkspaceSnapshotResponse = {
  profile?: CandidateProfileRecord | null;
  target?: SearchTargetRecord | null;
  imports: ImportBatchRecord[];
  latest_run?: SearchRunDetailResponse | null;
};

type ProfileIngestResponse = {
  generated_at: string;
  profile: CandidateProfileData;
  suggested_target: SearchTargetData;
  llm_status: LLMStatus;
};

type SaveProfileResponse = {
  saved_at: string;
  profile: CandidateProfileRecord;
  target: SearchTargetRecord;
};

type AppState = {
  workspaceLoading: boolean;
  busy: string | null;
  error: string | null;
  notice: string | null;
  draftProfile: CandidateProfileData | null;
  draftTarget: SearchTargetData | null;
  llmStatus: LLMStatus | null;
  savedProfile: CandidateProfileRecord | null;
  savedTarget: SearchTargetRecord | null;
  imports: ImportBatchRecord[];
  run: SearchRunDetailResponse | null;
  selectedOpportunityId: string | null;
  importFormat: "json" | "csv" | "urls";
  importContent: string;
};

const initialState: AppState = {
  workspaceLoading: true,
  busy: null,
  error: null,
  notice: null,
  draftProfile: null,
  draftTarget: null,
  llmStatus: null,
  savedProfile: null,
  savedTarget: null,
  imports: [],
  run: null,
  selectedOpportunityId: null,
  importFormat: "json",
  importContent: ""
};

const remotePreferenceOptions = [
  { value: "remote_or_hybrid", label: "Remote or hybrid" },
  { value: "hybrid_or_remote", label: "Hybrid or remote" },
  { value: "onsite_friendly", label: "Onsite friendly" }
];

const workModeOptions = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "Onsite" }
];

const seniorityOptions = [
  { value: "entry-level", label: "Entry-level" },
  { value: "mid-level", label: "Mid-level" },
  { value: "senior", label: "Senior" }
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

function formatVisaSupport(value?: string | null): string {
  if (value === "available") return "Visa support available";
  if (value === "not available") return "No visa support";
  return "Visa support not specified";
}

function decisionTone(decision: FitAssessmentData["triage_decision"]): string {
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

async function jsonFetch<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const payload = (await response.json()) as T & { detail?: string };
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed.");
  }
  return payload;
}

function App() {
  const [state, setState] = useState<AppState>(initialState);

  useEffect(() => {
    void (async () => {
      try {
        const workspace = await jsonFetch<WorkspaceSnapshotResponse>("/api/workspace");
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
          selectedOpportunityId: workspace.latest_run?.results[0]?.opportunity.id ?? null
        }));
      } catch (error) {
        setState((current) => ({
          ...current,
          workspaceLoading: false,
          error: error instanceof Error ? error.message : "Could not load the workspace."
        }));
      }
    })();
  }, []);

  const selectedResult =
    state.run?.results.find((item) => item.opportunity.id === state.selectedOpportunityId) ??
    state.run?.results[0] ??
    null;

  async function handleResumeIngest(event: FormEvent<HTMLFormElement>) {
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
        body: formData
      });
      const payload = (await response.json()) as ProfileIngestResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(payload.detail || "Could not ingest the resume.");
      }
      setState((current) => ({
        ...current,
        busy: null,
        draftProfile: payload.profile,
        draftTarget: payload.suggested_target,
        llmStatus: payload.llm_status,
        notice: "Draft profile ingested. Review it, save it, then run search.",
        error: null
      }));
      form.reset();
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Could not ingest the resume."
      }));
    }
  }

  async function handleSaveProfile() {
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
          llm_status: state.llmStatus
        })
      });
      setState((current) => ({
        ...current,
        busy: null,
        savedProfile: payload.profile,
        savedTarget: payload.target,
        notice: `Saved profile v${payload.profile.version} and target v${payload.target.version}.`,
        error: null
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Could not save the profile."
      }));
    }
  }

  async function handleSearch() {
    setState((current) => ({ ...current, busy: "search", error: null, notice: null }));
    try {
      const payload = await jsonFetch<SearchRunDetailResponse>("/api/search-runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_action_plans: true })
      });
      setState((current) => ({
        ...current,
        busy: null,
        run: payload,
        selectedOpportunityId: payload.results[0]?.opportunity.id ?? null,
        notice: `Completed search run ${payload.run.id.slice(0, 8)} with ${payload.results.length} ranked opportunities.`
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Search run failed."
      }));
    }
  }

  async function handleImport() {
    if (!state.importContent.trim()) {
      setState((current) => ({ ...current, error: "Paste import content first." }));
      return;
    }
    setState((current) => ({ ...current, busy: "import", error: null, notice: null }));
    try {
      const payload = await jsonFetch<{ imported_at: string; batch: ImportBatchRecord }>("/api/imports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          format: state.importFormat,
          content: state.importContent
        })
      });
      setState((current) => ({
        ...current,
        busy: null,
        imports: [payload.batch, ...current.imports],
        importContent: "",
        notice: `Imported ${payload.batch.item_count} jobs into ${payload.batch.label}.`
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Import failed."
      }));
    }
  }

  async function handleResetWorkspace() {
    setState((current) => ({ ...current, busy: "reset-workspace", error: null, notice: null }));
    try {
      const response = await fetch("/api/workspace", { method: "DELETE" });
      if (!response.ok) {
        throw new Error("Could not reset the workspace.");
      }
      setState((current) => ({
        ...initialState,
        workspaceLoading: false,
        notice: "Workspace reset. Old saved profiles, targets, imports, and runs were cleared."
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Could not reset the workspace."
      }));
    }
  }

  async function submitFeedback(label: string) {
    if (!selectedResult || !state.run) return;
    setState((current) => ({ ...current, busy: "feedback", error: null, notice: null }));
    try {
      await jsonFetch("/api/opportunities/" + selectedResult.opportunity.id + "/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_id: state.run.run.id,
          label
        })
      });
      const refreshed = await jsonFetch<SearchRunDetailResponse>("/api/search-runs/" + state.run.run.id);
      setState((current) => ({
        ...current,
        busy: null,
        run: refreshed,
        notice: `Saved feedback: ${label.replace(/_/g, " ")}.`
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Could not save feedback."
      }));
    }
  }

  async function refreshActionPlan() {
    if (!selectedResult || !state.run) return;
    setState((current) => ({ ...current, busy: "action-plan", error: null, notice: null }));
    try {
      await jsonFetch("/api/opportunities/" + selectedResult.opportunity.id + "/action-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_id: state.run.run.id,
          force_refresh: true
        })
      });
      const refreshed = await jsonFetch<SearchRunDetailResponse>("/api/search-runs/" + state.run.run.id);
      setState((current) => ({
        ...current,
        busy: null,
        run: refreshed,
        notice: "Action plan refreshed."
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        busy: null,
        error: error instanceof Error ? error.message : "Could not refresh the action plan."
      }));
    }
  }

  function updateDraftProfile<K extends keyof CandidateProfileData>(key: K, value: CandidateProfileData[K]) {
    setState((current) => ({
      ...current,
      draftProfile: current.draftProfile ? { ...current.draftProfile, [key]: value } : current.draftProfile
    }));
  }

  function updateDraftTarget<K extends keyof SearchTargetData>(key: K, value: SearchTargetData[K]) {
    setState((current) => ({
      ...current,
      draftTarget: current.draftTarget ? { ...current.draftTarget, [key]: value } : current.draftTarget
    }));
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>Job Search Copilot</h1>
          <p>
            Ingest a resume, lock the target, run search across live and imported listings, then
            decide what deserves an application.
          </p>
        </div>
        <div className="header-meta">
          <span className="meta-pill">{state.savedProfile ? `Profile v${state.savedProfile.version}` : "No saved profile"}</span>
          <span className="meta-pill">{state.run ? `${state.run.results.length} ranked jobs` : "No run yet"}</span>
          <button type="button" onClick={handleResetWorkspace} disabled={state.busy === "reset-workspace"}>
            {state.busy === "reset-workspace" ? "Resetting..." : "Reset workspace"}
          </button>
        </div>
      </header>

      {(state.error || state.notice) && (
        <div className={`banner ${state.error ? "banner-error" : "banner-success"}`}>
          {state.error || state.notice}
        </div>
      )}

      <main className="workspace">
        <section className="column column-left">
          <section className="panel">
            <div className="panel-header">
              <h2>Profile</h2>
              {state.llmStatus && <span className="muted-text">LLM: {state.llmStatus.mode}</span>}
            </div>
            <form onSubmit={handleResumeIngest} className="stack">
              <label className="field">
                <span>Resume upload</span>
                <input name="resume" type="file" accept=".txt,.md,.doc,.docx,.rtf,.pdf" />
              </label>
              <button type="submit" disabled={state.busy === "ingest"}>
                {state.busy === "ingest" ? "Ingesting..." : "Ingest resume"}
              </button>
            </form>

            {state.draftProfile ? (
              <div className="stack">
                <label className="field">
                  <span>Summary</span>
                  <textarea
                    rows={3}
                    value={state.draftProfile.summary || ""}
                    onChange={(event) => updateDraftProfile("summary", event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Target roles</span>
                  <textarea
                    rows={3}
                    value={listToText(state.draftProfile.core_roles)}
                    onChange={(event) => updateDraftProfile("core_roles", textToList(event.target.value))}
                  />
                </label>
                <label className="field">
                  <span>Confirmed skills</span>
                  <textarea
                    rows={4}
                    value={listToText(state.draftProfile.skills_confirmed)}
                    onChange={(event) => updateDraftProfile("skills_confirmed", textToList(event.target.value))}
                  />
                </label>
                <label className="field">
                  <span>Preferred locations</span>
                  <textarea
                    rows={3}
                    value={listToText(state.draftProfile.preferred_locations)}
                    onChange={(event) => updateDraftProfile("preferred_locations", textToList(event.target.value))}
                  />
                </label>
                <div className="field-grid">
                  <label className="field">
                    <span>Remote preference</span>
                    <select
                      value={state.draftProfile.remote_preference}
                      onChange={(event) => updateDraftProfile("remote_preference", event.target.value)}
                    >
                      {remotePreferenceOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Employment preferences</span>
                    <textarea
                      rows={3}
                      value={listToText(state.draftProfile.employment_preferences)}
                      onChange={(event) => updateDraftProfile("employment_preferences", textToList(event.target.value))}
                    />
                  </label>
                </div>
                <div className="evidence-list">
                  {(state.draftProfile.evidence || []).slice(0, 4).map((item) => (
                    <article key={item.label + item.detail} className="evidence-item">
                      <strong>{item.label}</strong>
                      <p>{item.detail}</p>
                    </article>
                  ))}
                </div>
              </div>
            ) : (
              <div className="empty-block">No profile draft yet. Upload a resume to start.</div>
            )}
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>Targets</h2>
              <button type="button" onClick={handleSaveProfile} disabled={!state.draftProfile || !state.draftTarget || state.busy === "save-profile"}>
                {state.busy === "save-profile" ? "Saving..." : "Save profile + target"}
              </button>
            </div>
            {state.draftTarget ? (
              <div className="stack">
                <label className="field">
                  <span>Target roles</span>
                  <textarea
                    rows={3}
                    value={listToText(state.draftTarget.target_roles)}
                    onChange={(event) => updateDraftTarget("target_roles", textToList(event.target.value))}
                  />
                </label>
                <label className="field">
                  <span>Role families</span>
                  <textarea
                    rows={3}
                    value={listToText(state.draftTarget.role_families)}
                    onChange={(event) => updateDraftTarget("role_families", textToList(event.target.value))}
                  />
                </label>
                <label className="field">
                  <span>Query terms</span>
                  <textarea
                    rows={4}
                    value={listToText(state.draftTarget.query_terms)}
                    onChange={(event) => updateDraftTarget("query_terms", textToList(event.target.value))}
                  />
                </label>
                <div className="field-grid">
                  <label className="field">
                    <span>Preferred locations</span>
                    <textarea
                      rows={3}
                      value={listToText(state.draftTarget.preferred_locations)}
                      onChange={(event) => updateDraftTarget("preferred_locations", textToList(event.target.value))}
                    />
                  </label>
                  <label className="field">
                    <span>Employment preferences</span>
                    <textarea
                      rows={3}
                      value={listToText(state.draftTarget.employment_preferences)}
                      onChange={(event) => updateDraftTarget("employment_preferences", textToList(event.target.value))}
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
                              toggleListValue(state.draftTarget!.work_modes, option.value, event.target.checked)
                            )
                          }
                        />
                        {" "}
                        {option.label}
                      </label>
                    ))}
                  </div>
                </label>
                <div className="field-grid">
                  <label className="field">
                    <span>Must-have skills</span>
                    <textarea
                      rows={3}
                      value={listToText(state.draftTarget.must_have_skills)}
                      onChange={(event) => updateDraftTarget("must_have_skills", textToList(event.target.value))}
                    />
                  </label>
                  <label className="field">
                    <span>Excluded keywords</span>
                    <textarea
                      rows={3}
                      value={listToText(state.draftTarget.excluded_keywords)}
                      onChange={(event) => updateDraftTarget("excluded_keywords", textToList(event.target.value))}
                    />
                  </label>
                </div>
                <label className="field">
                  <span>Seniority ceiling</span>
                  <select
                    value={state.draftTarget.seniority_ceiling}
                    onChange={(event) => updateDraftTarget("seniority_ceiling", event.target.value)}
                  >
                    {seniorityOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="check-grid">
                  <label><input type="checkbox" checked={state.draftTarget.strict_location} onChange={(event) => updateDraftTarget("strict_location", event.target.checked)} /> Strict location</label>
                  <label><input type="checkbox" checked={state.draftTarget.strict_work_mode} onChange={(event) => updateDraftTarget("strict_work_mode", event.target.checked)} /> Strict work mode</label>
                  <label><input type="checkbox" checked={state.draftTarget.strict_employment} onChange={(event) => updateDraftTarget("strict_employment", event.target.checked)} /> Strict employment</label>
                  <label><input type="checkbox" checked={state.draftTarget.strict_must_have} onChange={(event) => updateDraftTarget("strict_must_have", event.target.checked)} /> Strict must-haves</label>
                </div>
                <div className="check-grid">
                  <label><input type="checkbox" checked={state.draftTarget!.providers.remotive} onChange={(event) => updateDraftTarget("providers", { ...state.draftTarget!.providers, remotive: event.target.checked })} /> Remotive</label>
                  <label><input type="checkbox" checked={state.draftTarget!.providers.remoteok} onChange={(event) => updateDraftTarget("providers", { ...state.draftTarget!.providers, remoteok: event.target.checked })} /> RemoteOK</label>
                  <label><input type="checkbox" checked={state.draftTarget!.providers.imports} onChange={(event) => updateDraftTarget("providers", { ...state.draftTarget!.providers, imports: event.target.checked })} /> Imports</label>
                </div>
              </div>
            ) : (
              <div className="empty-block">A suggested target appears after profile ingestion.</div>
            )}
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>Imports</h2>
              <button type="button" onClick={handleImport} disabled={state.busy === "import"}>
                {state.busy === "import" ? "Importing..." : "Save import"}
              </button>
            </div>
            <div className="stack">
              <label className="field">
                <span>Import format</span>
                <select
                  value={state.importFormat}
                  onChange={(event) =>
                    setState((current) => ({
                      ...current,
                      importFormat: event.target.value as AppState["importFormat"]
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
                  rows={8}
                  value={state.importContent}
                  onChange={(event) => setState((current) => ({ ...current, importContent: event.target.value }))}
                />
              </label>
            </div>
            <div className="import-list">
              {state.imports.length ? (
                state.imports.map((item) => (
                  <div key={item.id} className="import-row">
                    <strong>{item.label}</strong>
                    <span>{item.item_count} items</span>
                  </div>
                ))
              ) : (
                <div className="empty-block">No saved imports yet.</div>
              )}
            </div>
          </section>
        </section>

        <section className="column column-center">
          <section className="panel panel-stretch">
            <div className="panel-header">
              <h2>Inbox</h2>
              <button type="button" onClick={handleSearch} disabled={state.busy === "search" || !state.savedProfile || !state.savedTarget}>
                {state.busy === "search" ? "Running..." : "Run search"}
              </button>
            </div>
            {state.workspaceLoading ? (
              <div className="empty-block">Loading workspace...</div>
            ) : state.run?.results.length ? (
              <div className="result-list">
                {state.run.results.map((item) => (
                  <button
                    key={item.opportunity.id}
                    type="button"
                    className={`result-row ${state.selectedOpportunityId === item.opportunity.id ? "result-row-active" : ""}`}
                    onClick={() => setState((current) => ({ ...current, selectedOpportunityId: item.opportunity.id }))}
                  >
                    <div className="result-row-top">
                      <strong>{item.opportunity.title}</strong>
                      <span className={`decision decision-${decisionTone(item.assessment.triage_decision)}`}>
                        {item.assessment.triage_decision}
                      </span>
                    </div>
                    <div className="result-row-meta">
                      <span>{item.opportunity.company}</span>
                      <span>{item.opportunity.location}</span>
                      <span>{item.assessment.scores.total}/100</span>
                    </div>
                    <p>{item.assessment.explanation[0]}</p>
                  </button>
                ))}
              </div>
            ) : (
              <div className="empty-block">
                No ranked opportunities yet. Save a target and run search to populate the inbox.
              </div>
            )}
          </section>
        </section>

        <section className="column column-right">
          <section className="panel panel-stretch">
            <div className="panel-header">
              <h2>Detail</h2>
              <button type="button" onClick={refreshActionPlan} disabled={!selectedResult || state.busy === "action-plan"}>
                {state.busy === "action-plan" ? "Refreshing..." : "Refresh action plan"}
              </button>
            </div>
            {selectedResult ? (
              <div className="stack">
                <div className="detail-head">
                  <div>
                    <h3>{selectedResult.opportunity.title}</h3>
                    <p>{selectedResult.opportunity.company} · {selectedResult.opportunity.location} · {selectedResult.opportunity.source}</p>
                  </div>
                  <div className="score-box">{selectedResult.assessment.scores.total}</div>
                </div>

                <div className="metric-grid">
                  <div><span>Role</span><strong>{selectedResult.assessment.scores.role_alignment}/30</strong></div>
                  <div><span>Skills</span><strong>{selectedResult.assessment.scores.skills_alignment}/25</strong></div>
                  <div><span>Seniority</span><strong>{selectedResult.assessment.scores.seniority_alignment}/15</strong></div>
                  <div><span>Location</span><strong>{selectedResult.assessment.scores.location_alignment}/10</strong></div>
                </div>

                <section className="detail-section">
                  <h4>Life fit</h4>
                  <div className="chip-row">
                    <span className="chip">{selectedResult.opportunity.location_type}</span>
                    <span className="chip">{selectedResult.opportunity.seniority_band}</span>
                    <span className="chip">{selectedResult.opportunity.employment_type || "Employment not specified"}</span>
                    <span className="chip">{selectedResult.opportunity.salary_range || "Salary not listed"}</span>
                    <span className="chip">{formatVisaSupport(selectedResult.opportunity.visa_support)}</span>
                  </div>
                </section>

                <section className="detail-section">
                  <h4>Assessment</h4>
                  {selectedResult.assessment.eligible ? (
                    <ul>
                      {selectedResult.assessment.matched_signals.concat(selectedResult.assessment.explanation).map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  ) : (
                    <ul>
                      {selectedResult.assessment.ineligibility_reasons.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  )}
                </section>

                <section className="detail-section">
                  <h4>Gaps and risks</h4>
                  <div className="chip-row">
                    {selectedResult.assessment.missing_requirements.length ? selectedResult.assessment.missing_requirements.map((item) => <span key={item} className="chip chip-warning">{item}</span>) : <span className="chip">No major gaps surfaced</span>}
                  </div>
                  <ul>
                    {selectedResult.assessment.risk_flags.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
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
                    <div className="empty-block">No action plan yet. Apply or tailor candidates get one automatically.</div>
                  )}
                </section>

                <div className="feedback-bar">
                  {["apply", "tailor", "monitor", "skip", "wrong_stack", "wrong_location", "too_senior"].map((label) => (
                    <button key={label} type="button" className="feedback-button" onClick={() => void submitFeedback(label)}>
                      {label.replace(/_/g, " ")}
                    </button>
                  ))}
                </div>

                {selectedResult.opportunity.apply_url && (
                  <a className="apply-link" href={selectedResult.opportunity.apply_url} target="_blank" rel="noreferrer">
                    Open listing
                  </a>
                )}
              </div>
            ) : (
              <div className="empty-block">Select an opportunity from the inbox to inspect the fit and action plan.</div>
            )}
          </section>

          <details className="panel details-panel">
            <summary>Developer details</summary>
            {state.run ? (
              <div className="stack">
                <div className="meta-table">
                  <div><span>Fetched</span><strong>{state.run.run.diagnostics.fetched_listings}</strong></div>
                  <div><span>Normalized</span><strong>{state.run.run.diagnostics.normalized_opportunities}</strong></div>
                  <div><span>Deduped</span><strong>{state.run.run.diagnostics.deduped_opportunities}</strong></div>
                  <div><span>Eligible</span><strong>{state.run.run.diagnostics.eligible_opportunities}</strong></div>
                </div>
                <div className="chip-row">
                  {state.run.run.diagnostics.query_plan.map((item) => <span key={item} className="chip">{item}</span>)}
                </div>
                <ul>
                  {state.run.run.provider_statuses.map((item) => (
                    <li key={item.provider}>{item.provider}: {item.status} · fetched {item.fetched_count} · normalized {item.normalized_count}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="empty-block">No run diagnostics yet.</div>
            )}
          </details>
        </section>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

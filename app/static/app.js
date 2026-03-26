const profileForm = document.getElementById("profile-form");
const resumeInput = document.getElementById("resume");
const extractButton = document.getElementById("extract-button");
const reviewPanel = document.getElementById("review-panel");
const profileDraft = document.getElementById("profile-draft");
const searchButton = document.getElementById("search-button");
const statusCard = document.getElementById("status-card");
const statusText = document.getElementById("status-text");
const results = document.getElementById("results");
const profileSummary = document.getElementById("profile-summary");
const searchSummary = document.getElementById("search-summary");
const matchesList = document.getElementById("matches-list");
const sessionBadge = document.getElementById("session-badge");
const resultView = document.getElementById("result-view");

const targetRolesField = document.getElementById("target-roles");
const preferredLocationsField = document.getElementById("preferred-locations");
const mustHaveSkillsField = document.getElementById("must-have-skills");
const excludedRolesField = document.getElementById("excluded-roles");
const remotePreferenceField = document.getElementById("remote-preference");
const employmentPreferencesField = document.getElementById("employment-preferences");
const searchModeField = document.getElementById("search-mode");
const confirmTargetRolesField = document.getElementById("confirm-target-roles");
const confirmPreferredLocationsField = document.getElementById("confirm-preferred-locations");
const confirmMustHaveSkillsField = document.getElementById("confirm-must-have-skills");
const confirmRemotePreferenceField = document.getElementById("confirm-remote-preference");
const confirmEmploymentPreferencesField = document.getElementById("confirm-employment-preferences");

let currentProfile = null;
let latestPayload = null;
let currentSessionId = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStatus(state, message) {
  statusCard.dataset.state = state;
  statusText.textContent = message;
}

function splitList(value) {
  return String(value)
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function chipRow(items, emptyCopy = "Nothing surfaced yet.") {
  if (!items || !items.length) {
    return `<p class="list-text">${escapeHtml(emptyCopy)}</p>`;
  }
  return `<div class="chip-row">${items.map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}</div>`;
}

function summaryCard(title, content) {
  return `<article class="summary-card"><h3>${escapeHtml(title)}</h3>${content}</article>`;
}

function detailList(items) {
  if (!items || !items.length) {
    return '<p class="list-text">None</p>';
  }
  return `<ul class="detail-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function populatePreferenceForm(profile) {
  targetRolesField.value = profile.core_roles.join("\n");
  preferredLocationsField.value = profile.preferred_locations.join("\n");
  mustHaveSkillsField.value = profile.skills_confirmed.slice(0, 5).join("\n");
  excludedRolesField.value = "";
  remotePreferenceField.value = profile.remote_preference || "remote_or_hybrid";
  employmentPreferencesField.value = profile.employment_preferences.join("\n");
  searchModeField.value = "broad_recall";
  confirmTargetRolesField.checked = false;
  confirmPreferredLocationsField.checked = false;
  confirmMustHaveSkillsField.checked = false;
  confirmRemotePreferenceField.checked = false;
  confirmEmploymentPreferencesField.checked = false;
}

function renderDraftProfile(profile) {
  const confidenceItems = Object.entries(profile.confidence || {})
    .map(([label, value]) => `${label.replaceAll("_", " ")} ${Math.round(value * 100)}%`)
    .slice(0, 6);

  profileDraft.innerHTML = [
    summaryCard("Core roles", chipRow(profile.core_roles, "No role hypothesis yet.")),
    summaryCard("Adjacent roles", chipRow(profile.adjacent_roles, "No adjacent roles inferred.")),
    summaryCard("Confirmed skills", chipRow(profile.skills_confirmed, "No obvious skills extracted.")),
    summaryCard("Inferred skills", chipRow(profile.skills_inferred, "No implied skills inferred.")),
    summaryCard("Projects", detailList(profile.projects.map((item) => item.summary))),
    summaryCard("Confidence", chipRow(confidenceItems, "Confidence signals unavailable.")),
  ].join("");
}

function renderProfileSummary(payload) {
  const profile = payload.candidate;
  sessionBadge.textContent = `Session ${payload.session_id.slice(0, 8)}`;
  profileSummary.innerHTML = [
    summaryCard(
      "Candidate snapshot",
      `<p class="meta-text"><strong>${escapeHtml(profile.filename)}</strong></p>
       <p class="meta-text">${escapeHtml(profile.seniority)}</p>
       <p class="meta-text">${profile.years_experience ? `${profile.years_experience.toFixed(1)} years estimated` : "Years of experience not confidently detected"}</p>`
    ),
    summaryCard("Target roles", chipRow(payload.preferences.target_roles || profile.core_roles)),
    summaryCard("Confirmed skills", chipRow(profile.skills_confirmed)),
    summaryCard("Project evidence", detailList(profile.projects.map((item) => item.summary))),
    summaryCard("Evidence snippets", detailList(profile.evidence_snippets.map((item) => item.snippet))),
    summaryCard("Preferred work setup", chipRow([
      payload.preferences.remote_preference || profile.remote_preference,
      ...(payload.preferences.preferred_locations || profile.preferred_locations),
      ...(payload.preferences.employment_preferences || profile.employment_preferences),
    ], "No work preferences set.")),
  ].join("");
}

function renderSearchSummary(payload) {
  const providers = payload.provider_statuses.map((item) => {
    const details = `${item.provider}: ${item.status}, ${item.normalized_jobs} usable jobs`;
    return item.error ? `${details} (${item.error})` : details;
  });
  const diagnostics = payload.diagnostics || {};
  const funnel = [
    `Fetched ${diagnostics.fetched_jobs ?? 0}`,
    `Normalized ${diagnostics.normalized_jobs ?? 0}`,
    `Deduped ${diagnostics.deduped_jobs ?? 0}`,
    `Role pass ${diagnostics.role_filtered_jobs ?? 0}`,
    `Location pass ${diagnostics.location_filtered_jobs ?? 0}`,
    `Employment pass ${diagnostics.employment_filtered_jobs ?? 0}`,
    `Relevance pass ${diagnostics.relevance_filtered_jobs ?? 0}`,
    `Ranked ${diagnostics.final_ranked_jobs ?? 0}`,
  ];

  searchSummary.innerHTML = [
    summaryCard("Search plan", chipRow(payload.search_plan.combined_queries, "No search plan available.")),
    summaryCard("Exact role queries", chipRow(payload.search_plan.exact_role_queries)),
    summaryCard("Adjacent role queries", chipRow(payload.search_plan.adjacent_role_queries)),
    summaryCard("Stack-led queries", chipRow(payload.search_plan.stack_queries)),
    summaryCard("Widened role queries", chipRow(payload.search_plan.widened_role_queries || [], "No expanded role queries.")),
    summaryCard("Search mode", chipRow([
      payload.search_plan.search_mode || "broad_recall",
      ...((payload.search_plan.active_filters || []).map((item) => `hard filter: ${item}`)),
    ], "No active hard filters.")),
    summaryCard("Search funnel", detailList(funnel)),
    summaryCard("Relaxations", detailList(diagnostics.relaxation_steps || [])),
    summaryCard("Providers", detailList(providers)),
    summaryCard("Next focus", detailList(payload.summary.focus_areas.map((item) => `${item.title}: ${item.detail}`))),
  ].join("");
}

function scoreTone(label) {
  const normalized = label.toLowerCase();
  if (normalized.includes("exact")) return "strong";
  if (normalized.includes("strong")) return "promising";
  if (normalized.includes("tailoring")) return "tailored";
  return "stretch";
}

function feedbackButtons(match) {
  const options = [
    ["relevant", "Relevant"],
    ["too_senior", "Too senior"],
    ["wrong_stack", "Wrong stack"],
    ["wrong_location", "Wrong location"],
    ["good_stretch", "Good stretch"],
  ];
  return `<div class="feedback-row">${options
    .map(
      ([value, label]) =>
        `<button class="feedback-button" type="button" data-feedback="${value}" data-job-id="${escapeHtml(match.job.id)}">${escapeHtml(label)}</button>`
    )
    .join("")}</div>`;
}

function renderMatch(match) {
  const tone = scoreTone(match.score_label);
  const link = match.job.apply_url
    ? `<a class="match-link" href="${escapeHtml(match.job.apply_url)}" target="_blank" rel="noreferrer">Open listing</a>`
    : "";

  return `
    <article class="match-card">
      <div class="match-head">
        <div>
          <h3>${escapeHtml(match.job.title)}</h3>
          <p class="match-meta">${escapeHtml(match.job.company)} • ${escapeHtml(match.job.location)} • ${escapeHtml(match.job.seniority_band)}</p>
          <p class="match-meta">${escapeHtml(match.recommendation_tier)} • ${escapeHtml(match.likely_rejection_driver)}</p>
        </div>
        <div class="score-badge ${tone}">${match.score}</div>
      </div>

      <p class="match-copy">${escapeHtml(match.reasoning)}</p>

      <div class="metric-row">
        <div class="metric"><span class="metric-label">Role</span><span class="metric-value">${match.breakdown.role_fit}/25</span></div>
        <div class="metric"><span class="metric-label">Required</span><span class="metric-value">${match.breakdown.required_skills_fit}/25</span></div>
        <div class="metric"><span class="metric-label">Transferable</span><span class="metric-value">${match.breakdown.adjacent_fit}/15</span></div>
        <div class="metric"><span class="metric-label">Seniority</span><span class="metric-value">${match.breakdown.seniority_fit}/10</span></div>
        <div class="metric"><span class="metric-label">Location</span><span class="metric-value">${match.breakdown.location_fit}/10</span></div>
        <div class="metric"><span class="metric-label">Projects</span><span class="metric-value">${match.breakdown.project_fit}/10</span></div>
        <div class="metric"><span class="metric-label">Quality</span><span class="metric-value">${match.breakdown.source_quality_fit}/5</span></div>
      </div>

      <div class="match-columns">
        <section class="match-panel">
          <h4>Why it surfaced</h4>
          ${detailList(match.surfaced_reasons)}
        </section>
        <section class="match-panel">
          <h4>Hard requirements met</h4>
          ${chipRow(match.hard_requirements_met, "No hard requirements matched yet.")}
        </section>
        <section class="match-panel">
          <h4>Hard requirements missing</h4>
          ${chipRow(match.hard_requirements_missing, "No major hard gaps detected.")}
        </section>
        <section class="match-panel">
          <h4>Transferable evidence</h4>
          ${detailList(match.transferable_evidence)}
        </section>
      </div>

      <div class="match-foot">
        <div class="meta-stack">
          <p class="match-meta">${escapeHtml(match.why_this_is_still_worth_applying)}</p>
          <p class="match-meta">${escapeHtml(match.breakdown.explanation)}</p>
          ${link ? `<p class="match-meta">${link} • Source: ${escapeHtml(match.job.source)}</p>` : `<p class="match-meta">Source: ${escapeHtml(match.job.source)}</p>`}
        </div>
        ${feedbackButtons(match)}
      </div>
    </article>
  `;
}

function sortedMatches(matches, mode) {
  const items = [...matches];
  if (mode === "remote") {
    return items.filter((item) => item.job.location_type === "remote" || item.job.location_type === "hybrid");
  }
  if (mode === "newest") {
    return items.sort((a, b) => (a.job.job_age_days ?? 9999) - (b.job.job_age_days ?? 9999));
  }
  if (mode === "growth") {
    return items.sort(
      (a, b) =>
        (b.breakdown.project_fit + b.breakdown.adjacent_fit + b.score) -
        (a.breakdown.project_fit + a.breakdown.adjacent_fit + a.score)
    );
  }
  if (mode === "discovery") {
    return items.sort(
      (a, b) =>
        (b.breakdown.adjacent_fit + b.breakdown.project_fit) -
        (a.breakdown.adjacent_fit + a.breakdown.project_fit)
    );
  }
  return items.sort((a, b) => b.score - a.score);
}

function renderMatches(payload) {
  const filtered = sortedMatches(payload.matches, resultView.value);
  if (!filtered.length) {
    matchesList.innerHTML = '<div class="empty-state">No jobs match the current result view. Try a different filter.</div>';
    return;
  }
  matchesList.innerHTML = filtered.map(renderMatch).join("");
}

function buildSearchRequest() {
  return {
    candidate: currentProfile,
    preferences: {
      target_roles: splitList(targetRolesField.value),
      preferred_locations: splitList(preferredLocationsField.value),
      remote_preference: remotePreferenceField.value,
      employment_preferences: splitList(employmentPreferencesField.value),
      must_have_skills: splitList(mustHaveSkillsField.value),
      excluded_roles: splitList(excludedRolesField.value),
      ranking_mode: "balanced",
      search_mode: searchModeField.value,
      confirmed_preferences: {
        target_roles: confirmTargetRolesField.checked,
        preferred_locations: confirmPreferredLocationsField.checked,
        must_have_skills: confirmMustHaveSkillsField.checked,
        remote_preference: confirmRemotePreferenceField.checked,
        employment_preferences: confirmEmploymentPreferencesField.checked,
      },
    },
    session_id: currentSessionId,
  };
}

async function extractProfile(event) {
  event.preventDefault();
  const formData = new FormData(profileForm);
  if (!resumeInput.files.length) {
    setStatus("error", "Choose a resume file before extracting a profile.");
    return;
  }

  extractButton.disabled = true;
  setStatus("loading", "Reading your resume and drafting a candidate profile...");

  try {
    const response = await fetch("/api/profile/extract", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Could not extract a profile from the uploaded resume.");
    }

    currentProfile = payload.candidate;
    populatePreferenceForm(currentProfile);
    renderDraftProfile(currentProfile);
    reviewPanel.hidden = false;
    setStatus("success", "Draft profile ready. Review it, then search for jobs.");
  } catch (error) {
    setStatus("error", error.message || "The resume could not be profiled.");
  } finally {
    extractButton.disabled = false;
  }
}

async function runSearch() {
  if (!currentProfile) {
    setStatus("error", "Extract a draft profile before searching.");
    return;
  }

  searchButton.disabled = true;
  setStatus("loading", "Searching live providers, normalizing jobs, and ranking the best fits...");
  try {
    const response = await fetch("/api/jobs/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildSearchRequest()),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "The job search failed.");
    }

    latestPayload = payload;
    currentSessionId = payload.session_id;
    results.style.display = "block";
    renderProfileSummary(payload);
    renderSearchSummary(payload);
    renderMatches(payload);
    setStatus(
      "success",
      `Finished ranking ${payload.jobs_analyzed} jobs. Best current fit: ${payload.summary.strongest_fit || "n/a"}.`
    );
  } catch (error) {
    setStatus("error", error.message || "The job search failed.");
  } finally {
    searchButton.disabled = false;
  }
}

async function submitFeedback(jobId, label) {
  if (!currentSessionId) {
    return;
  }

  const response = await fetch("/api/feedback", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: currentSessionId,
      job_id: jobId,
      label,
    }),
  });
  const payload = await response.json();
  if (payload.saved) {
    setStatus("success", `Saved feedback: ${label.replaceAll("_", " ")}. Re-run the search to reweight similar jobs.`);
  } else {
    setStatus("error", "Could not save feedback for that result.");
  }
}

profileForm.addEventListener("submit", extractProfile);
searchButton.addEventListener("click", runSearch);
resultView.addEventListener("change", () => {
  if (latestPayload) {
    renderMatches(latestPayload);
  }
});

matchesList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-feedback]");
  if (!button) return;
  await submitFeedback(button.dataset.jobId, button.dataset.feedback);
});

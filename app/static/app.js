const form = document.getElementById("analyze-form");
const submitButton = document.getElementById("submit-button");
const statusCard = document.getElementById("status-card");
const statusText = document.getElementById("status-text");
const results = document.getElementById("results");
const resumeSummary = document.getElementById("resume-summary");
const insightsSummary = document.getElementById("insights-summary");
const matchesList = document.getElementById("matches-list");

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

function createChipRow(items) {
  if (!items || !items.length) {
    return '<p class="list-text">None detected yet.</p>';
  }

  return `<div class="chip-row">${items
    .map((item) => `<span class="chip">${escapeHtml(item)}</span>`)
    .join("")}</div>`;
}

function createSummaryCard(title, content) {
  return `<article class="summary-card"><h3>${title}</h3>${content}</article>`;
}

function createInsightCard(title, content) {
  return `<article class="insight-card"><h3>${title}</h3>${content}</article>`;
}

function scoreTone(label) {
  const normalized = label.toLowerCase();
  if (normalized.includes("strong")) return "strong";
  if (normalized.includes("promising")) return "promising";
  if (normalized.includes("stretch")) return "stretch";
  return "low";
}

function renderResumeSummary(payload) {
  const experience = payload.resume.experience_years
    ? `${payload.resume.experience_years.toFixed(1)} years estimated`
    : "No explicit years detected";
  const education = payload.resume.education.length
    ? payload.resume.education.join(", ")
    : "No degree keywords detected";
  const signals = payload.resume.signals.length
    ? `<p class="meta-text">${payload.resume.signals.map(escapeHtml).join(" • ")}</p>`
    : '<p class="meta-text">Upload a fuller resume to surface stronger highlights.</p>';

  resumeSummary.innerHTML = [
    createSummaryCard(
      "Profile details",
      `<p class="meta-text"><strong>${escapeHtml(payload.resume.filename)}</strong></p>
       <p class="meta-text">${payload.jobs_analyzed} jobs analyzed</p>
       <p class="meta-text">${escapeHtml(experience)}</p>
       <p class="meta-text">${escapeHtml(education)}</p>`
    ),
    createSummaryCard("Detected skills", createChipRow(payload.resume.skills)),
    createSummaryCard(
      "Strongest fit",
      `<p class="meta-text">${escapeHtml(payload.summary.strongest_fit || "No match available yet")}</p>`
    ),
    createSummaryCard("Resume signals", signals),
  ].join("");
}

function renderInsights(payload) {
  const topMissing = payload.summary.top_missing_skills.length
    ? `<div class="chip-row">${payload.summary.top_missing_skills
        .map((item) => `<span class="chip">${escapeHtml(item.skill)} (${item.frequency})</span>`)
        .join("")}</div>`
    : '<p class="list-text">No recurring skill gaps surfaced.</p>';

  const searchTerms = payload.summary.search_terms.length
    ? `<div class="chip-row">${payload.summary.search_terms
        .map((item) => `<span class="chip">${escapeHtml(item)}</span>`)
        .join("")}</div>`
    : '<p class="list-text">No search terms were derived.</p>';

  const providersUsed = payload.summary.providers_used.length
    ? `<p class="list-text">${payload.summary.providers_used.map(escapeHtml).join(", ")}</p>`
    : '<p class="list-text">No provider reported.</p>';

  const focusAreas = payload.summary.focus_areas.length
    ? payload.summary.focus_areas
        .map(
          (item) =>
            `<article class="insight-card"><h3>${escapeHtml(item.title)}</h3><p class="list-text">${escapeHtml(item.detail)}</p></article>`
        )
        .join("")
    : createInsightCard(
        "Next step",
        '<p class="list-text">Add clearer skills and project details to your resume to improve the search and scoring signal.</p>'
      );

  insightsSummary.innerHTML = [
    createInsightCard("Narrative", `<p class="list-text">${escapeHtml(payload.summary.narrative)}</p>`),
    createInsightCard("Recurring missing skills", topMissing),
    createInsightCard("Search terms used", searchTerms),
    createInsightCard("Live sources used", providersUsed),
    payload.summary.external_factor_roles.length
      ? createInsightCard(
          "Roles where rejection may be external",
          `<p class="list-text">${payload.summary.external_factor_roles.map(escapeHtml).join(", ")}</p>`
        )
      : createInsightCard(
          "Rejection signal",
          '<p class="list-text">Most current gaps still look skill-related rather than competition-related.</p>'
        ),
    focusAreas,
  ].join("");
}

function renderMatch(match) {
  const tone = scoreTone(match.score_label);
  const matchedSkills = createChipRow(match.matched_skills);
  const missingSkills = createChipRow(match.missing_skills);
  const applyLink = match.job.url
    ? `<p class="match-meta"><a class="match-link" href="${escapeHtml(match.job.url)}" target="_blank" rel="noreferrer">Open listing</a> • Source: ${escapeHtml(match.job.source)}</p>`
    : `<p class="match-meta">Source: ${escapeHtml(match.job.source)}</p>`;

  return `
    <article class="match-card">
      <div class="match-head">
        <div>
          <h3>${escapeHtml(match.job.title)}</h3>
          <p class="match-meta">${escapeHtml(match.job.company)} • ${escapeHtml(match.job.location)}</p>
          <p class="match-meta">${escapeHtml(match.score_label)} • ${escapeHtml(match.likely_rejection_driver)}</p>
        </div>
        <div class="score-badge ${tone}">${match.score}%</div>
      </div>
      <p class="match-copy">${escapeHtml(match.reasoning)}</p>
      ${applyLink}
      <div class="metric-row">
        <div class="metric">
          <span class="metric-label">Skills</span>
          <span class="metric-value">${match.breakdown.skill_score}/55</span>
        </div>
        <div class="metric">
          <span class="metric-label">Title fit</span>
          <span class="metric-value">${match.breakdown.title_score}/15</span>
        </div>
        <div class="metric">
          <span class="metric-label">Experience</span>
          <span class="metric-value">${match.breakdown.experience_score}/15</span>
        </div>
        <div class="metric">
          <span class="metric-label">Context</span>
          <span class="metric-value">${match.breakdown.context_score}/15</span>
        </div>
      </div>
      <div class="skill-blocks">
        <section class="skill-panel">
          <h4>Matched skills</h4>
          ${matchedSkills}
        </section>
        <section class="skill-panel ${match.missing_skills.length ? "" : "empty"}">
          <h4>Missing skills</h4>
          ${missingSkills}
        </section>
      </div>
      <p class="match-meta">${escapeHtml(match.breakdown.explanation)}</p>
    </article>
  `;
}

function renderMatches(payload) {
  matchesList.innerHTML = payload.matches.map(renderMatch).join("");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(form);

  submitButton.disabled = true;
  setStatus("loading", "Reading your resume, finding live jobs, and scoring the best matches...");
  results.style.display = "none";

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "The analysis request failed.");
    }

    renderResumeSummary(payload);
    renderInsights(payload);
    renderMatches(payload);
    results.style.display = "block";
    setStatus(
      "success",
      `Finished scoring ${payload.jobs_analyzed} jobs. Highest match: ${payload.summary.strongest_fit || "n/a"}.`
    );
  } catch (error) {
    setStatus("error", error.message || "The analysis failed.");
  } finally {
    submitButton.disabled = false;
  }
});

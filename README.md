# AI-Assisted Job Application Insight Tool

FastAPI app for uploading a resume, extracting a draft candidate profile, searching live public job feeds, and ranking the strongest early-career matches with transparent reasoning.

## What it does

- Upload a resume and extract a richer candidate profile.
- Infer target roles, adjacent roles, seniority, projects, and confirmed skills.
- Let the user review and edit the inferred search intent before jobs are fetched.
- Search public job feeds with a structured search plan instead of a single keyword guess.
- Normalize messy job descriptions into required skills, preferred skills, seniority, location type, freshness, and source quality.
- Rank jobs with role fit, hard-skill coverage, transferable evidence, early-career fit, location fit, project relevance, and source quality.
- Capture inline result feedback such as `relevant`, `too senior`, `wrong stack`, and `good stretch`.
- Run an offline benchmark suite against curated fixture cases.

## Supported input

- Resume upload: `TXT`, `MD`, `DOC`, `DOCX`, `RTF`, and `PDF`

`TXT` resumes work out of the box. `DOCX` uses macOS `textutil`. `PDF` parsing requires `pypdf`.

## Run locally

```bash
cd ai-job-matcher
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Then open [http://127.0.0.1:8010](http://127.0.0.1:8010).

## API flow

- `POST /api/profile/extract`
  - Upload a resume and receive a draft `CandidateProfile`.
- `POST /api/jobs/search`
  - Submit the reviewed candidate profile plus search preferences and receive ranked jobs.
- `POST /api/feedback`
  - Save per-result feedback for future reweighting within the session.
- `POST /api/analyze`
  - Backward-compatible one-step wrapper that uploads, auto-accepts defaults, searches, and ranks.

## Quality checks

```bash
pytest -q
python3 -m compileall app tests
```

## Current architecture highlights

- `app/services/profile_extraction.py`
  - Builds the candidate profile and evidence snippets from resume text.
- `app/services/job_search.py`
  - Builds the search plan, wraps job providers, normalizes jobs, and deduplicates results.
- `app/services/scoring.py`
  - Runs the staged ranking logic and stores in-session result feedback.
- `app/services/evaluation.py`
  - Evaluates benchmark fixtures with precision, MRR, relevant-result rate, and too-senior rate.

## Notes

- The app is designed for early-career matching first.
- The “deep” reasoning layer is currently implemented as transparent heuristic + semantic scoring rather than a live external LLM call, so it runs locally and stays testable.
- Because live job feeds can change response shapes over time, provider adapters may still need small maintenance updates later.

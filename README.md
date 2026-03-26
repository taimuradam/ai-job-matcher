# AI-Assisted Job Application Insight Tool

Personal FastAPI project for uploading a resume, fetching matching live job postings from public job feeds, ranking the best-fit roles, and surfacing the difference between likely skill gaps and likely external rejection factors.

## What it does

- Upload a resume and extract readable experience and skill signals.
- Infer role and keyword searches from the resume automatically.
- Fetch live jobs from public job feeds and score them against the resume.
- Show transparent score breakdowns instead of a black-box number.
- Highlight recurring missing skills across your strongest target roles.
- Flag roles where a rejection may be driven more by competition than by profile mismatch.

## Supported input

- Resume upload: `TXT`, `MD`, `DOC`, `DOCX`, `RTF`, and `PDF`

`TXT` resumes work out of the box. `DOCX` uses macOS `textutil`. `PDF` parsing requires `pypdf`.

## Run locally

```bash
cd /Users/taimuradam/Desktop/Personal/Code_Projects/JobInsightTool
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Then open [http://127.0.0.1:8010](http://127.0.0.1:8010).

## Live search behavior

- The app derives several likely role searches from the resume.
- It currently queries public remote-job feeds and filters results for relevance.
- The fetched postings are then scored for skills, title alignment, experience, and overall context fit.

Because live job sources can change their response shapes over time, this provider layer may need small endpoint updates in the future.

## Next upgrades

- Add more job providers and stronger source normalization.
- Store application outcomes and trend them over time.
- Add optional LLM-generated coaching summaries.
- Pull live jobs from saved searches or ATS-specific connectors.

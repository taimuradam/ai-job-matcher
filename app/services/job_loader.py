from __future__ import annotations

import csv
import json
import re
from io import StringIO
from pathlib import Path

from fastapi import UploadFile

from app.schemas import JobRecord


def _decode_text(raw_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("The job dataset could not be decoded as text.")


def _coalesce(mapping: dict[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        value = mapping.get(key, "")
        if value:
            return value.strip()
    return default


def _job_from_mapping(mapping: dict[str, str], source: str) -> JobRecord:
    title = _coalesce(mapping, "title", "role", "job_title")
    description = _coalesce(mapping, "description", "job_description", "summary")
    if not title or not description:
        raise ValueError(
            "Each uploaded job entry must include at least 'title' and 'description'."
        )

    return JobRecord(
        title=title,
        company=_coalesce(mapping, "company", "organization", default="Unknown"),
        location=_coalesce(mapping, "location", "city", default="Not specified"),
        description=description,
        employment_type=_coalesce(mapping, "employment_type", "type") or None,
        url=_coalesce(mapping, "url", "link") or None,
        source=source,
    )


def _parse_csv_jobs(raw_text: str) -> list[JobRecord]:
    reader = csv.DictReader(StringIO(raw_text))
    jobs = [_job_from_mapping({k.lower(): v for k, v in row.items()}, "csv") for row in reader]
    if not jobs:
        raise ValueError("The uploaded CSV did not contain any job rows.")
    return jobs


def _parse_json_jobs(raw_text: str) -> list[JobRecord]:
    payload = json.loads(raw_text)
    items = payload["jobs"] if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not items:
        raise ValueError("The uploaded JSON must be a non-empty list of jobs.")
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Every JSON job entry must be an object.")
        jobs.append(_job_from_mapping({str(k).lower(): str(v) for k, v in item.items()}, "json"))
    return jobs


def _parse_text_blocks(raw_text: str) -> list[JobRecord]:
    blocks = [
        block.strip()
        for block in re.split(r"\n\s*---\s*\n", raw_text.strip())
        if block.strip()
    ]
    jobs: list[JobRecord] = []
    for index, block in enumerate(blocks, start=1):
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        mapping: dict[str, str] = {}
        description_lines: list[str] = []
        in_description = False
        for line in lines:
            if ":" in line and not in_description:
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip()
                if key == "description":
                    in_description = True
                    if value:
                        description_lines.append(value)
                else:
                    mapping[key] = value
            else:
                in_description = True
                description_lines.append(line)

        if "title" not in mapping:
            raise ValueError(
                f"Text block {index} is missing a 'Title:' line."
            )
        mapping["description"] = "\n".join(description_lines).strip()
        jobs.append(_job_from_mapping(mapping, "text"))

    if not jobs:
        raise ValueError("No job descriptions were found in the pasted text.")
    return jobs


async def _parse_uploaded_jobs(upload: UploadFile) -> list[JobRecord]:
    if not upload.filename:
        raise ValueError("The uploaded job dataset needs a filename.")

    raw_bytes = await upload.read()
    if not raw_bytes:
        raise ValueError("The uploaded job dataset was empty.")

    raw_text = _decode_text(raw_bytes)
    suffix = Path(upload.filename).suffix.lower()
    if suffix == ".csv":
        return _parse_csv_jobs(raw_text)
    if suffix == ".json":
        return _parse_json_jobs(raw_text)
    if suffix in {".txt", ".md"}:
        return _parse_text_blocks(raw_text)

    raise ValueError("Use CSV, JSON, or TXT for the job dataset upload.")


def _load_sample_jobs(base_dir: Path) -> list[JobRecord]:
    sample_path = base_dir / "data" / "sample_jobs.json"
    payload = json.loads(sample_path.read_text())
    return [_job_from_mapping({str(k).lower(): str(v) for k, v in item.items()}, "sample") for item in payload]


async def load_jobs(
    jobs_file: UploadFile | None,
    job_text: str,
    use_sample_jobs: bool,
    base_dir: Path,
) -> list[JobRecord]:
    if jobs_file is not None and jobs_file.filename:
        return await _parse_uploaded_jobs(jobs_file)
    if job_text.strip():
        return _parse_text_blocks(job_text)
    if use_sample_jobs:
        return _load_sample_jobs(base_dir)
    raise ValueError(
        "Upload a job dataset, paste at least one job description, or enable sample jobs."
    )

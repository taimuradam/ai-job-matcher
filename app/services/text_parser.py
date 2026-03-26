from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from fastapi import UploadFile


TEXT_EXTENSIONS = {".txt", ".md", ".rst"}
WORD_PROCESSOR_EXTENSIONS = {".doc", ".docx", ".rtf"}


def _decode_text(raw_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("The uploaded file could not be decoded as text.")


def _extract_doc_with_textutil(raw_bytes: bytes, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        temp_file.write(raw_bytes)
        temp_path = Path(temp_file.name)

    try:
        result = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", str(temp_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        text = result.stdout.strip()
        if not text:
            raise ValueError("The document did not contain any readable text.")
        return text
    except FileNotFoundError as exc:
        raise ValueError(
            "DOCX parsing requires macOS textutil or python-docx to be installed."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError("The document could not be converted into plain text.") from exc
    finally:
        temp_path.unlink(missing_ok=True)


def _extract_pdf(raw_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError(
            "PDF parsing requires the optional 'pypdf' package. "
            "Install it or upload a TXT/DOCX resume."
        ) from exc

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
        temp_file.write(raw_bytes)
        temp_path = Path(temp_file.name)

    try:
        reader = PdfReader(str(temp_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if not text:
            raise ValueError("The PDF did not contain extractable text.")
        return text
    finally:
        temp_path.unlink(missing_ok=True)


async def extract_text_from_upload(upload: UploadFile) -> str:
    if not upload.filename:
        raise ValueError("Please upload a resume file.")

    raw_bytes = await upload.read()
    if not raw_bytes:
        raise ValueError("The uploaded file was empty.")

    suffix = Path(upload.filename).suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return _decode_text(raw_bytes).strip()
    if suffix in WORD_PROCESSOR_EXTENSIONS:
        return _extract_doc_with_textutil(raw_bytes, suffix)
    if suffix == ".pdf":
        return _extract_pdf(raw_bytes)

    raise ValueError(
        "Unsupported file type. Use TXT, MD, DOC, DOCX, RTF, or PDF."
    )

"""Upload ingestion: txt/md/pdf/docx bytes with caps. No disk writes."""
from __future__ import annotations

from dataclasses import dataclass

from pruvfetch.extract import extract_text

ALLOWED_SUFFIXES = (".txt", ".md", ".pdf", ".docx")
MAX_FILE_BYTES = 200_000
MAX_FILES = 5


@dataclass(frozen=True)
class UploadedDoc:
    name: str
    text: str
    truncated: bool = False
    kind: str = "txt"
    warning: str = ""


def read_uploads(files: list) -> list:
    """Read Streamlit-style uploads (objects with .name + .getvalue()/.read()).

    Skips disallowed suffixes and enforces size/count caps.
    """
    docs: list = []
    for f in (files or [])[:MAX_FILES]:
        name = str(getattr(f, "name", "upload"))
        if not name.lower().endswith(ALLOWED_SUFFIXES):
            continue
        raw = f.getvalue() if hasattr(f, "getvalue") else f.read()
        data = bytes(raw() if callable(raw) else raw)
        if name.lower().endswith((".pdf", ".docx")):
            ext = extract_text(name, data)
            docs.append(UploadedDoc(name=name, text=ext.text, truncated=ext.truncated,
                                    kind=ext.kind, warning=ext.warning))
            continue
        truncated = len(data) > MAX_FILE_BYTES
        text = data[:MAX_FILE_BYTES].decode("utf-8", errors="replace")
        docs.append(UploadedDoc(name=name, text=text, truncated=truncated, kind="txt"))
    return docs

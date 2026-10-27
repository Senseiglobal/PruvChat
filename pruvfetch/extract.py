"""Text extraction for txt/md/pdf/docx uploads. Safe, capped, never raises."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

try:
    from pypdf import PdfReader, PdfWriter  # noqa: F401 (writer used by tests)
    _HAVE_PDF = True
except Exception:
    _HAVE_PDF = False

try:
    from docx import Document
    _HAVE_DOCX = True
except Exception:
    _HAVE_DOCX = False

MAX_FILE_BYTES = 200_000
MAX_PDF_PAGES = 30
MAX_DOCX_PARAS = 2000


@dataclass(frozen=True)
class ExtractedDoc:
    name: str
    text: str
    kind: str = "txt"  # txt | pdf | docx
    pages: int | None = None
    truncated: bool = False
    warning: str = ""
    size_bytes: int = 0


def _fail(name: str, kind: str, warning: str, size: int) -> ExtractedDoc:
    return ExtractedDoc(name=name, text="", kind=kind, warning=warning, size_bytes=size)


def extract_text(name: str, data: bytes) -> ExtractedDoc:
    """Extract text by file suffix. Returns warnings instead of raising."""
    size = len(data or b"")
    low = str(name or "upload").lower()
    if low.endswith((".txt", ".md")):
        return ExtractedDoc(name=str(name), text=bytes(data or b"").decode("utf-8", errors="replace"),
                            kind="txt", size_bytes=size)
    if low.endswith(".pdf"):
        return _extract_pdf(str(name), bytes(data or b""), size)
    if low.endswith(".docx"):
        return _extract_docx(str(name), bytes(data or b""), size)
    return _fail(str(name), "txt", f"unsupported file type: {name}", size)


def _extract_pdf(name: str, data: bytes, size: int) -> ExtractedDoc:
    if not _HAVE_PDF:
        return _fail(name, "pdf", "PDF support not installed (pypdf missing)", size)
    if size > MAX_FILE_BYTES:
        return _fail(name, "pdf", f"PDF exceeds {MAX_FILE_BYTES}-byte cap; skipped", size)
    if not data:
        return _fail(name, "pdf", "empty file", size)
    try:
        reader = PdfReader(BytesIO(data), strict=False)
    except Exception as exc:
        return _fail(name, "pdf", f"could not parse PDF: {type(exc).__name__}", size)
    try:
        npages = len(reader.pages)
    except Exception:
        return _fail(name, "pdf", "could not read PDF pages", size)
    parts: list = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    text = "\n".join(p for p in (s.strip() for s in parts) if p)
    warning = ""
    if npages > MAX_PDF_PAGES:
        warning = f"only first {MAX_PDF_PAGES} of {npages} pages read"
    if not text.strip():
        note = "no extractable text (scanned image or empty page; OCR not available)"
        warning = f"{warning}; {note}" if warning else note
    return ExtractedDoc(name=name, text=text, kind="pdf", pages=npages,
                        truncated=npages > MAX_PDF_PAGES, warning=warning, size_bytes=size)


def _extract_docx(name: str, data: bytes, size: int) -> ExtractedDoc:
    if not _HAVE_DOCX:
        return _fail(name, "docx", "DOCX support not installed (python-docx missing)", size)
    if size > MAX_FILE_BYTES:
        return _fail(name, "docx", f"DOCX exceeds {MAX_FILE_BYTES}-byte cap; skipped", size)
    if not data:
        return _fail(name, "docx", "empty file", size)
    try:
        doc = Document(BytesIO(data))
        paras = [p.text for p in doc.paragraphs]
    except Exception as exc:
        return _fail(name, "docx", f"could not parse DOCX: {type(exc).__name__}", size)
    kept = paras[:MAX_DOCX_PARAS]
    text = "\n".join(s for s in (s.strip() for s in kept) if s)
    warning = ""
    if len(paras) > MAX_DOCX_PARAS:
        warning = f"only first {MAX_DOCX_PARAS} of {len(paras)} paragraphs read"
    if not text.strip():
        note = "no text found in document"
        warning = f"{warning}; {note}" if warning else note
    return ExtractedDoc(name=name, text=text, kind="docx",
                        truncated=len(paras) > MAX_DOCX_PARAS, warning=warning, size_bytes=size)

"""PruvFetch: uploads + safe URL ingest (offline stub in Phase 1)."""
from pruvfetch.extract import ExtractedDoc, extract_text
from pruvfetch.fetch import FetchedDoc, fetch_url
from pruvfetch.uploads import MAX_FILE_BYTES, MAX_FILES, UploadedDoc, read_uploads
from pruvfetch.urls import UrlIngestResult, ingest_url, validate_url

__all__ = [
    "MAX_FILE_BYTES",
    "MAX_FILES",
    "ExtractedDoc",
    "FetchedDoc",
    "UploadedDoc",
    "extract_text",
    "fetch_url",
    "read_uploads",
    "UrlIngestResult",
    "ingest_url",
    "validate_url",
]

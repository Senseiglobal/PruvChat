"""PDF/DOCX extraction: real text out, honest warnings, never raises."""
from io import BytesIO

import pytest

from pruvfetch.extract import MAX_FILE_BYTES, extract_text
from pruvfetch.uploads import read_uploads

pypdf = pytest.importorskip("pypdf")
docx_mod = pytest.importorskip("docx")


def _make_pdf(text: str) -> bytes:
    """Build a minimal valid one-page PDF with correct xref offsets."""
    content = f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode()
    return bytes(out)


def _make_docx(paragraphs) -> bytes:
    buf = BytesIO()
    doc = docx_mod.Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(buf)
    return buf.getvalue()


class FakeUpload:
    def __init__(self, name, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


def test_pdf_extracts_real_text():
    ext = extract_text("spec.pdf", _make_pdf("Hello PDF extraction"))
    assert ext.kind == "pdf"
    assert "Hello PDF extraction" in ext.text
    assert ext.pages == 1
    assert ext.warning == ""


def test_pdf_blank_page_warns_about_ocr():
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    ext = extract_text("scan.pdf", buf.getvalue())
    assert ext.text == ""
    assert "OCR" in ext.warning


def test_pdf_corrupt_bytes_never_raise():
    ext = extract_text("broken.pdf", b"%PDF-1.4 not really a pdf \x00\xff" * 10)
    assert ext.text == ""
    assert "could not parse" in ext.warning or "no extractable text" in ext.warning


def test_pdf_oversize_skipped():
    ext = extract_text("big.pdf", b"x" * (MAX_FILE_BYTES + 1))
    assert ext.text == ""
    assert "cap" in ext.warning


def test_docx_round_trip():
    ext = extract_text("notes.docx", _make_docx(["First line here", "Second line here"]))
    assert ext.kind == "docx"
    assert "First line here" in ext.text and "Second line here" in ext.text
    assert ext.warning == ""


def test_docx_corrupt_bytes_never_raise():
    ext = extract_text("broken.docx", b"PK not a zip" * 50)
    assert ext.text == ""
    assert "could not parse" in ext.warning


def test_unsupported_suffix_warns():
    ext = extract_text("photo.png", b"fake")
    assert ext.text == "" and "unsupported" in ext.warning


def test_read_uploads_accepts_pdf_and_docx():
    docs = read_uploads([
        FakeUpload("a.pdf", _make_pdf("Alpha beta")),
        FakeUpload("b.docx", _make_docx(["Gamma delta"])),
        FakeUpload("c.exe", b"nope"),
    ])
    assert [(d.name, d.kind) for d in docs] == [("a.pdf", "pdf"), ("b.docx", "docx")]
    assert "Alpha beta" in docs[0].text
    assert "Gamma delta" in docs[1].text

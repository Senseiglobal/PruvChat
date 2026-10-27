"""Upload ingestion: suffix allowlist, size and count caps."""
from pruvfetch.uploads import MAX_FILE_BYTES, MAX_FILES, read_uploads


class FakeUpload:
    def __init__(self, name, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


def test_read_uploads_txt_ok():
    docs = read_uploads([FakeUpload("notes.txt", b"hello world")])
    assert len(docs) == 1
    assert docs[0].name == "notes.txt"
    assert docs[0].text == "hello world"
    assert docs[0].truncated is False


def test_read_uploads_skips_disallowed_suffix():
    docs = read_uploads([FakeUpload("evil.exe", b"data"), FakeUpload("photo.png", b"data")])
    assert docs == []


def test_read_uploads_truncates_oversize():
    docs = read_uploads([FakeUpload("big.md", b"x" * (MAX_FILE_BYTES + 10))])
    assert len(docs) == 1
    assert docs[0].truncated is True
    assert len(docs[0].text.encode("utf-8")) == MAX_FILE_BYTES


def test_read_uploads_enforces_count_cap_and_empty():
    files = [FakeUpload(f"f{i}.txt", b"hi") for i in range(MAX_FILES + 3)]
    assert len(read_uploads(files)) == MAX_FILES
    assert read_uploads([]) == []
    assert read_uploads(None) == []

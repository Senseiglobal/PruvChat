"""Safe URL retrieval with mocked network (no sockets in tests)."""
import socket

import pruvfetch.fetch as fetch_mod
from pruvfetch.fetch import fetch_url


def _public_dns(monkeypatch, mapping=None):
    mapping = mapping or {}
    def fake_getaddrinfo(host, port, type=None, *a, **k):
        ip = mapping.get(host, "93.184.216.34")  # public TEST-NET-ish
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


class FakeHeaders(dict):
    def get(self, key, default=""):
        return super().get(key, default)


class FakeResp:
    def __init__(self, body=b"", status=200, ctype="text/plain", location=""):
        self._body = body
        self.status = status
        self.headers = FakeHeaders({"Content-Type": ctype, "Location": location})

    def read(self, n=-1):
        chunk, self._body = self._body[:n], self._body[n:]
        return chunk


class FakeOpener:
    def __init__(self, script):
        self.script = list(script)
        self.addheaders = []

    def open(self, req, timeout=None):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_fetch_plain_text(monkeypatch):
    _public_dns(monkeypatch)
    monkeypatch.setattr(fetch_mod, "build_opener",
                        lambda *a: FakeOpener([FakeResp(b"hello world")]))
    r = fetch_url("https://example.com/doc.txt")
    assert r.text == "hello world" and r.status == 200 and r.warning == ""
    assert r.final_url == "https://example.com/doc.txt" and r.fetched_at


def test_fetch_html_strips_tags_and_scripts(monkeypatch):
    _public_dns(monkeypatch)
    html = b"<html><head><script>evil()</script></head><body><p>Visible</p></body></html>"
    monkeypatch.setattr(fetch_mod, "build_opener",
                        lambda *a: FakeOpener([FakeResp(html, ctype="text/html")]))
    r = fetch_url("https://example.com/page")
    assert "Visible" in r.text and "evil" not in r.text


def test_fetch_truncates_oversize(monkeypatch):
    _public_dns(monkeypatch)
    monkeypatch.setattr(fetch_mod, "build_opener",
                        lambda *a: FakeOpener([FakeResp(b"z" * (fetch_mod.FETCH_MAX_BYTES + 5))]))
    r = fetch_url("https://example.com/big")
    assert r.truncated is True and len(r.text.encode()) == fetch_mod.FETCH_MAX_BYTES


def test_fetch_blocks_private_dns(monkeypatch):
    _public_dns(monkeypatch, {"evil.example": "169.254.169.254"})
    monkeypatch.setattr(fetch_mod, "build_opener",
                        lambda *a: FakeOpener([FakeResp(b"x")]))
    r = fetch_url("https://evil.example/latest")
    assert r.text == "" and "non-public IP" in r.warning


def test_fetch_blocks_redirect_to_private(monkeypatch):
    _public_dns(monkeypatch, {"internal.example": "10.1.2.3"})
    red = fetch_mod._Redirected(302, "http://internal.example/secret")
    monkeypatch.setattr(fetch_mod, "build_opener", lambda *a: FakeOpener([red]))
    r = fetch_url("https://example.com/start")
    assert r.text == "" and "redirect blocked" in r.warning


def test_fetch_rejects_bad_scheme_port_and_type(monkeypatch):
    _public_dns(monkeypatch)
    assert "scheme" in fetch_url("ftp://example.com/x").warning
    assert "port" in fetch_url("https://example.com:8443/x").warning
    monkeypatch.setattr(fetch_mod, "build_opener",
                        lambda *a: FakeOpener([FakeResp(b"\x00", ctype="image/png")]))
    assert "content type" in fetch_url("https://example.com/i.png").warning


def test_fetch_network_error_never_raises(monkeypatch):
    _public_dns(monkeypatch)
    monkeypatch.setattr(fetch_mod, "build_opener",
                        lambda *a: FakeOpener([TimeoutError("slow")]))
    r = fetch_url("https://example.com/slow")
    assert r.text == "" and "request failed" in r.warning

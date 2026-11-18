"""Exercise real network boundaries without using actual authentication data."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
from threading import Thread

import pytest
import requests

from lyra.utils import download_file, redacted_download_url


@pytest.mark.parametrize("url", [
    "https://fixture-user:tiny@host.invalid/file.zip",
    "https://fixture-user@host.invalid/file.zip",
])
def test_userinfo_is_rejected_before_cache_or_network(tmp_path, monkeypatch, url):
    dest = tmp_path / "cached.zip"
    dest.write_bytes(b"already downloaded")
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("userinfo URL must not reach network"))
    with pytest.raises(ValueError) as result:
        download_file(url, dest)
    assert "fixture-user" not in str(result.value)
    assert "tiny" not in str(result.value)
    assert "host.invalid/file.zip" in str(result.value)


def test_authenticated_query_failure_is_redacted_in_logs_and_error(tmp_path, monkeypatch, caplog):
    url = "https://host.invalid/file.zip?path=models&token=fixture-secret-query"
    def fail(*a, **k):
        raise requests.Timeout(url)
    monkeypatch.setattr(requests, "get", fail)
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError) as result:
        download_file(url, tmp_path / "file.zip")
    assert "fixture-secret-query" not in caplog.text + str(result.value)
    assert "path=models" in str(result.value)
    assert "Timeout" in str(result.value)
    assert not (tmp_path / "file.zip").exists()


def test_discord_and_signed_asset_parameters_are_redacted():
    value = redacted_download_url("https://cdn.invalid/file.zip?hm=fixture-hmac&ex=1234&X-Amz-Signature=fixture-signature&path=img")
    assert "fixture-hmac" not in value and "fixture-signature" not in value
    assert "ex=1234" in value and "path=img" in value


@contextmanager
def local_download_server():
    requests_seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            requests_seen.append(self.path)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/data?path=images&signature=fixture-signature")
                self.end_headers()
            elif self.path == "/bad-redirect":
                self.send_response(302)
                self.send_header("Location", f"http://fixture-user:short@127.0.0.1:{self.server.server_port}/data")
                self.end_headers()
            elif self.path.startswith("/missing"):
                self.send_response(404)
                self.end_headers()
            else:
                body = b"public mod payload"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests_seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_real_redirect_download_and_credential_redirect_rejection(tmp_path):
    with local_download_server() as (base, seen):
        dest = tmp_path / "file.zip"
        assert download_file(base + "/redirect", dest, quiet=True) == dest
        assert dest.read_bytes() == b"public mod payload"
        assert len(seen) == 2
        seen.clear()
        with pytest.raises(ValueError) as result:
            download_file(base + "/bad-redirect", tmp_path / "bad.zip")
        assert seen == ["/bad-redirect"]
        assert "fixture-user" not in str(result.value)
        with pytest.raises(RuntimeError) as result:
            download_file(base + "/missing?token=fixture-private-token", tmp_path / "missing.zip")
        assert "HTTP 404" in str(result.value)
        assert "fixture-private-token" not in str(result.value)

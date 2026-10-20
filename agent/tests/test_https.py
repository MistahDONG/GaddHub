import hashlib
import logging
import ssl
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock

import pytest
import requests
import trustme
from gaddhub_agent.config import Settings
from gaddhub_agent.export import read_export
from gaddhub_agent.store import Store
from gaddhub_agent.sync import Engine, upload


@pytest.fixture
def https_server(tmp_path):
    ca = trustme.CA()
    cert = ca.issue_cert("localhost")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    cert.configure_cert(context)
    ca_path = tmp_path / "ca.pem"
    ca.cert_pem.write_to_path(ca_path)
    records = []
    response = [201, {}]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            records.append((self.path, dict(self.headers), body))
            self.send_response(response[0])
            for key, value in response[1].items():
                self.send_header(key, value)
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield (
            f"https://localhost:{server.server_port}/v1/sync/snapshots",
            ca_path,
            records,
            response,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def trust_test_ca(monkeypatch, ca_path):
    session_class = requests.Session

    def session():
        instance = session_class()
        instance.verify = str(ca_path)
        return instance

    monkeypatch.setattr("gaddhub_agent.sync.requests.Session", session)


def test_real_https_upload_and_contract(https_server, export_data, monkeypatch):
    url, ca_path, records, _ = https_server
    trust_test_ca(monkeypatch, ca_path)
    content_hash, payload = read_export(export_data)[0]
    result = upload(url, "shared-test-password", content_hash, payload)
    assert result.success
    path, headers, body = records[0]
    assert path == "/v1/sync/snapshots"
    assert headers["Authorization"] == "Bearer shared-test-password"
    assert headers["Idempotency-Key"] == hashlib.sha256(body).hexdigest()
    assert headers["Content-Type"] == "application/json"
    assert body == payload


def test_untrusted_certificate_is_rejected(https_server, export_data):
    url, _, records, _ = https_server
    result = upload(url, "secret", *read_export(export_data)[0])
    assert not result.success
    assert "TLS" in result.message
    assert records == []


def test_file_to_https_with_persistent_acknowledgement(
    https_server, export_data, tmp_path, monkeypatch, caplog
):
    caplog.set_level(logging.INFO, logger="gaddhub_agent")
    url, ca_path, records, _ = https_server
    trust_test_ca(monkeypatch, ca_path)
    source = tmp_path / "GuildSync.lua"
    source.write_bytes(export_data)
    settings = Settings(server_url=url, sources=[str(source)])
    database = tmp_path / "queue.sqlite3"
    store = Store(database)
    engine = Engine(settings, "test-password", store, lambda text: None)
    engine.tick()
    assert records == []
    engine.observed[str(source)].changed -= 3
    engine.tick()
    assert len(records) == 1
    assert store.status(url)[2] is not None
    assert 'Attempting to send snapshot from file "GuildSync.lua"' in caplog.text
    assert 'Success: snapshot from file "GuildSync.lua"' in caplog.text
    assert "HTTP 201" in caplog.text
    assert "test-password" not in caplog.text
    store.close()
    store = Store(database)
    engine = Engine(replace(settings), "test-password", store, lambda text: None)
    engine.tick()
    engine.observed[str(source)].changed -= 3
    engine.tick()
    assert len(records) == 1
    assert store.due(url) is None
    store.close()


@pytest.mark.parametrize(
    ("code", "permanent", "auth"),
    [
        (200, False, False),
        (204, False, False),
        (301, True, False),
        (302, True, False),
        (401, False, True),
        (403, False, True),
        (409, True, False),
        (422, True, False),
        (429, False, False),
        (503, False, False),
    ],
)
def test_http_status_and_no_redirects(
    https_server, export_data, monkeypatch, code, permanent, auth
):
    url, ca_path, records, response = https_server
    trust_test_ca(monkeypatch, ca_path)
    response[:] = [code, {"Location": url + "/redirect", "Retry-After": "120"}]
    result = upload(url, "secret", *read_export(export_data)[0])
    assert result.success == (code in (200, 204))
    assert result.permanent == permanent
    assert result.auth_error == auth
    assert len(records) == 1
    if code in (429, 503):
        assert result.retry_after == 120


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (requests.exceptions.ConnectionError("private-password"), "Connection failed"),
        (requests.exceptions.Timeout("private-password"), "Network timeout"),
        (requests.exceptions.SSLError("private-password"), "TLS certificate"),
        (requests.exceptions.RequestException("private-password"), "Network error"),
    ],
)
def test_network_failures_are_distinct_and_do_not_echo_exception_details(
    monkeypatch, export_data, error, message
):
    session = MagicMock()
    session.__enter__.return_value = session
    session.post.side_effect = error
    monkeypatch.setattr("gaddhub_agent.sync.requests.Session", lambda: session)
    result = upload(
        "https://example.invalid/upload", "private-password", *read_export(export_data)[0]
    )
    assert not result.success
    assert message in result.message
    assert "private-password" not in result.message

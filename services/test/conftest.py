"""
Shared test fixtures for ZZCC services test suite.
Provides:
- Mock NebulaGraph session (mock_nebula_session)
- Server base URL for integration tests
- test_space_name fixture

Run:
    # Unit tests (mocked NebulaGraph)
    pytest test/ -v -m "not integration"

    # Integration tests (against live server)
    pytest test/ -v -m integration
"""
import os
import json
import pytest
from unittest.mock import MagicMock
from contextlib import contextmanager


# ---------- Configuration ----------

SERVER_HOST = os.environ.get("ZZCC_SERVER_HOST", "124.223.47.167")
INTERFACE_PORT = os.environ.get("ZZCC_INTERFACE_PORT", "8001")
NEBULA_PORT = os.environ.get("ZZCC_NEBULA_PORT", "9669")
MATRIX_PORT = os.environ.get("ZZCC_MATRIX_PORT", "8008")
ELEMENT_PORT = os.environ.get("ZZCC_ELEMENT_PORT", "8080")

INTERFACE_BASE = f"http://{SERVER_HOST}:{INTERFACE_PORT}"
TEST_SPACE_PREFIX = "zzcc_test_"


# ---------- Mock fixtures ----------

@pytest.fixture
def mock_nebula_session():
    """Mock NebulaGraph session that simulates query responses.
    Compatible with both sync and async context manager entry.
    No real network calls are made."""
    session = MagicMock()
    session.execute.return_value.is_succeeded.return_value = True
    session.execute.return_value.error_msg.return_value = ""
    session.execute.return_value.keys.return_value = []
    session.execute.return_value.rows.return_value = []
    session.release = MagicMock()
    return session


@pytest.fixture
def test_space_name():
    """Generate a unique test space name for integration tests."""
    import time
    return f"{TEST_SPACE_PREFIX}{int(time.time())}"


# ---------- Integration test HTTP client ----------

@pytest.fixture
def api_client():
    """Simple HTTP client for integration tests against the live server.
    Use with `pytest -m integration` marker."""
    import urllib.request
    import urllib.error

    class SimpleHttpClient:
        def __init__(self, base_url):
            self.base_url = base_url

        def _do(self, method, path, data=None, headers=None, params=None):
            url = self.base_url + path
            if params:
                qs = "&".join(f"{k}={v}" for k, v in params.items())
                url = f"{url}?{qs}"
            hdrs = {"Content-Type": "application/json"}
            if headers:
                hdrs.update(headers)
            body = json.dumps(data).encode() if data else None
            req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.status, json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                rbody = e.read().decode()
                try:
                    return e.code, json.loads(rbody)
                except json.JSONDecodeError:
                    return e.code, rbody
            except urllib.error.URLError as e:
                return 0, str(e.reason)

        def get(self, path, params=None):
            return self._do("GET", path, params=params)

        def post(self, path, data=None):
            return self._do("POST", path, data=data)

        def delete(self, path, data=None):
            return self._do("DELETE", path, data=data)

        def patch(self, path, data=None):
            return self._do("PATCH", path, data=data)

        def post_with_retry(self, path, data=None, retries=3, delay=0.5):
            """POST with retry on SpaceNotFound (NebulaGraph metadata sync delay)."""
            import time
            for _ in range(retries):
                status, body = self.post(path, data)
                if status != 400 or "SpaceNotFound" not in str(body):
                    return status, body
                time.sleep(delay)
            return self.post(path, data)

    return SimpleHttpClient(INTERFACE_BASE)

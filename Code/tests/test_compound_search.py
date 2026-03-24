from pathlib import Path
import sys

import pytest
import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from report_generator import compound_search


class DummyResponse:
    def __init__(self, status_code=200, payload=None, url="https://commonchemistry.cas.org/api/search"):
        self.status_code = status_code
        self._payload = payload or {}
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} error",
                response=self,
            )

    def json(self):
        return self._payload


def test_cas_search_retries_on_timeout_and_succeeds(monkeypatch):
    monkeypatch.setattr(compound_search, "CAS_API", "test-api-key")
    monkeypatch.setattr(compound_search.time, "sleep", lambda _: None)

    calls = {"count": 0}

    def fake_get(url, headers, params, timeout):
        calls["count"] += 1
        assert timeout == compound_search.REQUEST_TIMEOUT
        assert headers["X-API-KEY"] == "test-api-key"
        assert params == {"q": "2-Thiopheneacetic acid"}
        if calls["count"] < 3:
            raise requests.exceptions.Timeout("timed out")
        return DummyResponse(payload={"results": [{"rn": "123-45-6"}]}, url=url)

    monkeypatch.setattr(compound_search.requests, "get", fake_get)

    result = compound_search.cas_search("2-Thiopheneacetic acid")

    assert result == {"results": [{"rn": "123-45-6"}]}
    assert calls["count"] == 3


def test_cas_detail_does_not_retry_non_retryable_http_error(monkeypatch):
    monkeypatch.setattr(compound_search, "CAS_API", "test-api-key")
    monkeypatch.setattr(compound_search.time, "sleep", lambda _: pytest.fail("sleep should not be called"))

    calls = {"count": 0}

    def fake_get(url, headers, params, timeout):
        calls["count"] += 1
        assert timeout == compound_search.REQUEST_TIMEOUT
        assert params == {"cas_rn": "123-45-6"}
        return DummyResponse(status_code=403, url=url)

    monkeypatch.setattr(compound_search.requests, "get", fake_get)

    result = compound_search.cas_detail("123-45-6")

    assert result is None
    assert calls["count"] == 1
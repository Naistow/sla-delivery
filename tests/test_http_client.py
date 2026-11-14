import pytest
import requests
from integration.domain import DirectoryError
from integration.http_client import DirectoryClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_retries_after_connection_error():
    session = FakeSession(
        requests.ConnectionError("down"),
        FakeResponse([{"code": "Z-CENTER", "sla_target_min": 45}]),
    )
    client = DirectoryClient("http://1c.local", session=session, sleep=lambda s: None)
    assert client.zones() == [{"code": "Z-CENTER", "sla_target_min": 45}]
    assert session.calls == 2


def test_raises_directory_error_after_all_retries():
    session = FakeSession(
        requests.Timeout("t1"),
        requests.Timeout("t2"),
        requests.Timeout("t3"),
    )
    client = DirectoryClient("http://1c.local", session=session, retries=3, sleep=lambda s: None)
    with pytest.raises(DirectoryError):
        client.zones()
    assert session.calls == 3

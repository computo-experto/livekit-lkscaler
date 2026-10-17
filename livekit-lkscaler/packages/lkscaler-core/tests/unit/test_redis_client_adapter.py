from __future__ import annotations

from typing import Any

import pytest
from lkscaler_core.redis import RedisClientAdapter


class StubRedis:
    """Mimics the redis-py calls the adapter makes, cursor protocol included."""

    def __init__(self, *, scan_pages: list[tuple[int, list[bytes | str]]] | None = None) -> None:
        self.values: dict[str, bytes] = {}
        self.calls: list[tuple[str, Any]] = []
        self.scan_pages = list(scan_pages or [(0, [])])
        self.closed = False
        self.pinged = False

    @classmethod
    def from_url(cls, url: str) -> StubRedis:
        instance = cls()
        instance.calls.append(("from_url", url))
        return instance

    def ping(self) -> bool:
        self.pinged = True
        return True

    def close(self) -> None:
        self.closed = True

    def set(
        self, key: str, value: bytes, nx: bool | None = None, px: int | None = None
    ) -> bool | None:
        self.calls.append(("set", (key, value, nx, px)))
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self.values.pop(key, None) is not None:
                removed += 1
        return removed

    def scan(self, cursor: int, match: str, count: int) -> tuple[int, list[bytes | str]]:
        _ = (cursor, match, count)
        return self.scan_pages.pop(0) if self.scan_pages else (0, [])


def _adapter(monkeypatch: pytest.MonkeyPatch) -> tuple[RedisClientAdapter, StubRedis]:
    holder: dict[str, StubRedis] = {}

    def factory(url: str) -> StubRedis:
        stub = StubRedis()
        stub.calls.append(("from_url", url))
        holder["stub"] = stub
        return stub

    monkeypatch.setattr("redis.Redis", type("Patched", (), {"from_url": staticmethod(factory)}))
    adapter = RedisClientAdapter(url="redis://cache:6379/0")
    adapter.connect()
    return adapter, holder["stub"]


def test_connect_builds_a_client_from_the_url_and_pings(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, stub = _adapter(monkeypatch)

    assert stub.calls[0] == ("from_url", "redis://cache:6379/0")
    assert stub.pinged is True
    assert adapter is not None


def test_close_is_idempotent_and_safe_before_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    RedisClientAdapter(url="redis://cache:6379/0").close()

    adapter, stub = _adapter(monkeypatch)
    adapter.close()
    adapter.close()

    assert stub.closed is True


def test_set_if_absent_reports_success_and_loses_the_race(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, stub = _adapter(monkeypatch)

    assert adapter.set_if_absent("k", b"first", ttl_ms=1500) is True
    assert adapter.set_if_absent("k", b"second", ttl_ms=1500) is False

    assert stub.calls[-1] == ("set", ("k", b"second", True, 1500))
    assert stub.values["k"] == b"first"


def test_set_value_passes_the_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, stub = _adapter(monkeypatch)

    adapter.set_value("k", b"payload", ttl_ms=30000)

    assert stub.calls[-1] == ("set", ("k", b"payload", None, 30000))


def test_get_value_returns_bytes_or_none(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, stub = _adapter(monkeypatch)
    stub.values["k"] = b"payload"

    assert adapter.get_value("k") == b"payload"
    assert adapter.get_value("missing") is None


def test_delete_counts_removed_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, stub = _adapter(monkeypatch)
    stub.values["a"] = b"1"

    assert adapter.delete("a", "b") == 1


def test_scan_keys_follows_the_cursor_and_decodes_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    holder: dict[str, StubRedis] = {}

    def factory(url: str) -> StubRedis:
        stub = StubRedis(scan_pages=[(7, [b"one", b"two"]), (0, [b"three"])])
        holder["stub"] = stub
        return stub

    monkeypatch.setattr("redis.Redis", type("Patched", (), {"from_url": staticmethod(factory)}))
    adapter = RedisClientAdapter(url="redis://cache:6379/0")
    adapter.connect()

    assert adapter.scan_keys("livekit-binpack:demo:pods:*") == ["one", "two", "three"]


def test_scan_keys_decodes_string_keys_too(monkeypatch: pytest.MonkeyPatch) -> None:
    holder: dict[str, StubRedis] = {}

    def factory(url: str) -> StubRedis:
        stub = StubRedis(scan_pages=[(0, ["plain"])])
        holder["stub"] = stub
        return stub

    monkeypatch.setattr("redis.Redis", type("Patched", (), {"from_url": staticmethod(factory)}))
    adapter = RedisClientAdapter(url="redis://cache:6379/0")
    adapter.connect()

    assert adapter.scan_keys("*") == ["plain"]

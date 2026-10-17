from __future__ import annotations

from typing import Any

import pytest
from kazoo.exceptions import NodeExistsError, NoNodeError
from lkscaler_core.zookeeper import KazooNodeClient


class StubKazooClient:
    """Mimics the kazoo calls the adapter makes, including its exception contract."""

    def __init__(self) -> None:
        self.nodes: dict[str, bytes] = {}
        self.created: list[tuple[str, bytes, bool, bool]] = []
        self.updated: list[tuple[str, bytes]] = []
        self.deleted: list[str] = []
        self.started_with: int | None = None
        self.stopped = False
        self.closed = False

    def start(self, timeout: int | None = None) -> None:
        self.started_with = timeout

    def create(
        self, path: str, data: bytes, ephemeral: bool = False, makepath: bool = False
    ) -> None:
        if path in self.nodes:
            raise NodeExistsError()
        self.nodes[path] = data
        self.created.append((path, data, ephemeral, makepath))

    def get(self, path: str) -> tuple[bytes, object]:
        if path not in self.nodes:
            raise NoNodeError()
        return self.nodes[path], object()

    def set(self, path: str, data: bytes) -> None:
        if path not in self.nodes:
            raise NoNodeError()
        self.nodes[path] = data
        self.updated.append((path, data))

    def delete(self, path: str) -> None:
        if path not in self.nodes:
            raise NoNodeError()
        del self.nodes[path]
        self.deleted.append(path)

    def get_children(self, path: str) -> list[str]:
        if path not in self.nodes:
            raise NoNodeError()
        prefix = f"{path}/"
        return sorted(
            {node[len(prefix) :].split("/", 1)[0] for node in self.nodes if node.startswith(prefix)}
        )

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


def _client() -> tuple[KazooNodeClient, StubKazooClient]:
    adapter = KazooNodeClient(hosts=["zk-1:2181", "zk-2:2181"])
    stub = StubKazooClient()
    adapter._client = stub
    return adapter, stub


def test_create_if_absent_reports_success_and_marks_the_node_ephemeral() -> None:
    adapter, stub = _client()

    assert adapter.create_if_absent("/a/b", b"payload", ephemeral=True) is True

    assert stub.created == [("/a/b", b"payload", True, True)]


def test_create_if_absent_reports_the_lost_race() -> None:
    adapter, stub = _client()
    stub.nodes["/a/b"] = b"first"

    assert adapter.create_if_absent("/a/b", b"second", ephemeral=True) is False
    assert stub.nodes["/a/b"] == b"first"


def test_upsert_creates_a_missing_node() -> None:
    adapter, stub = _client()

    adapter.upsert("/a/b", b"payload", ephemeral=True)

    assert stub.nodes == {"/a/b": b"payload"}
    assert stub.updated == []


def test_upsert_sets_an_existing_node() -> None:
    adapter, stub = _client()
    stub.nodes["/a/b"] = b"old"

    adapter.upsert("/a/b", b"new", ephemeral=True)

    assert stub.nodes["/a/b"] == b"new"
    assert stub.updated == [("/a/b", b"new")]


def test_read_returns_bytes_or_none() -> None:
    adapter, stub = _client()
    stub.nodes["/a/b"] = b"payload"

    assert adapter.read("/a/b") == b"payload"
    assert adapter.read("/missing") is None


def test_remove_is_idempotent() -> None:
    adapter, stub = _client()
    stub.nodes["/a/b"] = b"payload"

    adapter.remove("/a/b")
    adapter.remove("/a/b")

    assert stub.deleted == ["/a/b"]
    assert "/a/b" not in stub.nodes


def test_children_listed_and_missing_parent_treated_as_empty() -> None:
    adapter, stub = _client()
    stub.nodes["/a"] = b""
    stub.nodes["/a/one"] = b"1"
    stub.nodes["/a/two"] = b"2"
    stub.nodes["/a/two/nested"] = b"nested"

    assert adapter.children("/a") == ["one", "two"]
    assert adapter.children("/absent") == []


def test_start_builds_a_client_from_the_configured_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    built: dict[str, Any] = {}
    stub = StubKazooClient()

    def factory(**kwargs: Any) -> StubKazooClient:
        built.update(kwargs)
        return stub

    monkeypatch.setattr("kazoo.client.KazooClient", factory)
    adapter = KazooNodeClient(hosts=["zk-1:2181", "zk-2:2181"], session_timeout_sec=7)

    adapter.start()

    assert built == {"hosts": "zk-1:2181,zk-2:2181", "timeout": 7}
    assert stub.started_with == 7


def test_close_stops_and_closes_once() -> None:
    adapter, stub = _client()

    adapter.close()
    adapter.close()

    assert (stub.stopped, stub.closed) == (True, True)


def test_close_before_start_is_a_no_op() -> None:
    adapter = KazooNodeClient(hosts=["zk-1:2181"])

    adapter.close()

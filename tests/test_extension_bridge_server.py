"""extension_bridge_server の単体テスト（Listen 前後の notify 挙動）。"""

import asyncio
import socket
import threading
import time

import aiohttp

import extension_bridge_server as ebs
from extension_bridge_server import ExtensionBridgeServer, _normalize_room_id_for_sse


def test_format_listen_error_port_in_use_win() -> None:
    err = OSError("foo")
    err.winerror = 10048  # type: ignore[attr-defined]
    assert "ポートが使用中" in ExtensionBridgeServer._format_listen_error(err)


def test_format_listen_error_address_in_use_message() -> None:
    err = OSError("Address already in use")
    assert "ポートが使用中" in ExtensionBridgeServer._format_listen_error(err)


def test_format_listen_error_generic() -> None:
    err = OSError("weird")
    err.errno = 999  # type: ignore[attr-defined]
    msg = ExtensionBridgeServer._format_listen_error(err)
    assert "待受に失敗" in msg


def test_normalize_room_id_for_sse_strips_newlines() -> None:
    assert _normalize_room_id_for_sse("AB\nC\r12") == "ABC12"


def test_notify_room_id_ignores_blank_after_normalization() -> None:
    s = ExtensionBridgeServer()
    s.notify_room_id("  \n\r  ")
    assert s._last_confirmed_id is None  # noqa: SLF001


def test_notify_room_id_stores_last_before_listening() -> None:
    """待受完了前の notify でも直近 ID を保持し、後から接続したクライアントがリプレイ可能になる。"""
    s = ExtensionBridgeServer()
    assert s._last_confirmed_id is None  # noqa: SLF001 — テスト用に内部状態を確認

    s.notify_room_id("ABC12")

    assert s._last_confirmed_id == "ABC12"  # noqa: SLF001


def test_enqueue_sse_queue_coalesces_when_full() -> None:
    """遅いクライアント想定: 満杯時は最古を捨てて最新 ID を載せる。"""

    async def _run() -> None:
        q: asyncio.Queue = asyncio.Queue(maxsize=2)
        q.put_nowait("a")
        q.put_nowait("b")
        ExtensionBridgeServer._enqueue_sse_queue(q, "c")
        assert q.qsize() == 2
        first = await q.get()
        second = await q.get()
        assert {first, second} == {"b", "c"}

    asyncio.run(_run())


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_until(predicate, timeout_sec: float = 2.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_sse_replay_and_heartbeat(monkeypatch) -> None:
    monkeypatch.setattr(ebs, "SSE_HEARTBEAT_SEC", 0.05)
    server = ExtensionBridgeServer()
    port = _pick_free_port()
    ok = threading.Event()
    errs = []
    server.notify_room_id("A1B2C")
    server.start(
        port=port,
        on_listen_error=lambda msg: errs.append(msg),
        on_listen_ok=lambda: ok.set(),
    )
    assert ok.wait(2.0), "SSE server failed to listen in time"

    async def _run() -> None:
        timeout = aiohttp.ClientTimeout(total=2.0, sock_read=0.5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"http://127.0.0.1:{port}{ebs.SSE_PATH}") as resp:
                replay_line = (await resp.content.readline()).decode("utf-8")
                assert replay_line.startswith("data: A1B2C")
                _ = await resp.content.readline()  # event separator
                heartbeat_line = (await resp.content.readline()).decode("utf-8")
                assert heartbeat_line.startswith(": keep-alive")

    try:
        asyncio.run(_run())
    finally:
        server.stop()

    assert not errs


def test_stop_while_notifying_does_not_hang() -> None:
    server = ExtensionBridgeServer()
    port = _pick_free_port()
    ok = threading.Event()
    server.start(port=port, on_listen_error=lambda _m: None, on_listen_ok=lambda: ok.set())
    assert ok.wait(2.0), "SSE server failed to listen in time"
    assert _wait_until(lambda: server.is_listening_on(port), timeout_sec=1.0)

    keep_running = True

    def notifier() -> None:
        i = 0
        while keep_running:
            server.notify_room_id(f"A{i % 10}B{i % 10}C")
            i += 1

    th = threading.Thread(target=notifier, daemon=True)
    th.start()
    time.sleep(0.05)
    server.stop()
    keep_running = False
    th.join(timeout=1.0)
    assert not server.is_listening_on(port)

"""extension_bridge_server の単体テスト（Listen 前後の notify 挙動）。"""

import asyncio

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

"""
127.0.0.1 上の SSE（Server-Sent Events）で部屋IDを配信する拡張連携用サーバー。

OCR ワーカーの asyncio ループとは別スレッド・別イベントループで動作する。

Chrome 拡張側のパス・既定ポートは `chrome-extension/constants.js` の `SMASH_ARENA_BRIDGE` と一致させること。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable, Optional

from aiohttp import web

logger = logging.getLogger(__name__)

# クライアント・設計書・将来の Chrome 拡張で共有するパス（変更時は docs も更新）
SSE_PATH = "/events"

# GUI から `stop()` したときの `Thread.join` 上限。通常はイベントループ停止で数 ms〜数百 ms 程度。
STOP_JOIN_TIMEOUT_SEC = 4.0


def _normalize_room_id_for_sse(room_id: str) -> str:
    """SSE の `data:` 行を壊さないよう改行を除去（部屋IDは単行想定）。"""
    if not room_id:
        return ""
    return room_id.replace("\r", "").replace("\n", "").strip()


class ExtensionBridgeServer:
    """単一ポート・単一パス GET の SSE サーバー。ライブ配信は待受成功時のみ。直近 ID は常に保持。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # _client_queues の add / discard / clear / 再代入と _broadcast のスナップショットを直列化
        self._queues_lock = threading.Lock()
        self._last_confirmed_id: Optional[str] = None
        self._client_queues = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._shutdown_async: Optional[asyncio.Event] = None
        self._listening = False
        self._active_port: Optional[int] = None
        self._on_listen_error: Optional[Callable[[str], None]] = None
        self._on_listen_ok: Optional[Callable[[], None]] = None

    def is_listening_on(self, port: int) -> bool:
        """同一ポートで待受中なら True（冪等な sync 用）。"""
        with self._lock:
            return self._listening and self._active_port == port and self._thread is not None and self._thread.is_alive()

    def notify_room_id(self, room_id: str) -> None:
        """部屋ID確定を配信。待受前でも直近 ID は保持し、Listen 後の接続でリプレイ可能にする。

        待受に成功していない間はブロードキャストしない（OCR をブロックしない）。
        """
        safe = _normalize_room_id_for_sse(room_id)
        if not safe:
            logger.debug("拡張連携: 空の部屋IDのため notify をスキップしました")
            return
        with self._lock:
            self._last_confirmed_id = safe
            if not self._listening:
                return
            loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(self._broadcast, safe)
            except RuntimeError:
                # stop() 後や loop.close() 後に閉じたループへスケジュールすると発生しうる
                logger.debug(
                    "拡張連携: イベントループが終了済みのため notify のブロードキャストをスキップしました"
                )

    @staticmethod
    def _enqueue_sse_queue(q: asyncio.Queue, room_id: str) -> None:
        """遅いクライアントでも最新 ID を優先するため、満杯時は古い 1 件を捨てて再試行。"""
        try:
            q.put_nowait(room_id)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(room_id)
            except asyncio.QueueFull:
                logger.debug("拡張連携: SSE クライアントキューが連続で満杯のため通知を落としました")

    def _broadcast(self, room_id: str) -> None:
        with self._queues_lock:
            queues = list(self._client_queues)
        for q in queues:
            try:
                self._enqueue_sse_queue(q, room_id)
            except Exception:
                logger.debug("SSE クライアントキューへの追加をスキップしました", exc_info=True)

    def start(
        self,
        port: int,
        on_listen_error: Callable[[str], None],
        on_listen_ok: Optional[Callable[[], None]] = None,
    ) -> None:
        """待受を開始。既に同じポートで待受中なら何もしない。"""
        with self._lock:
            if self._listening and self._active_port == port and self._thread and self._thread.is_alive():
                return
        self.stop()
        self._on_listen_error = on_listen_error
        self._on_listen_ok = on_listen_ok
        t = threading.Thread(target=self._thread_main, args=(port,), name="ExtensionBridgeSSE", daemon=True)
        with self._lock:
            self._thread = t
            self._active_port = port
        t.start()

    def _thread_main(self, port: int) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop
        try:
            loop.run_until_complete(self._run(port))
        except Exception:
            logger.exception("拡張連携 SSE スレッドで未処理例外")
        finally:
            with self._lock:
                self._listening = False
                self._loop = None
                self._shutdown_async = None
            loop.close()

    async def _run(self, port: int) -> None:
        with self._queues_lock:
            self._client_queues = set()
        self._shutdown_async = asyncio.Event()

        async def handle_sse(request: web.Request) -> web.StreamResponse:
            resp = web.StreamResponse(
                status=200,
                reason="OK",
                headers={
                    "Content-Type": "text/event-stream; charset=utf-8",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                },
            )
            await resp.prepare(request)
            with self._lock:
                replay = self._last_confirmed_id
            if replay:
                await resp.write(f"data: {replay}\n\n".encode("utf-8"))
            q: asyncio.Queue = asyncio.Queue(maxsize=64)
            with self._queues_lock:
                self._client_queues.add(q)
            try:
                while True:
                    rid = await q.get()
                    try:
                        await resp.write(f"data: {rid}\n\n".encode("utf-8"))
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        break
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("SSE ストリーム終了", exc_info=True)
            finally:
                with self._queues_lock:
                    self._client_queues.discard(q)
            return resp

        async def handle_options(_request: web.Request) -> web.Response:
            return web.Response(
                status=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                },
            )

        app = web.Application()
        app.router.add_get(SSE_PATH, handle_sse)
        app.router.add_options(SSE_PATH, handle_options)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)
        try:
            await site.start()
        except OSError as e:
            logger.exception("拡張連携 SSE の待受に失敗しました (port=%s)", port)
            if self._on_listen_error:
                self._on_listen_error(self._format_listen_error(e))
            await runner.cleanup()
            with self._lock:
                self._listening = False
                self._active_port = None
                # 待受に一度も成功していないので、直近 ID のリプレイは行わない
                self._last_confirmed_id = None
            return

        with self._lock:
            self._listening = True
        ok_cb = self._on_listen_ok
        if ok_cb:
            try:
                ok_cb()
            except Exception:
                logger.debug("拡張連携: on_listen_ok で例外（無視）", exc_info=True)

        try:
            await self._shutdown_async.wait()
        finally:
            with self._lock:
                self._listening = False
            try:
                await site.stop()
            except Exception:
                logger.debug("TCPSite.stop で例外（無視）", exc_info=True)
            try:
                await runner.cleanup()
            except Exception:
                logger.debug("AppRunner.cleanup で例外（無視）", exc_info=True)
            with self._lock:
                self._active_port = None
                # Listen 終了後は古い部屋IDをリプレイしない（監視再開までの取り違い防止）
                self._last_confirmed_id = None
            with self._queues_lock:
                self._client_queues.clear()

    @staticmethod
    def _format_listen_error(e: OSError) -> str:
        msg = (e.strerror or str(e) or "").strip()
        if getattr(e, "winerror", None) == 10048:
            return "拡張連携: ポートが使用中です"
        if getattr(e, "errno", None) == 98:
            return "拡張連携: ポートが使用中です"
        if "address already in use" in msg.lower() or "既に使用" in msg:
            return "拡張連携: ポートが使用中です"
        return f"拡張連携: 待受に失敗 ({msg or 'OS エラー'})"

    def stop(self) -> None:
        """待受を終了し、スレッドが終わるまで待つ。"""
        loop: Optional[asyncio.AbstractEventLoop] = None
        ev: Optional[asyncio.Event] = None
        th: Optional[threading.Thread] = None
        with self._lock:
            loop = self._loop
            ev = self._shutdown_async
            th = self._thread
        if loop is not None and ev is not None and not ev.is_set():
            try:
                loop.call_soon_threadsafe(ev.set)
            except RuntimeError:
                pass
        if th is not None and th.is_alive():
            th.join(timeout=STOP_JOIN_TIMEOUT_SEC)
            if th.is_alive():
                logger.warning(
                    "拡張連携 SSE スレッドが %.1fs 以内に終了しませんでした。",
                    STOP_JOIN_TIMEOUT_SEC,
                )
        with self._lock:
            # start() が待機中に新スレッドへ差し替えた場合は、ここで消さない（孤児化・誤クリア防止）
            if self._thread is th:
                self._thread = None
                self._active_port = None
                self._listening = False
                self._loop = None

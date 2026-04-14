"""
Chrome 拡張向けローカル SSE (`ExtensionBridgeServer`) と GUI の接続・設定同期。
"""

from __future__ import annotations

import logging
import threading

import customtkinter as ctk
import tkinter as tk

from config_manager import DEFAULT_EXTENSION_BRIDGE_PORT

logger = logging.getLogger(__name__)


class ExtensionBridgeMixin:
    """`SmashArenaIDScannerApp` が提供する属性（config / worker / ウィジェット等）を前提にする。"""

    def _apply_extension_bridge_port_widgets_state(self) -> None:
        on = self._extension_bridge_enabled.get()
        gray = "gray50" if not on else None
        try:
            self.entry_extension_bridge_port.configure(state="normal" if on else "disabled")
            tc = gray or ("#d0d0d0" if ctk.get_appearance_mode() == "Dark" else "#333333")
            self.label_bridge_port.configure(text_color=tc)
        except tk.TclError:
            pass

    def _on_extension_bridge_switch_changed(self) -> None:
        self._apply_extension_bridge_port_widgets_state()
        self._save_config()

    def _on_extension_bridge_port_commit(self, _event=None) -> None:
        self._save_config()

    def _apply_extension_bridge_fields_from_ui(self) -> None:
        self.config.extension_bridge_enabled = self._extension_bridge_enabled.get()
        ebp = self._extension_bridge_port_str.get().strip()
        if ebp.isdigit():
            self.config.extension_bridge_port = int(ebp)
        else:
            self.config.extension_bridge_port = DEFAULT_EXTENSION_BRIDGE_PORT

    def _finalize_extension_bridge_after_save(self, prev_ext: tuple[bool, int]) -> None:
        self._extension_bridge_port_str.set(str(self.config.extension_bridge_port))
        if (self.config.extension_bridge_enabled, self.config.extension_bridge_port) != prev_ext:
            self._sync_extension_bridge_listen()

    def _on_extension_listen_error(self, message: str) -> None:
        def upd():
            self.label_status.configure(text=message, text_color="orange")

        self._dispatch_ui(upd)

    def _on_extension_listen_ok(self) -> None:
        """待受成功時にポート競合などの一時エラー表示を解消（監視中かつ連携 ON のときのみ）。"""

        def upd():
            if self._is_shutting_down:
                return
            if not self.config.extension_bridge_enabled:
                return
            if not self.worker or not self.worker.is_monitoring:
                return
            self.label_status.configure(
                text="👀 監視中... 部屋IDをスキャンしています", text_color="white"
            )

        self._dispatch_ui(upd)

    def _sync_extension_bridge_listen(self) -> None:
        if self._is_shutting_down:
            return
        with self._extension_bridge_sync_lock:
            want = bool(self.config.extension_bridge_enabled) and bool(
                self.worker and self.worker.is_monitoring
            )
            port = int(self.config.extension_bridge_port)
            if not want:
                self._extension_bridge.stop()
                return
            if self._extension_bridge.is_listening_on(port):
                return
            self._extension_bridge.start(
                port, self._on_extension_listen_error, self._on_extension_listen_ok
            )

    def _safe_on_confirmed_id_bridge(self, room_id: str) -> None:
        if self._is_shutting_down:
            return
        if not self.config.extension_bridge_enabled:
            return
        if not self.worker or not self.worker.is_monitoring:
            return
        try:
            self._extension_bridge.notify_room_id(room_id)
        except Exception:
            logger.exception("拡張連携: notify_room_id に失敗しました")

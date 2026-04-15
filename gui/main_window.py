"""
メインウィンドウ `SmashArenaIDScannerApp`。
レイアウトの一部は `gui.mixins` に分割。
"""

import logging
import os
import sys
import webbrowser
from pathlib import Path
import threading
import tkinter.font as tkfont
import winsound
from typing import Callable, Optional

import customtkinter as ctk
import pyperclip
import pystray
import tkinter as tk
from tkinter import messagebox

from config_manager import AppConfig, ConfigManager, DEFAULT_EXTENSION_BRIDGE_PORT
from extension_bridge_server import ExtensionBridgeServer
from gui.constants import (
    AUTO_START_INITIAL_DELAY_MS,
    AUTO_START_MAX_ATTEMPTS,
    AUTO_START_RETRY_INTERVAL_MS,
    BOTTOM_SEPARATOR_HEIGHT,
    BOTTOM_SEPARATOR_PADX,
    BOTTOM_SEPARATOR_PADY_BOTTOM,
    BOTTOM_SEPARATOR_PADY_TOP,
    FRAME_ID_OUTER_HEIGHT,
    HISTORY_BORDER,
    HISTORY_CORNER_RADIUS,
    HISTORY_FG,
    HISTORY_MENU_INNER_PAD,
    HISTORY_TEXT_PAD_LEFT,
    HISTORY_TEXT_PAD_RIGHT,
    HISTORY_GAP_TEXT_TO_CARET,
    HISTORY_CARET_CANVAS_W,
    HISTORY_TRIGGER_HEIGHT,
    HISTORY_TRIGGER_TEXT,
    ID_SIDE_RESERVE_FOR_LAMPS,
    LAMP_ID_OFF,
    LAMP_ID_ON,
    LAMP_LABEL_HIT_WIDTH,
    LAMP_ROOM_OFF,
    LAMP_ROOM_ON,
    RUN_CLUSTER_BTN_STATUS_GAP,
    RUN_SPACER_WEIGHT_BOTTOM,
    RUN_SPACER_WEIGHT_TOP,
    WINDOW_GEOMETRY_BOOTSTRAP,
    WORKER_JOIN_TIMEOUT_SEC,
)
from gui.mixins.connection import ConnectionLayoutMixin
from gui.mixins.extension_bridge import ExtensionBridgeMixin
from gui.mixins.history import HistoryMenuMixin
from gui.tooltip import ToolTip
from gui.tray import create_tray_image
from obs_capture import DEFAULT_PORT as DEFAULT_OBS_WEBSOCKET_PORT
from ocr_worker import OCRWorker

logger = logging.getLogger(__name__)


class SmashArenaIDScannerApp(ctk.CTk, ConnectionLayoutMixin, HistoryMenuMixin, ExtensionBridgeMixin):
    def __init__(self):
        super().__init__()
        self.withdraw()

        self.title("Smash Arena ID Scanner")
        self.geometry(WINDOW_GEOMETRY_BOOTSTRAP)
        self.resizable(False, False)

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.config: AppConfig = ConfigManager.load()
        self.worker: Optional[OCRWorker] = None
        self._tray_icon: Optional[pystray.Icon] = None
        self._is_shutting_down = False
        self._is_destroying = False

        self._recent_ids: list[str] = []
        self._current_id: str = "-----"
        self._history_font_measurer: Optional[tkfont.Font] = None
        self._history_trigger_width_cache: Optional[int] = None

        _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._base_path = getattr(sys, "_MEIPASS", _repo_root)

        base_family = "Yu Gothic UI"
        self.font_huge = ctk.CTkFont(family=base_family, size=38, weight="bold")
        self.font_heading = ctk.CTkFont(family=base_family, size=15, weight="bold")
        self.font_label = ctk.CTkFont(family=base_family, size=13, weight="bold")
        self.font_input = ctk.CTkFont(family=base_family, size=13, weight="normal")
        self.font_btn = ctk.CTkFont(family=base_family, size=14, weight="bold")
        self.font_status = ctk.CTkFont(family=base_family, size=13, weight="normal")
        self.font_small = ctk.CTkFont(family=base_family, size=11, weight="normal")

        self._sound_enabled = ctk.BooleanVar(value=self.config.sound_enabled)
        self._always_on_top = ctk.BooleanVar(value=self.config.always_on_top)
        self._auto_start = ctk.BooleanVar(value=self.config.auto_start)
        self._extension_bridge_enabled = ctk.BooleanVar(value=self.config.extension_bridge_enabled)
        self._extension_bridge_port_str = ctk.StringVar(value=str(self.config.extension_bridge_port))
        self._extension_bridge = ExtensionBridgeServer()
        self._extension_bridge_sync_lock = threading.Lock()

        self.attributes("-topmost", self.config.always_on_top)

        self._build_ui()
        self._apply_window_icon()
        self._setup_tray()

        self.protocol("WM_DELETE_WINDOW", self._request_shutdown)
        self.bind("<Unmap>", self._on_unmap)

        if self.config.auto_start:
            self.after(500, self._auto_start_sequence)

        self._history_menu_open = False
        self.after(80, self._layout_history_trigger)

        self.deiconify()

    def _auto_start_sequence(self):
        self._on_connect()
        attempt = [0]

        def _try_start():
            attempt[0] += 1
            if self.worker and self.worker.has_connected:
                self._on_toggle_monitor()
            elif attempt[0] < AUTO_START_MAX_ATTEMPTS:
                self.after(AUTO_START_RETRY_INTERVAL_MS, _try_start)

        self.after(AUTO_START_INITIAL_DELAY_MS, _try_start)

    def _build_ui(self):
        lamp_bg = self._get_bg_color()
        self.frame_lamps = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_lamps.place(x=10, y=8, anchor="nw")

        self.canvas_lamp_room = ctk.CTkCanvas(
            self.frame_lamps, width=14, height=14, bg=lamp_bg, highlightthickness=0
        )
        self.oval_lamp_room = self.canvas_lamp_room.create_oval(
            2, 2, 12, 12, fill=LAMP_ROOM_OFF, outline=""
        )
        self.canvas_lamp_room.grid(row=0, column=0, padx=(0, 4), pady=(0, 2), sticky="e")

        self.label_lamp_room = ctk.CTkLabel(
            self.frame_lamps,
            text="ROOM",
            font=self.font_small,
            text_color="#888888",
            anchor="w",
            width=LAMP_LABEL_HIT_WIDTH,
        )
        self.label_lamp_room.grid(row=0, column=1, padx=0, pady=(0, 2), sticky="w")

        self.canvas_lamp_id = ctk.CTkCanvas(
            self.frame_lamps, width=14, height=14, bg=lamp_bg, highlightthickness=0
        )
        self.oval_lamp_id = self.canvas_lamp_id.create_oval(
            2, 2, 12, 12, fill=LAMP_ID_OFF, outline=""
        )
        self.canvas_lamp_id.grid(row=1, column=0, padx=(0, 4), pady=0, sticky="e")

        self.label_lamp_id = ctk.CTkLabel(
            self.frame_lamps,
            text="ID",
            font=self.font_small,
            text_color="#888888",
            anchor="w",
            width=LAMP_LABEL_HIT_WIDTH,
        )
        self.label_lamp_id.grid(row=1, column=1, padx=0, pady=0, sticky="w")

        _tip_room = "専用部屋を検知"
        _tip_id = "部屋ID（5桁）を読み取り済み"
        ToolTip(self.canvas_lamp_room, _tip_room)
        ToolTip(self.label_lamp_room, _tip_room)
        ToolTip(self.canvas_lamp_id, _tip_id)
        ToolTip(self.label_lamp_id, _tip_id)

        frame_id = ctk.CTkFrame(self, fg_color="transparent", height=FRAME_ID_OUTER_HEIGHT)
        frame_id.pack(padx=20, pady=(5, 5), fill="x")
        frame_id.pack_propagate(False)
        self._frame_id_outer = frame_id

        frame_id_content = ctk.CTkFrame(frame_id, fg_color="transparent")
        frame_id_content.pack(
            fill="both",
            expand=True,
            padx=(ID_SIDE_RESERVE_FOR_LAMPS, ID_SIDE_RESERVE_FOR_LAMPS),
            pady=0,
        )

        self.btn_current_id = ctk.CTkButton(
            frame_id_content,
            text="-----",
            font=self.font_huge,
            fg_color="transparent",
            text_color="#00FF88",
            hover_color="#333333",
            cursor="hand2",
            command=self._on_click_current_id,
            height=55,
            border_spacing=0,
        )
        self.btn_current_id.place(relx=0.5, rely=0.45, anchor="center")

        self.label_id_hint = ctk.CTkLabel(
            frame_id_content,
            text="👆 クリックで再コピー",
            font=self.font_small,
            text_color="#888888",
        )
        self.label_id_hint.place(relx=0.5, rely=0.45, y=28, anchor="n")

        self.frame_dynamic = ctk.CTkFrame(self, fg_color="transparent")
        self._build_connection_cards()

        bg_run = self._get_bg_color()
        self.frame_run_middle = tk.Frame(
            self.frame_dynamic, bg=bg_run, highlightthickness=0
        )
        self.frame_run_middle.columnconfigure(0, weight=1)
        self.frame_run_spacer_top = tk.Frame(self.frame_run_middle, bg=bg_run, highlightthickness=0)
        self.frame_run_spacer_bottom = tk.Frame(self.frame_run_middle, bg=bg_run, highlightthickness=0)
        self.frame_run_cluster = ctk.CTkFrame(self.frame_run_middle, fg_color="transparent")

        self.frame_ctrl = ctk.CTkFrame(self.frame_run_cluster, fg_color="transparent", height=40)
        self.frame_ctrl.pack_propagate(False)

        self.btn_toggle = ctk.CTkButton(
            self.frame_ctrl,
            text="監視を開始",
            state="disabled",
            fg_color="#28a745",
            hover_color="#218838",
            command=self._on_toggle_monitor,
            font=self.font_btn,
            width=160,
            height=36,
        )
        self.btn_toggle.place(relx=0.5, rely=0.5, anchor="center")

        self.canvas_indicator = ctk.CTkCanvas(
            self.frame_ctrl, width=16, height=16, bg=self._get_bg_color(), highlightthickness=0
        )
        self.indicator_oval = self.canvas_indicator.create_oval(2, 2, 14, 14, fill="gray", outline="")
        self.canvas_indicator.place(relx=0.5, rely=0.5, x=-95, anchor="center")

        self.label_status = ctk.CTkLabel(
            self.frame_run_cluster,
            text="接続設定を入力して「OBS に接続」を押してください",
            text_color="gray",
            wraplength=360,
            font=self.font_status,
        )
        self.frame_ctrl.pack(fill="x", pady=(0, RUN_CLUSTER_BTN_STATUS_GAP))
        self.label_status.pack(fill="x", pady=(0, 0))
        self.frame_run_spacer_top.grid(row=0, column=0, sticky="nsew")
        self.frame_run_cluster.grid(row=1, column=0, sticky="ew")
        self.frame_run_spacer_bottom.grid(row=2, column=0, sticky="nsew")
        self.frame_run_middle.rowconfigure(0, weight=RUN_SPACER_WEIGHT_TOP)
        self.frame_run_middle.rowconfigure(1, weight=0, minsize=0)
        self.frame_run_middle.rowconfigure(2, weight=RUN_SPACER_WEIGHT_BOTTOM)

        self.frame_bottom_separator = ctk.CTkFrame(
            self,
            height=BOTTOM_SEPARATOR_HEIGHT,
            fg_color=self._get_bottom_separator_color(),
            corner_radius=0,
        )
        self.frame_bottom_separator.pack_propagate(False)

        self.frame_toggles = ctk.CTkFrame(self, fg_color="transparent")

        self.frame_toggles.columnconfigure(0, weight=1)
        self.frame_toggles.columnconfigure(1, weight=1)
        self.frame_toggles.columnconfigure(2, weight=1)

        chk_sound = ctk.CTkSwitch(
            self.frame_toggles, text="🔔 通知音", variable=self._sound_enabled, font=self.font_label, width=90
        )
        chk_sound.grid(row=0, column=0, padx=0, pady=2, sticky="w")

        chk_topmost = ctk.CTkSwitch(
            self.frame_toggles,
            text="📌 常に最前面",
            variable=self._always_on_top,
            font=self.font_label,
            width=110,
            command=self._on_topmost_changed,
        )
        chk_topmost.grid(row=0, column=1, padx=0, pady=2, sticky="w")

        self.chk_auto_start = ctk.CTkCheckBox(
            self.frame_toggles,
            text="⚡ 自動接続",
            variable=self._auto_start,
            font=self.font_label,
            text_color="gray",
            checkbox_width=16,
            checkbox_height=16,
            command=self._save_config,
        )
        self.chk_auto_start.grid(row=0, column=2, padx=0, pady=2, sticky="e")
        ToolTip(self.chk_auto_start, "アプリ起動時に自動で接続・監視を開始します")

        self.frame_arena_scan_row = ctk.CTkFrame(self, fg_color="transparent")

        _arena_logo = self._load_arena_scan_logo_ctk()
        _col = 0
        if _arena_logo is not None:
            self._arena_scan_logo_ctk = _arena_logo
            self.label_arena_scan_logo = ctk.CTkLabel(
                self.frame_arena_scan_row, image=_arena_logo, text=""
            )
            self.label_arena_scan_logo.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="w")
            ToolTip(self.label_arena_scan_logo, "Arena Scan（このアプリ）と Chrome 拡張をつなぎます")
            _col = 1

        self.chk_extension_bridge = ctk.CTkSwitch(
            self.frame_arena_scan_row,
            text="と連携",
            variable=self._extension_bridge_enabled,
            font=self.font_label,
            width=78,
            command=self._on_extension_bridge_switch_changed,
        )
        self.chk_extension_bridge.grid(row=0, column=_col, padx=(0, 6), pady=0, sticky="w")
        ToolTip(
            self.chk_extension_bridge,
            "ON のとき、監視中のみこの PC 内で Chrome 拡張とつながります（拡張の番号と同じにしてください）。OBS のポートとは別です。",
        )

        self.btn_extension_bridge_port = ctk.CTkButton(
            self.frame_arena_scan_row,
            text="⚙",
            width=34,
            height=28,
            font=self.font_btn,
            command=self._open_extension_bridge_port_modal,
        )
        self.btn_extension_bridge_port.grid(row=0, column=_col + 1, padx=(0, 0), pady=0, sticky="w")
        ToolTip(self.btn_extension_bridge_port, "連携ポートを変更（既定と同じ番号にそろえる）")
        self.frame_arena_scan_row.columnconfigure(_col + 2, weight=1)

        self._build_extension_bridge_port_modal()
        self._apply_extension_bridge_port_widgets_state()

        start_run = bool(self.config.auto_start and self.config.target_source.strip())
        self._apply_connection_layout("run" if start_run else "setup", skip_fit=True)

        self.frame_toggles.pack(side="bottom", fill="x", padx=20, pady=(0, 2))
        self.frame_bottom_separator.pack(
            side="bottom",
            fill="x",
            padx=BOTTOM_SEPARATOR_PADX,
            pady=(BOTTOM_SEPARATOR_PADY_TOP, BOTTOM_SEPARATOR_PADY_BOTTOM),
        )
        self.frame_arena_scan_row.pack(side="bottom", fill="x", padx=20, pady=(0, 6))
        self.frame_dynamic.pack(side="top", fill="both", expand=True, padx=20, pady=(0, 0))
        self.frame_bottom_separator.lift()
        self.frame_arena_scan_row.lift()
        self.frame_toggles.lift()
        self._frame_id_outer.lift()

        self.frame_history_trigger = ctk.CTkFrame(
            self,
            height=HISTORY_TRIGGER_HEIGHT,
            fg_color=HISTORY_FG,
            corner_radius=HISTORY_CORNER_RADIUS,
        )
        self.frame_history_trigger.place(relx=1.0, y=10, x=-12, anchor="ne")
        self.frame_history_trigger.pack_propagate(False)
        self.frame_history_trigger.lift()

        self.frame_lamps.lift()

        self.label_history = ctk.CTkLabel(
            self.frame_history_trigger,
            text="🕒 履歴",
            font=self.font_small,
            text_color=HISTORY_TRIGGER_TEXT,
            anchor="w",
        )
        self.label_history.pack(side="left", padx=(HISTORY_TEXT_PAD_LEFT, HISTORY_GAP_TEXT_TO_CARET))

        self.canvas_history_caret = ctk.CTkCanvas(
            self.frame_history_trigger,
            width=HISTORY_CARET_CANVAS_W,
            height=10,
            bg=HISTORY_FG,
            highlightthickness=0,
        )
        self.canvas_history_caret.pack(side="left", padx=(0, HISTORY_TEXT_PAD_RIGHT))
        self._draw_history_caret(False)

        for w in (
            self.frame_history_trigger,
            self.label_history,
            self.canvas_history_caret,
        ):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", self._toggle_history_menu, add="+")

        self.frame_history_menu = ctk.CTkFrame(
            self,
            fg_color=HISTORY_FG,
            corner_radius=HISTORY_CORNER_RADIUS,
            border_width=1,
            border_color=HISTORY_BORDER,
        )
        self.frame_history_menu_inner = ctk.CTkFrame(
            self.frame_history_menu, fg_color=HISTORY_FG, corner_radius=0
        )
        self.frame_history_menu_inner.pack(
            fill="x",
            expand=False,
            padx=HISTORY_MENU_INNER_PAD,
            pady=HISTORY_MENU_INNER_PAD,
        )
        self.frame_history_menu.pack_propagate(False)
        self.bind("<Button-1>", self._check_click_outside, add="+")

        self.update_idletasks()
        self._fixed_window_height = self._compute_fixed_window_height()
        self._fit_window_height_to_content()

    def _get_bg_color(self):
        mode = ctk.get_appearance_mode()
        return "#242424" if mode == "Dark" else "#ebebeb"

    def _get_bottom_separator_color(self) -> str:
        if ctk.get_appearance_mode() == "Dark":
            return HISTORY_BORDER
        return "#666666"

    def _load_arena_scan_logo_ctk(self):
        try:
            from PIL import Image

            path = os.path.join(self._base_path, "icons", "arena scan@128.png")
            if not os.path.isfile(path):
                return None
            pil = Image.open(path).convert("RGBA")
            pil = pil.resize((28, 28), Image.Resampling.LANCZOS)
            return ctk.CTkImage(light_image=pil, dark_image=pil, size=(28, 28))
        except Exception:
            logger.debug("Arena Scan ロゴの読み込みに失敗しました。", exc_info=True)
            return None

    def _build_extension_bridge_port_modal(self) -> None:
        self._extension_bridge_port_modal = ctk.CTkToplevel(self)
        self._extension_bridge_port_modal.withdraw()
        self._extension_bridge_port_modal.title("連携ポート")
        self._extension_bridge_port_modal.resizable(False, False)
        self._extension_bridge_port_modal.transient(self)
        self._extension_bridge_port_modal.protocol(
            "WM_DELETE_WINDOW", self._close_extension_bridge_port_modal
        )

        outer = ctk.CTkFrame(self._extension_bridge_port_modal, fg_color="transparent")
        outer.pack(padx=20, pady=16, fill="both", expand=True)

        self.label_bridge_port = ctk.CTkLabel(outer, text="連携ポート", font=self.font_label, anchor="w")
        self.label_bridge_port.pack(fill="x")

        self.entry_extension_bridge_port = ctk.CTkEntry(
            outer,
            textvariable=self._extension_bridge_port_str,
            width=140,
            font=self.font_input,
            justify="center",
        )
        self.entry_extension_bridge_port.pack(fill="x", pady=(6, 0))
        self.entry_extension_bridge_port.bind("<FocusOut>", self._on_extension_bridge_port_commit, add="+")
        self.entry_extension_bridge_port.bind("<Return>", self._on_extension_bridge_port_commit, add="+")

        self.label_extension_bridge_port_default = ctk.CTkLabel(
            outer,
            text=f"既定: {DEFAULT_EXTENSION_BRIDGE_PORT}",
            font=self.font_small,
            text_color="gray",
            anchor="w",
        )
        self.label_extension_bridge_port_default.pack(fill="x", pady=(8, 0))

        hint = ctk.CTkLabel(
            outer,
            text="Chrome 拡張の設定と同じ番号にしてください（OBS のポートとは別です）。",
            font=self.font_small,
            text_color="gray",
            wraplength=280,
            anchor="w",
            justify="left",
        )
        hint.pack(fill="x", pady=(6, 0))

        row = ctk.CTkFrame(outer, fg_color="transparent")
        row.pack(fill="x", pady=(14, 0))

        btn_readme = ctk.CTkButton(
            row,
            text="手順を見る（README）",
            font=self.font_small,
            width=160,
            command=self._open_extension_bridge_readme,
        )
        btn_readme.pack(side="left", padx=(0, 8))

        btn_close = ctk.CTkButton(
            row,
            text="閉じる",
            font=self.font_btn,
            width=100,
            command=self._close_extension_bridge_port_modal,
        )
        btn_close.pack(side="right")

    def _open_extension_bridge_readme(self) -> None:
        readme = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "chrome-extension",
            "README.md",
        )
        if os.path.isfile(readme):
            webbrowser.open(Path(readme).as_uri())
        else:
            messagebox.showinfo(
                "README",
                "chrome-extension フォルダ内の README.md が見つかりませんでした。",
                parent=self,
            )

    def _open_extension_bridge_port_modal(self) -> None:
        if self._is_shutting_down:
            return
        self._extension_bridge_port_modal.deiconify()
        self._extension_bridge_port_modal.lift()
        self._extension_bridge_port_modal.focus_force()
        try:
            self.entry_extension_bridge_port.focus_set()
        except tk.TclError:
            pass
        try:
            self._extension_bridge_port_modal.grab_set()
        except tk.TclError:
            pass

    def _close_extension_bridge_port_modal(self) -> None:
        self._on_extension_bridge_port_commit()
        try:
            self._extension_bridge_port_modal.grab_release()
        except tk.TclError:
            pass
        self._extension_bridge_port_modal.withdraw()

    def _on_topmost_changed(self):
        self.config.always_on_top = self._always_on_top.get()
        self.attributes("-topmost", self.config.always_on_top)
        self._save_config()

    def _flash_main_id(self):
        self.btn_current_id.configure(fg_color="#00FF88", text_color="#1a1a1a")
        self.canvas_indicator.itemconfig(self.indicator_oval, fill="#ffffff")

        def revert():
            self.btn_current_id.configure(fg_color="transparent", text_color="#00FF88")
            if self.worker and self.worker.is_monitoring:
                self.canvas_indicator.itemconfig(self.indicator_oval, fill="#ff4444")
            else:
                self.canvas_indicator.itemconfig(self.indicator_oval, fill="gray")

        self.after(500, revert)

    def _on_click_current_id(self):
        if self._current_id and self._current_id != "-----":
            pyperclip.copy(self._current_id)
            self.label_status.configure(text=f"手動コピー: {self._current_id}", text_color="#00FF88")
            self._flash_main_id()

    def _apply_window_icon(self) -> None:
        try:
            from PIL import Image, ImageTk

            path = os.path.join(self._base_path, "icons", "arena scan@128.png")
            if not os.path.isfile(path):
                return
            img = Image.open(path).convert("RGBA")
            img = img.resize((64, 64), Image.Resampling.LANCZOS)
            self._window_icon_photo = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._window_icon_photo)
        except Exception:
            logger.debug("ウィンドウアイコンを設定できませんでした。", exc_info=True)

    def _setup_tray(self):
        icon_img = create_tray_image(self._base_path)
        menu = pystray.Menu(
            pystray.MenuItem("開く", self._on_tray_open, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("終了", self._on_tray_exit),
        )
        self._tray_icon = pystray.Icon(
            "SmashArenaIDScanner", icon_img, "Smash Arena ID Scanner", menu
        )
        self._tray_icon.run_detached()

    def _on_unmap(self, event):
        try:
            if self.state() == "iconic":
                self.withdraw()
        except Exception:
            pass

    def _on_tray_open(self, icon=None, item=None):
        def _show():
            self.deiconify()
            self.lift()

        self.after(0, _show)

    def _on_tray_exit(self, icon=None, item=None):
        self._request_shutdown()

    def _request_shutdown(self):
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        try:
            self.after(0, self._full_destroy)
        except tk.TclError:
            self._full_destroy()

    def _dispatch_ui(self, fn: Callable[[], None]) -> None:
        if self._is_shutting_down:
            return
        try:
            self.after(0, fn)
        except tk.TclError:
            pass

    def _stop_worker(self, *, join_timeout: float = WORKER_JOIN_TIMEOUT_SEC) -> None:
        worker = self.worker
        self.worker = None
        if not worker:
            return
        try:
            worker.stop_worker()
        except Exception:
            logger.exception("worker.stop_worker() に失敗しました。")
        try:
            worker.join(timeout=join_timeout)
            if worker.is_alive():
                logger.warning("OCRWorker が終了待機 timeout 後も稼働中です。")
        except Exception:
            logger.exception("worker.join() に失敗しました。")

    def _full_destroy(self):
        if self._is_destroying:
            return
        self._is_destroying = True

        try:
            with self._extension_bridge_sync_lock:
                self._extension_bridge.stop()
        except Exception:
            logger.exception("拡張連携 SSE の stop() に失敗しました。")

        self._stop_worker(join_timeout=WORKER_JOIN_TIMEOUT_SEC)

        tray_icon = self._tray_icon
        self._tray_icon = None
        if tray_icon:
            try:
                tray_icon.stop()
            except Exception:
                logger.exception("tray_icon.stop() に失敗しました。")

        try:
            super().destroy()
        except tk.TclError:
            pass

    def _save_config(self):
        prev_ext = (self.config.extension_bridge_enabled, self.config.extension_bridge_port)
        self.config.host = self.entry_ip.get().strip()
        port_str = self.entry_port.get().strip()
        if port_str.isdigit():
            self.config.port = max(1, min(65535, int(port_str)))
        else:
            self.config.port = DEFAULT_OBS_WEBSOCKET_PORT
        self.config.password = self.entry_pass.get().strip()
        self.config.always_on_top = self._always_on_top.get()
        self.config.auto_start = self._auto_start.get()
        self.config.sound_enabled = self._sound_enabled.get()
        self._apply_extension_bridge_fields_from_ui()
        try:
            ConfigManager.save(self.config)
        except Exception as e:
            logger.exception("ConfigManager.save() に失敗しました。")
            self.label_status.configure(
                text=f"設定保存に失敗しました: {e}",
                text_color="orange",
            )
            return
        self._finalize_extension_bridge_after_save(prev_ext)

    def _resolve_template(self, name: str) -> Optional[str]:
        candidates = (
            os.path.join(self._base_path, name),
            os.path.join(self._base_path, "assets", "templates", name),
        )
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _on_connect(self):
        if self._is_shutting_down:
            return
        self._save_config()
        self._set_setup_status_notice("")
        self.btn_connect.configure(state="disabled", text="接続中...")
        self.btn_toggle.configure(
            state="disabled",
            text="監視を開始",
            fg_color="#28a745",
            hover_color="#218838",
        )
        self.canvas_indicator.itemconfig(self.indicator_oval, fill="gray")
        self.combo_source.configure(state="disabled", values=[])
        self.label_status.configure(text="接続しています...", text_color="gray")

        self._stop_worker(join_timeout=WORKER_JOIN_TIMEOUT_SEC)

        self.worker = OCRWorker(
            config=self.config,
            on_status=self._safe_update_status,
            on_sources=self._safe_update_sources,
            on_id_found=self._safe_on_id_found,
            on_disconnected=self._safe_on_disconnected,
            template_1080p=self._resolve_template("arenahere.png"),
            template_720p=self._resolve_template("arenahere_720p.png"),
            on_detection_lamps=self._safe_update_detection_lamps,
            on_confirmed_id_bridge=self._safe_on_confirmed_id_bridge,
        )
        self.worker.start()

    def _on_source_select(self, choice: str):
        self.config.target_source = choice
        ConfigManager.save(self.config)

    def _on_toggle_monitor(self):
        if not self.worker or not self.worker.has_connected:
            return

        if not self.worker.is_monitoring:
            selected = self.combo_source.get()
            if not selected:
                self.label_status.configure(
                    text="エラー: 対象ソースを選択してください。", text_color="orange"
                )
                return
            self.config.target_source = selected
            self.worker.is_monitoring = True
            self.btn_toggle.configure(text="監視を停止", fg_color="#dc3545", hover_color="#c82333")
            self.canvas_indicator.itemconfig(self.indicator_oval, fill="#ff4444")
            self.label_status.configure(
                text="👀 監視中... 部屋IDをスキャンしています", text_color="white"
            )
            self._sync_extension_bridge_listen()
        else:
            self.worker.is_monitoring = False
            self.btn_toggle.configure(text="監視を開始", fg_color="#28a745", hover_color="#218838")
            self.canvas_indicator.itemconfig(self.indicator_oval, fill="gray")
            self.label_status.configure(text="監視を停止しました。", text_color="gray")
            self._sync_extension_bridge_listen()

    def _safe_update_detection_lamps(self, room: bool, id_ok: bool) -> None:
        def upd():
            self.canvas_lamp_room.itemconfig(
                self.oval_lamp_room, fill=LAMP_ROOM_ON if room else LAMP_ROOM_OFF
            )
            self.canvas_lamp_id.itemconfig(
                self.oval_lamp_id, fill=LAMP_ID_ON if id_ok else LAMP_ID_OFF
            )

        self._dispatch_ui(upd)

    def _safe_update_status(self, text: str):
        color = "#ff6b6b" if "エラー" in text else ("#cccccc" if "停止" in text or "接続中" in text else "white")

        def upd():
            self.label_status.configure(text=text, text_color=color)
            if self._connection_layout_mode == "setup" and "エラー" in text:
                try:
                    if self.winfo_exists():
                        messagebox.showerror("接続エラー", text, parent=self)
                except tk.TclError:
                    pass

        self._dispatch_ui(upd)

    def _safe_update_sources(self, sources: list[str]):
        def update():
            self._set_setup_status_notice("")
            self.btn_connect.configure(state="normal", text="再接続")
            self.combo_source.configure(state="normal", values=sources)
            if self.config.target_source in sources:
                self.combo_source.set(self.config.target_source)
            elif sources:
                self.combo_source.set(sources[0])
                self.config.target_source = sources[0]
            self.btn_toggle.configure(
                state="normal",
                text="監視を開始",
                fg_color="#28a745",
                hover_color="#218838",
            )
            self.canvas_indicator.itemconfig(self.indicator_oval, fill="gray")
            self.label_status.configure(
                text="✅ 接続完了！「監視を開始」を押してください。",
                text_color="white",
            )
            self._apply_connection_layout("run")

        self._dispatch_ui(update)

    def _safe_on_id_found(self, room_id: str):
        def notify():
            if self._current_id != "-----" and self._current_id != room_id:
                if self._current_id not in self._recent_ids:
                    self._recent_ids.insert(0, self._current_id)
                    if len(self._recent_ids) > 5:
                        self._recent_ids.pop()

            self._current_id = room_id
            self.btn_current_id.configure(text=room_id)
            self._layout_history_trigger()

            self.label_status.configure(
                text=f"🎯 ID: {room_id} をコピーしました！", text_color="#00FF88"
            )
            self._flash_main_id()

            if self._sound_enabled.get():
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)

        self._dispatch_ui(notify)

    def _safe_on_disconnected(self):
        def reset():
            disconnected_text = "OBS との接続が切れました。再接続してください。"
            self.btn_connect.configure(state="normal", text="再接続")
            self.combo_source.configure(state="disabled", values=[])
            self.btn_toggle.configure(
                state="disabled",
                text="監視を開始",
                fg_color="#28a745",
                hover_color="#218838",
            )
            self.canvas_indicator.itemconfig(self.indicator_oval, fill="gray")
            self.label_status.configure(
                text=disconnected_text, text_color="orange"
            )
            if self.worker:
                self.worker.is_monitoring = False
                self.worker.has_connected = False
            self.canvas_lamp_room.itemconfig(self.oval_lamp_room, fill=LAMP_ROOM_OFF)
            self.canvas_lamp_id.itemconfig(self.oval_lamp_id, fill=LAMP_ID_OFF)
            self._apply_connection_layout("setup")
            self._set_setup_status_notice(disconnected_text, "orange")
            self._sync_extension_bridge_listen()

        self._dispatch_ui(reset)

    def destroy(self):
        self._request_shutdown()


if __name__ == "__main__":
    app = SmashArenaIDScannerApp()
    app.mainloop()

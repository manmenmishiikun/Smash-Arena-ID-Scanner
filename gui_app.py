"""
gui_app.py
Smash Arena ID Scanner - メインGUIアプリケーション

機能:
  - OBS WebSocket v5 とのリアルタイム連携
  - 部屋ID自動検出 → クリップボード自動コピー（同一IDの再通知抑制・任意でWin+V履歴から旧ID削除）
  - 検知ランプ・履歴ドロップダウン
  - 通知音オン/オフ切替（設定を起動間も保持）
  - システムトレイ連携（最小化ボタンでトレイに格納、×ボタンで終了）
  - OBS 接続設定・対象ソースの独立角丸カードと setup/run レイアウト切替（瞬時）
  - システム標準の美しいフォント（Yu Gothic UI等）を使用
"""

import logging
import os
import sys
import tkinter.font as tkfont
import winsound
from typing import Callable, Optional

import customtkinter as ctk
import pyperclip
import pystray
from PIL import Image, ImageDraw
import tkinter as tk
from tkinter import messagebox

from clipboard_history_win import try_remove_text_from_clipboard_history
from config_manager import ConfigManager, AppConfig
from ocr_worker import OCRWorker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 幅は固定。縦は起動時に状態A/Bの要請高さの max を `_fixed_window_height` に保存し、切替時も `_fit_window_height_to_content` で同じ高さを維持する
WINDOW_WIDTH = 400
WINDOW_GEOMETRY_BOOTSTRAP = f"{WINDOW_WIDTH}x420"

# 検知ランプ（Room=arenahere テンプレ一致、ID=5桁部屋IDを読取）
LAMP_ROOM_ON = "#1EBFE5"
LAMP_ROOM_OFF = "#2A4F58"
LAMP_ID_ON = "#12FF88"
LAMP_ID_OFF = "#2A4035"

# 履歴ドロップダウン（対象ソースのコンボボックスと揃える見た目トークン）
HISTORY_CORNER_RADIUS = 6
HISTORY_TRIGGER_HEIGHT = 28
HISTORY_TEXT_PAD_LEFT = 8
HISTORY_TEXT_PAD_RIGHT = 6
HISTORY_GAP_TEXT_TO_CARET = 4
HISTORY_CARET_CANVAS_W = 12
HISTORY_MIN_TRIGGER_WIDTH = 68
HISTORY_MENU_INNER_PAD = 3
HISTORY_ITEM_HEIGHT = 20
HISTORY_FG = "#333333"
# トリガー上の「🕒 履歴」ラベルとキャンバス描画キャレットで同じ色（キャレットだけ明るくならないよう揃える）
HISTORY_TRIGGER_TEXT = "#9a9a9a"
# キャレット領域もトリガー本体と同色（視覚的優先度を下げ、アフォーダンスは形状で示す）
HISTORY_BORDER = "#555555"
HISTORY_HOVER = "#444444"
# 履歴トリガーは place(..., x=-12) で右端からの余白。メニューも同じ基準でクランプする
HISTORY_WINDOW_EDGE_RIGHT = 12
HISTORY_WINDOW_EDGE_LEFT = 8

# 検知ランプ列と巨大ID（緑ハイライト含む）の横方向の重なりを避けるための左右取り（frame_id 内 px・対称でウィンドウ中央と一致させる）
# 2行（ROOM / ID 縦積み）で横幅が抑えられる分、やや狭められる
ID_SIDE_RESERVE_FOR_LAMPS = 88
# ROOM / ID ラベル列の最小幅（ツールチップの当たり判定幅を揃える）
LAMP_LABEL_HIT_WIDTH = 52

# OBS 接続設定 / 対象ソース（独立角丸カード・レイアウト切替）
CONNECTION_CARD_CORNER_RADIUS = 8
CONNECTION_HEADER_ROW_HEIGHT = 32
# カードまわりの統一余白（状態B「対象ソース」下の狭い余白 +1px を基準に全体へ）
CONNECTION_CARD_UNIFORM_PAD = 2
CONNECTION_HEADER_PADY = CONNECTION_CARD_UNIFORM_PAD
# 角丸枠と子の間に取るインセット（底に full-width の子を置くと角が潰れて見えるためフットは使わない）
CONNECTION_CARD_INSET = CONNECTION_CARD_UNIFORM_PAD
CONNECTION_BODY_PACK_PAD_BOTTOM = CONNECTION_CARD_UNIFORM_PAD
# OBS フォーム行間（状態Aの入力行のすき間）
CONNECTION_ROW_PADY = 1
# 再接続ボタン：最終入力行との距離をやや広げる（上, 下）
CONNECTION_BTN_CONNECT_PADY = (4, CONNECTION_CARD_UNIFORM_PAD)
CONNECTION_COMBO_PADY = (0, CONNECTION_CARD_UNIFORM_PAD + 2)
# 状態A/B とも 2 カードの間のすき間（OBS 直下 pady / 状態B のソース上 pady）
CONNECTION_CARD_PEER_GAP = 5
# 状態B: frame_run_middle の grid 余白（計測で上側が不足していたため上+2px）
RUN_MIDDLE_GRID_PADY = (4, 1)
# 状態B: 監視クラスタの上下スペーサーに割り当てる縦の重み（上>下で、区切り線をウィジェット座標より下にあるとみなして帯の縦中央に近づける）
RUN_SPACER_WEIGHT_TOP = 8
RUN_SPACER_WEIGHT_BOTTOM = 3
# 状態B: 監視ボタン行とステータス行の間（frame_ctrl の下側 pady）
RUN_CLUSTER_BTN_STATUS_GAP = 6
CONNECTION_CARET_W = 14
CONNECTION_CARET_H = 12
CONNECTION_CARET_COLOR = "#b0b0b0"
# カードヘッダ左のキャレット位置（タイトルはカード幅中央に place）
HEADER_CARET_PAD_X = 8

# 巨大ID行の固定高（ヒント「クリックで再コピー」が下端で切れないよう余裕を確保）
FRAME_ID_OUTER_HEIGHT = 100

# 下端トグル帯の上に引く区切り線（ウィンドウ端からインデント）
BOTTOM_SEPARATOR_PADX = 28
BOTTOM_SEPARATOR_PADY_TOP = 5
BOTTOM_SEPARATOR_PADY_BOTTOM = 3
# 1px だと DPI によっては消えるため 2px。色は履歴テキストに近いグレー
BOTTOM_SEPARATOR_HEIGHT = 2


# ---------------------------------------------------------------------------
# ツールチップウィジェット
# ---------------------------------------------------------------------------

class ToolTip:
    """tkinter ウィジェットにホバー時の説明テキストを表示するプレーンツールチップ。"""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tw: Optional[tk.Toplevel] = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_attributes("-topmost", True)  # 親が最前面のとき隠れないようにする
        
        label = tk.Label(
            self.tw, text=self.text,
            background="#333333", foreground="white",
            relief="solid", borderwidth=1,
            font=("Yu Gothic UI", 9), padx=6, pady=3,
        )
        label.pack()
        
        self.tw.update_idletasks()
        tw_width = self.tw.winfo_reqwidth()
        
        # ウインドウの右端（パディング20px考慮）に合わせてはみ出しを防ぐ
        master = self.widget.winfo_toplevel()
        max_x = master.winfo_rootx() + master.winfo_width() - 20
        if x + tw_width > max_x:
            x = max_x - tw_width
            
        self.tw.wm_geometry(f"+{x}+{y}")

    def leave(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None


# ---------------------------------------------------------------------------
# システムトレイアイコン生成
# ---------------------------------------------------------------------------

def _create_tray_image() -> Image.Image:
    """シンプルなシステムトレイアイコン画像を生成する。"""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, size - 2, size - 2], fill=(50, 130, 220, 255))
    d.text((12, 18), "SA", fill="white")
    return img


# ---------------------------------------------------------------------------
# メイン GUI アプリケーション
# ---------------------------------------------------------------------------

class SmashArenaIDScannerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        # レイアウト確定・縦幅スナップまで非表示にし、デフォルト寸法や暫定高さの一瞬の表示を防ぐ
        self.withdraw()

        self.title("Smash Arena ID Scanner")
        self.geometry(WINDOW_GEOMETRY_BOOTSTRAP)
        self.resizable(False, False)

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.config = ConfigManager.load()
        self.worker: Optional[OCRWorker] = None
        self._tray_icon: Optional[pystray.Icon] = None
        self._is_shutting_down = False
        self._is_destroying = False

        self._recent_ids: list[str] = []
        self._current_id: str = "-----"
        self._history_font_measurer: Optional[tkfont.Font] = None
        self._history_trigger_width_cache: Optional[int] = None

        self._base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

        # ---------------------------------------------------------
        # フォント設定:
        # メリハリをつけて美しくするため、システム標準の見やすいゴシック体を使用。
        # ---------------------------------------------------------
        base_family = "Yu Gothic UI"
        self.font_huge    = ctk.CTkFont(family=base_family, size=38, weight="bold")
        self.font_heading = ctk.CTkFont(family=base_family, size=15, weight="bold")
        self.font_label   = ctk.CTkFont(family=base_family, size=13, weight="bold")
        self.font_input   = ctk.CTkFont(family=base_family, size=13, weight="normal")
        self.font_btn     = ctk.CTkFont(family=base_family, size=14, weight="bold")
        self.font_status  = ctk.CTkFont(family=base_family, size=13, weight="normal")
        self.font_small   = ctk.CTkFont(family=base_family, size=11, weight="normal")

        # ── BooleanVar は_build_ui()より前に必ず初期化する──
        # _build_ui()内で使用するため、呼び出し前に定義しておく必要がある。
        self._sound_enabled = ctk.BooleanVar(value=self.config.sound_enabled)  # 設定ファイルから復元
        self._always_on_top = ctk.BooleanVar(value=self.config.always_on_top)
        self._auto_start    = ctk.BooleanVar(value=self.config.auto_start)

        self.attributes("-topmost", self.config.always_on_top)

        self._build_ui()
        self._setup_tray()

        self.protocol("WM_DELETE_WINDOW", self._request_shutdown)
        self.bind("<Unmap>", self._on_unmap)

        if self.config.auto_start:
            self.after(500, self._auto_start_sequence)

        self._history_menu_open = False
        self.after(80, self._layout_history_trigger)

        self.deiconify()

    def _measure_history_text(self, text: str) -> int:
        """履歴メニュー用フォントでテキスト幅を測る。"""
        if self._history_font_measurer is None:
            try:
                self._history_font_measurer = tkfont.Font(
                    family=self.font_small.cget("family") or "Yu Gothic UI",
                    size=-abs(int(self.font_small.cget("size") or 11)),
                )
            except Exception:
                self._history_font_measurer = tkfont.Font(family="Yu Gothic UI", size=-11)
        return self._history_font_measurer.measure(text)

    def _compute_history_trigger_width(self) -> int:
        """トリガー・履歴メニュー共通の最小幅（内容に合わせて詰める）。"""
        candidates = ["🕒 履歴", "履歴なし"] + list(self._recent_ids)
        max_tw = max(self._measure_history_text(s) for s in candidates) if candidates else self._measure_history_text("🕒 履歴")
        w = (
            HISTORY_TEXT_PAD_LEFT
            + max_tw
            + HISTORY_GAP_TEXT_TO_CARET
            + HISTORY_CARET_CANVAS_W
            + HISTORY_TEXT_PAD_RIGHT
        )
        return max(HISTORY_MIN_TRIGGER_WIDTH, w)

    def _layout_history_trigger(self) -> None:
        """履歴トリガー幅を内容に合わせて更新する。"""
        w = self._compute_history_trigger_width()
        if w != self._history_trigger_width_cache:
            self._history_trigger_width_cache = w
            self.frame_history_trigger.configure(width=w)
            self.frame_history_trigger.update_idletasks()

    def _draw_history_caret(self, open_menu: bool) -> None:
        """コンボボックス風のキャレット（開閉で向きを反転）。"""
        self.canvas_history_caret.delete("all")
        self.canvas_history_caret.configure(bg=HISTORY_FG)
        # 下向きシェブロン / 上向きシェブロン（12x10 キャンバス中央付近）
        if open_menu:
            self.canvas_history_caret.create_line(
                2, 7, 6, 3, 10, 7,
                fill=HISTORY_TRIGGER_TEXT,
                width=2,
                capstyle="round",
                joinstyle="round",
            )
        else:
            self.canvas_history_caret.create_line(
                2, 3, 6, 7, 10, 3,
                fill=HISTORY_TRIGGER_TEXT,
                width=2,
                capstyle="round",
                joinstyle="round",
            )

    def _auto_start_sequence(self):
        """起動時自動接続→自動監視開始。最大60回（30秒）試行してあきらめる。"""
        self._on_connect()
        attempt = [0]
        def _try_start():
            attempt[0] += 1
            if self.worker and self.worker.has_connected:
                self._on_toggle_monitor()
            elif attempt[0] < 60:
                self.after(500, _try_start)
        self.after(1000, _try_start)

    def _build_ui(self):
        # ── 検知ランプ（左上）──
        lamp_bg = self._get_bg_color()
        self.frame_lamps = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_lamps.place(x=10, y=8, anchor="nw")

        # 上段: ROOM 灯 + ラベル / 下段: ID 灯 + ラベル（横幅を抑える）
        self.canvas_lamp_room = ctk.CTkCanvas(
            self.frame_lamps, width=14, height=14, bg=lamp_bg, highlightthickness=0
        )
        self.oval_lamp_room = self.canvas_lamp_room.create_oval(
            2, 2, 12, 12, fill=LAMP_ROOM_OFF, outline=""
        )
        # sticky: e / w だけにすると、行の高さ内で縦方向は中央寄せになる（nw だと上寄せでズレる）
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

        # ── 巨大なID表示エリア ──
        # 固定高フレームを作り、そのド真ん中付近(rely=0.45)に巨大IDを「絶対配置」する。
        # 補助テキストはその下にぶら下げるように place() することで、巨大IDの重心を一切妨害しない。
        frame_id = ctk.CTkFrame(self, fg_color="transparent", height=FRAME_ID_OUTER_HEIGHT)
        frame_id.pack(padx=20, pady=(5, 5), fill="x")
        frame_id.pack_propagate(False)
        self._frame_id_outer = frame_id

        # ランプ列と重ならないよう左右を同じ幅だけ空け、中央寄せはその内側で行う（片側だけだと画面中央からずれる）
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
            cursor="hand2",  # クリックできることをアピール
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

        # ── 動的中間エリア（OBS/ソース/監視・ステータス。下端トグルとは pack で分離）──
        self.frame_dynamic = ctk.CTkFrame(self, fg_color="transparent")
        self._build_connection_cards()

        # ── コントロール（状態B：cluster を上下スペーサーで縦寄せ。区切り線は数値上より下に見えやすいので上側に多めに余白を割り当てる）──
        bg_run = self._get_bg_color()
        self.frame_run_middle = tk.Frame(
            self.frame_dynamic, bg=bg_run, highlightthickness=0
        )
        self.frame_run_middle.columnconfigure(0, weight=1)
        self.frame_run_spacer_top = tk.Frame(self.frame_run_middle, bg=bg_run, highlightthickness=0)
        self.frame_run_spacer_bottom = tk.Frame(self.frame_run_middle, bg=bg_run, highlightthickness=0)
        self.frame_run_cluster = ctk.CTkFrame(self.frame_run_middle, fg_color="transparent")

        self.frame_ctrl = ctk.CTkFrame(self.frame_run_cluster, fg_color="transparent", height=40)
        self.frame_ctrl.pack_propagate(False)  # height=40 を維持するため

        self.btn_toggle = ctk.CTkButton(
            self.frame_ctrl, text="監視を開始", state="disabled",
            fg_color="#28a745", hover_color="#218838",
            command=self._on_toggle_monitor,
            font=self.font_btn, width=160, height=36
        )
        # ボタンをフレームの完全な中央に配置（上の再接続ボタンと縦に一致する）
        self.btn_toggle.place(relx=0.5, rely=0.5, anchor="center")

        # ステータスインジケーター（ボタンのすぐ左に配置）
        self.canvas_indicator = ctk.CTkCanvas(self.frame_ctrl, width=16, height=16, bg=self._get_bg_color(), highlightthickness=0)
        self.indicator_oval = self.canvas_indicator.create_oval(2, 2, 14, 14, fill="gray", outline="")
        # relx=0.5(中央) から x=-95 で左にずらす (160/2 + 余白)
        self.canvas_indicator.place(relx=0.5, rely=0.5, x=-95, anchor="center")

        self.label_status = ctk.CTkLabel(
            self.frame_run_cluster,
            text="接続設定を入力して「OBS に接続」を押してください",
            text_color="gray", wraplength=360, font=self.font_status,
        )
        self.frame_ctrl.pack(fill="x", pady=(0, RUN_CLUSTER_BTN_STATUS_GAP))
        self.label_status.pack(fill="x", pady=(0, 0))
        self.frame_run_spacer_top.grid(row=0, column=0, sticky="nsew")
        self.frame_run_cluster.grid(row=1, column=0, sticky="ew")
        self.frame_run_spacer_bottom.grid(row=2, column=0, sticky="nsew")
        self.frame_run_middle.rowconfigure(0, weight=RUN_SPACER_WEIGHT_TOP)
        self.frame_run_middle.rowconfigure(1, weight=0, minsize=0)
        self.frame_run_middle.rowconfigure(2, weight=RUN_SPACER_WEIGHT_BOTTOM)

        # ── 下端固定帯：区切り線 + トグル（状態A/Bでは pack し直さない）──
        self.frame_bottom_separator = ctk.CTkFrame(
            self,
            height=BOTTOM_SEPARATOR_HEIGHT,
            fg_color=self._get_bottom_separator_color(),
            corner_radius=0,
        )
        self.frame_bottom_separator.pack_propagate(False)

        # ── 各種設定（トグル） ──
        self.frame_toggles = ctk.CTkFrame(self, fg_color="transparent")

        # 3つの設定を横に整然と並べる
        self.frame_toggles.columnconfigure(0, weight=1)
        self.frame_toggles.columnconfigure(1, weight=1)
        self.frame_toggles.columnconfigure(2, weight=1)

        chk_sound = ctk.CTkSwitch(self.frame_toggles, text="🔔 通知音", variable=self._sound_enabled, font=self.font_label, width=90)
        chk_sound.grid(row=0, column=0, padx=0, pady=2, sticky="w")
        
        chk_topmost = ctk.CTkSwitch(self.frame_toggles, text="📌 常に最前面", variable=self._always_on_top, font=self.font_label, width=110, command=self._on_topmost_changed)
        chk_topmost.grid(row=0, column=1, padx=0, pady=2, sticky="w")

        self.chk_auto_start = ctk.CTkCheckBox(
            self.frame_toggles, text="⚡ 自動接続", variable=self._auto_start,
            font=self.font_label, text_color="gray", checkbox_width=16, checkbox_height=16,
            command=self._save_config
        )
        self.chk_auto_start.grid(row=0, column=2, padx=0, pady=2, sticky="e")
        ToolTip(self.chk_auto_start, "アプリ起動時に自動で接続・監視を開始します")

        # 状態A（セットアップ）/ 状態B（実行）の初期レイアウト（自動接続＋保存ソースありなら実行側）
        start_run = bool(self.config.auto_start and self.config.target_source.strip())
        self._apply_connection_layout("run" if start_run else "setup", skip_fit=True)

        # 下端を先に確保してから動的中間を expand（見切れ防止）
        self.frame_toggles.pack(side="bottom", fill="x", padx=20, pady=(0, 2))
        self.frame_bottom_separator.pack(
            side="bottom",
            fill="x",
            padx=BOTTOM_SEPARATOR_PADX,
            pady=(BOTTOM_SEPARATOR_PADY_TOP, BOTTOM_SEPARATOR_PADY_BOTTOM),
        )
        self.frame_dynamic.pack(side="top", fill="both", expand=True, padx=20, pady=(0, 0))
        self.frame_bottom_separator.lift()
        self.frame_toggles.lift()
        # 動的中間は pack 順で ID 帯より前面になるため、ヒントが角丸カードに隠れないよう ID 帯を前面へ
        self._frame_id_outer.lift()

        # ── 履歴ドロップダウン（右上端）──
        # 対象ソースのコンボボックスと同系統: 左にラベル、右にキャレット領域。
        self.frame_history_trigger = ctk.CTkFrame(
            self,
            height=HISTORY_TRIGGER_HEIGHT,
            fg_color=HISTORY_FG,
            corner_radius=HISTORY_CORNER_RADIUS,
        )
        self.frame_history_trigger.place(relx=1.0, y=10, x=-12, anchor="ne")
        self.frame_history_trigger.pack_propagate(False)
        self.frame_history_trigger.lift()
        # ランプは ID 行より手前に（pack 順で隠れないよう）。緑ハイライト時は _flash_main_id で ID フレームだけ一時的に前面へ。
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

        # 角丸の外枠 + 内側パディングで角が潰れず見える（子は内側フレームに詰める）
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
        # expand=False: 縦に伸ばさず中身の高さに合わせる（expand=True だと下だけ空きが出やすい）
        self.frame_history_menu_inner.pack(
            fill="x",
            expand=False,
            padx=HISTORY_MENU_INNER_PAD,
            pady=HISTORY_MENU_INNER_PAD,
        )
        # 子ウィジェットの最小幅(CTkButton 既定など)に親幅が引き伸ばされるのを防ぐ
        self.frame_history_menu.pack_propagate(False)
        self.bind("<Button-1>", self._check_click_outside, add="+")

        self.update()
        self._fixed_window_height = self._compute_fixed_window_height()
        self._fit_window_height_to_content()
        self.update()

    def _build_connection_cards(self) -> None:
        """OBS 設定・対象ソースを独立した角丸カードにし、ヘッダクリックで状態A/Bを切替。"""
        self._connection_layout_mode = "setup"
        caret_bg = self._get_bg_color()

        # --- OBS カード（内側ラッパーでインセットを取り、底に full-width 子を置かず角丸を維持）---
        self.frame_obs_card = ctk.CTkFrame(self.frame_dynamic, corner_radius=CONNECTION_CARD_CORNER_RADIUS)
        self.frame_obs_inner = ctk.CTkFrame(self.frame_obs_card, fg_color="transparent")
        self.frame_obs_inner.pack(
            fill="both",
            expand=True,
            padx=CONNECTION_CARD_INSET,
            pady=CONNECTION_CARD_INSET,
        )
        self.frame_obs_header = ctk.CTkFrame(
            self.frame_obs_inner, fg_color="transparent", height=CONNECTION_HEADER_ROW_HEIGHT
        )
        self.frame_obs_header.pack(fill="x", padx=CONNECTION_CARD_UNIFORM_PAD + 1, pady=(CONNECTION_HEADER_PADY, CONNECTION_HEADER_PADY))
        self.frame_obs_header.pack_propagate(False)
        self.canvas_connection_caret_obs = ctk.CTkCanvas(
            self.frame_obs_header,
            width=CONNECTION_CARET_W,
            height=CONNECTION_CARET_H,
            bg=caret_bg,
            highlightthickness=0,
        )
        self.label_connection_obs = ctk.CTkLabel(
            self.frame_obs_header,
            text="■ OBS WebSocket 接続設定",
            font=self.font_heading,
            anchor="center",
        )
        self.label_connection_obs.place(relx=0.5, rely=0.5, anchor="center")
        self.canvas_connection_caret_obs.place(x=HEADER_CARET_PAD_X, rely=0.5, anchor="w")
        # Canvas は lift/tkraise を tag_raise に束縛しているため、ウィジェット順は Misc.tkraise を使う
        tk.Misc.tkraise(self.canvas_connection_caret_obs)
        for w in (self.frame_obs_header, self.canvas_connection_caret_obs, self.label_connection_obs):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", lambda e: self._toggle_connection_layout())

        self.frame_obs_body = ctk.CTkFrame(self.frame_obs_inner, fg_color="transparent")
        for label, attr, default, show in [
            ("IP アドレス:", "entry_ip", self.config.host, ""),
            ("ポート番号:", "entry_port", str(self.config.port), ""),
            ("パスワード:", "entry_pass", self.config.password, "*"),
        ]:
            row = ctk.CTkFrame(self.frame_obs_body, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=CONNECTION_ROW_PADY)
            ctk.CTkLabel(row, text=label, width=95, anchor="w", font=self.font_label).pack(side="left")
            entry = ctk.CTkEntry(row, width=190, show=show, font=self.font_input)
            entry.insert(0, default)
            entry.pack(side="right")
            setattr(self, attr, entry)

        self.btn_connect = ctk.CTkButton(
            self.frame_obs_body,
            text="OBS に接続",
            command=self._on_connect,
            font=self.font_btn,
            width=200,
        )
        self.btn_connect.pack(pady=CONNECTION_BTN_CONNECT_PADY)

        # --- 対象ソースカード ---
        self.frame_source_card = ctk.CTkFrame(self.frame_dynamic, corner_radius=CONNECTION_CARD_CORNER_RADIUS)
        self.frame_source_inner = ctk.CTkFrame(self.frame_source_card, fg_color="transparent")
        self.frame_source_inner.pack(
            fill="both",
            expand=True,
            padx=CONNECTION_CARD_INSET,
            pady=CONNECTION_CARD_INSET,
        )
        self.frame_source_header = ctk.CTkFrame(
            self.frame_source_inner, fg_color="transparent", height=CONNECTION_HEADER_ROW_HEIGHT
        )
        self.frame_source_header.pack(fill="x", padx=CONNECTION_CARD_UNIFORM_PAD + 1, pady=(CONNECTION_HEADER_PADY, CONNECTION_HEADER_PADY))
        self.frame_source_header.pack_propagate(False)
        self.canvas_connection_caret_src = ctk.CTkCanvas(
            self.frame_source_header,
            width=CONNECTION_CARET_W,
            height=CONNECTION_CARET_H,
            bg=caret_bg,
            highlightthickness=0,
        )
        self.label_connection_src = ctk.CTkLabel(
            self.frame_source_header,
            text="■ 対象ソース",
            font=self.font_heading,
            anchor="center",
        )
        self.label_connection_src.place(relx=0.5, rely=0.5, anchor="center")
        self.canvas_connection_caret_src.place(x=HEADER_CARET_PAD_X, rely=0.5, anchor="w")
        tk.Misc.tkraise(self.canvas_connection_caret_src)
        for w in (self.frame_source_header, self.canvas_connection_caret_src, self.label_connection_src):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", lambda e: self._toggle_connection_layout())

        self.frame_source_body = ctk.CTkFrame(self.frame_source_inner, fg_color="transparent")
        self.combo_source = ctk.CTkComboBox(
            self.frame_source_body,
            values=[],
            state="disabled",
            width=300,
            font=self.font_input,
            dropdown_font=self.font_input,
            command=self._on_source_select,
        )
        self.combo_source.pack(pady=CONNECTION_COMBO_PADY)

        # 伸縮スペーサー（状態Aのみ：動的中間内で対象ソースを下へ）
        # 空の CTkFrame は要請高さが約200pxになり、状態Aで無意味な縦余白になるため tk.Frame で最小化する
        self.frame_connection_spacer = tk.Frame(
            self.frame_dynamic,
            height=1,
            bg=self._get_bg_color(),
            highlightthickness=0,
        )

    def _draw_connection_caret(self, canvas: ctk.CTkCanvas, expanded: bool) -> None:
        """展開中は下向き、畳み時は右向きのシェブロン。"""
        canvas.delete("all")
        canvas.configure(bg=self._get_bg_color())
        if expanded:
            canvas.create_line(
                2, 4, 7, 9, 12, 4,
                fill=CONNECTION_CARET_COLOR,
                width=2,
                capstyle="round",
                joinstyle="round",
            )
        else:
            canvas.create_line(
                4, 2, 9, 6, 4, 10,
                fill=CONNECTION_CARET_COLOR,
                width=2,
                capstyle="round",
                joinstyle="round",
            )

    def _update_connection_carets(self) -> None:
        setup = self._connection_layout_mode == "setup"
        self._draw_connection_caret(self.canvas_connection_caret_obs, setup)
        self._draw_connection_caret(self.canvas_connection_caret_src, not setup)

    def _set_obs_card_expanded(self, expanded: bool) -> None:
        if expanded:
            self.frame_obs_body.pack(fill="x", padx=0, pady=(0, CONNECTION_BODY_PACK_PAD_BOTTOM))
        else:
            self.frame_obs_body.pack_forget()

    def _set_source_card_expanded(self, expanded: bool) -> None:
        if expanded:
            self.frame_source_body.pack(fill="x", padx=0, pady=(0, CONNECTION_BODY_PACK_PAD_BOTTOM))
        else:
            self.frame_source_body.pack_forget()

    def _toggle_connection_layout(self) -> None:
        """どちらのヘッダを押しても A↔B をスワップ。"""
        next_mode = "run" if self._connection_layout_mode == "setup" else "setup"
        self._apply_connection_layout(next_mode)

    def _apply_connection_layout(self, mode: str, *, skip_fit: bool = False) -> None:
        """
        setup（状態A）: OBS 展開、対象ソースはヘッダのみ＋スペーサーで下寄せ、監視行＋ステータス非表示。
        run（状態B）: OBS 畳み、対象ソース展開、監視行＋ステータス表示。
        frame_dynamic 内は grid で配置（カード枠を pack_forget しないため切替時の点滅を軽減）。
        """
        if mode not in ("setup", "run"):
            return
        self._connection_layout_mode = mode

        # OBS/ソースのカード枠は grid_forget しない（再マップの点滅を抑える）。可変行だけ外す。
        for w in (self.frame_connection_spacer, self.frame_run_middle):
            w.grid_forget()

        self.frame_dynamic.columnconfigure(0, weight=1)

        if mode == "setup":
            self._set_obs_card_expanded(True)
            self._set_source_card_expanded(False)
            # スペーサーは 2 カードの「間」ではなく下に置き、カード同士は近接させる
            self.frame_obs_card.grid(row=0, column=0, sticky="ew", pady=(0, CONNECTION_CARD_PEER_GAP))
            self.frame_source_card.grid(row=1, column=0, sticky="ew", pady=(0, 0))
            self.frame_connection_spacer.grid(row=2, column=0, sticky="nsew")
            self.frame_dynamic.rowconfigure(0, weight=0)
            self.frame_dynamic.rowconfigure(1, weight=0)
            self.frame_dynamic.rowconfigure(2, weight=1)
        else:
            self._set_obs_card_expanded(False)
            self._set_source_card_expanded(True)
            self.frame_obs_card.grid(row=0, column=0, sticky="ew", pady=(0, 0))
            self.frame_source_card.grid(row=1, column=0, sticky="ew", pady=(CONNECTION_CARD_PEER_GAP, CONNECTION_CARD_UNIFORM_PAD))
            self.frame_run_middle.grid(
                row=2, column=0, sticky="nsew", pady=RUN_MIDDLE_GRID_PADY
            )
            self.frame_dynamic.rowconfigure(0, weight=0)
            self.frame_dynamic.rowconfigure(1, weight=0)
            self.frame_dynamic.rowconfigure(2, weight=1)

        self._update_connection_carets()
        try:
            self.frame_bottom_separator.lift()
            self.frame_toggles.lift()
        except tk.TclError:
            pass
        if not skip_fit:
            self._fit_window_height_to_content()
            self.update()

    def _compute_fixed_window_height(self) -> int:
        """状態A（setup）と状態B（run）の要請高さの大きい方にウィンドウ縦を固定する（切替でリサイズしない）。"""
        saved = self._connection_layout_mode
        self._apply_connection_layout("setup", skip_fit=True)
        self.update()
        h_setup = int(self.winfo_reqheight())
        self._apply_connection_layout("run", skip_fit=True)
        self.update()
        h_run = int(self.winfo_reqheight())
        self._apply_connection_layout(saved, skip_fit=True)
        self.update()
        return max(h_setup, h_run)

    def _fit_window_height_to_content(self) -> None:
        """起動時に求めた固定縦幅へ合わせる。スペーサー行の weight=1 は余白吸収用で、ウィンドウ外寸は変えない。"""
        self.update_idletasks()
        try:
            if getattr(self, "_fixed_window_height", None) is not None:
                req = int(self._fixed_window_height)
            else:
                req = int(self.winfo_reqheight())
            if req < 1:
                return
            self.geometry(f"{WINDOW_WIDTH}x{req}")
        except tk.TclError:
            pass

    def _get_bg_color(self):
        # Canvas用に現在のテーマの背景色(近似値)を取得
        mode = ctk.get_appearance_mode()
        return "#242424" if mode == "Dark" else "#ebebeb"

    def _get_bottom_separator_color(self) -> str:
        """下端区切り線。ダークは履歴メニュー枠と同色(HISTORY_BORDER)、ライトは #666666 で明度を抑える。"""
        if ctk.get_appearance_mode() == "Dark":
            return HISTORY_BORDER
        return "#666666"

    def _on_topmost_changed(self):
        self.config.always_on_top = self._always_on_top.get()
        self.attributes("-topmost", self.config.always_on_top)
        self._save_config()

    def _flash_main_id(self):
        # コピー成功を強烈にアピールするため、巨大ID背景を反転させる演出
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

    def _toggle_history_menu(self, event=None):
        if self.frame_history_menu.winfo_ismapped():
            self.frame_history_menu.place_forget()
            self._history_menu_open = False
            self._draw_history_caret(False)
            return

        self._layout_history_trigger()
        self.update_idletasks()
        self.frame_history_trigger.update_idletasks()
        # プルダウン幅は「履歴」トリガーの実幅に厳密に合わせる
        tw = max(
            self.frame_history_trigger.winfo_width(),
            self.frame_history_trigger.winfo_reqwidth(),
        )
        menu_w = tw

        for widget in self.frame_history_menu_inner.winfo_children():
            widget.destroy()

        items = self._recent_ids if self._recent_ids else ["履歴なし"]
        n = len(items)
        # 枠線(1px×2)と内側 pad を除いたボタン幅 — 親を広げないよう明示指定
        btn_inner_w = max(28, menu_w - 2 * HISTORY_MENU_INNER_PAD - 4)
        for idx, item in enumerate(items):
            is_first = idx == 0
            is_last = idx == n - 1
            if n == 1:
                row_radius = HISTORY_CORNER_RADIUS
            elif is_first or is_last:
                row_radius = HISTORY_CORNER_RADIUS
            else:
                row_radius = 0
            btn = ctk.CTkButton(
                self.frame_history_menu_inner,
                text=item,
                font=self.font_small,
                width=btn_inner_w,
                height=HISTORY_ITEM_HEIGHT,
                fg_color=HISTORY_FG,
                hover_color=HISTORY_HOVER,
                text_color="#bbbbbb",
                anchor="center",
                corner_radius=row_radius,
                border_spacing=0,
                command=lambda i=item: self._select_history_item(i),
            )
            btn.pack(fill="x", pady=0)

        self.frame_history_menu.update_idletasks()
        self.frame_history_menu_inner.update_idletasks()
        inner_h = self.frame_history_menu_inner.winfo_reqheight()
        # 外枠 = 上下 inner pad + 上下 border + 中身（過剰な加算は下に余白が溜まる）
        _menu_border = int(self.frame_history_menu.cget("border_width") or 0)
        menu_outer_h = max(
            inner_h + 2 * HISTORY_MENU_INNER_PAD + 2 * _menu_border,
            HISTORY_TRIGGER_HEIGHT,
        )

        self.frame_history_menu.configure(width=menu_w, height=menu_outer_h)
        self.frame_history_menu.update_idletasks()

        tx = self.frame_history_trigger.winfo_x()
        # トリガー右端にメニュー右端を揃え、ウィンドウ内に収める
        x_raw = tx + tw - menu_w
        win_w = self.winfo_width()
        max_x = win_w - menu_w - HISTORY_WINDOW_EDGE_RIGHT
        min_x = HISTORY_WINDOW_EDGE_LEFT
        x = max(min_x, min(x_raw, max_x))

        y = self.frame_history_trigger.winfo_y() + self.frame_history_trigger.winfo_height() + 2
        self.frame_history_menu.place(x=x, y=y)
        self.frame_history_menu.lift()
        self._history_menu_open = True
        self._draw_history_caret(True)

        y_menu = y

        def _post_place_verify():
            try:
                if not self.winfo_exists():
                    return
                self.update_idletasks()
                aw = self.frame_history_menu.winfo_width()
                x_curr = self.frame_history_menu.winfo_x()
                win_w2 = self.winfo_width()
                max_right = win_w2 - HISTORY_WINDOW_EDGE_RIGHT
                # 幅が tw に一致していれば通常クランプ不要（ジャンプ防止）。ズレた場合のみ補正。
                if aw > menu_w + 2 or x_curr + aw > max_right:
                    if x_curr + aw > max_right:
                        x_adjusted = max(HISTORY_WINDOW_EDGE_LEFT, max_right - aw)
                        self.frame_history_menu.place(x=x_adjusted, y=y_menu)
                        self.update_idletasks()
            except Exception:
                pass

        self.after(0, _post_place_verify)

    def _select_history_item(self, item):
        self.frame_history_menu.place_forget()
        self._history_menu_open = False
        self._draw_history_caret(False)
        if item != "履歴なし":
            pyperclip.copy(item)
            self.label_status.configure(text=f"履歴からコピー: {item}", text_color="#00FF88")

    def _check_click_outside(self, event):
        if self.frame_history_menu.winfo_ismapped():
            try:
                x, y = self.winfo_pointerxy()
                rx = self.frame_history_menu.winfo_rootx()
                ry = self.frame_history_menu.winfo_rooty()
                rw = self.frame_history_menu.winfo_width()
                rh = self.frame_history_menu.winfo_height()
                
                bx = self.frame_history_trigger.winfo_rootx()
                by = self.frame_history_trigger.winfo_rooty()
                bw = self.frame_history_trigger.winfo_width()
                bh = self.frame_history_trigger.winfo_height()
                
                if not (rx <= x <= rx + rw and ry <= y <= ry + rh) and not (bx <= x <= bx + bw and by <= y <= by + bh):
                    self.frame_history_menu.place_forget()
                    self._history_menu_open = False
                    self._draw_history_caret(False)
            except Exception:
                pass

    def _setup_tray(self):
        icon_img = _create_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem("開く", self._on_tray_open, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("終了", self._on_tray_exit),
        )
        self._tray_icon = pystray.Icon(
            "SmashArenaIDScanner", icon_img, "Smash Arena ID Scanner", menu
        )
        self._tray_icon.run_detached()

    def _minimize_to_tray(self):
        self.withdraw()

    def _on_unmap(self, event):
        # 最小化時にトレイに収納する。
        # state() は withdraw() 後に内部状態が変化するため try/except で保護する。
        try:
            if self.state() == "iconic":
                self.withdraw()
        except Exception:
            pass

    def _on_tray_open(self, icon=None, item=None):
        # deiconify と lift を同一の after でまとめて呼び出す
        def _show():
            self.deiconify()
            self.lift()
        self.after(0, _show)

    def _on_tray_exit(self, icon=None, item=None):
        self._request_shutdown()

    def _request_shutdown(self):
        """終了要求を受け取り、UIスレッドで一度だけ終了シーケンスを開始する。"""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        try:
            self.after(0, self._full_destroy)
        except tk.TclError:
            self._full_destroy()

    def _stop_worker(self, *, join_timeout: float = 3.0) -> None:
        """ワーカー停止処理を共通化し、例外時でも終了シーケンスを継続する。"""
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
        """ワーカー停止・トレイ解放・GUI破棄を一度だけ実行する。"""
        if self._is_destroying:
            return
        self._is_destroying = True

        self._stop_worker(join_timeout=3.0)

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
        self.config.host = self.entry_ip.get().strip()
        port_str = self.entry_port.get().strip()
        if port_str.isdigit():
            self.config.port = max(1, min(65535, int(port_str)))
        else:
            self.config.port = 4455
        self.config.password = self.entry_pass.get().strip()
        self.config.always_on_top = self._always_on_top.get()
        self.config.auto_start = self._auto_start.get()
        self.config.sound_enabled = self._sound_enabled.get()  # 通知音設定も永続化
        ConfigManager.save(self.config)

    def _resolve_template(self, name: str) -> Optional[str]:
        p = os.path.join(self._base_path, name)
        return p if os.path.exists(p) else None

    def _on_connect(self):
        if self._is_shutting_down:
            return
        self._save_config()
        self.btn_connect.configure(state="disabled", text="接続中...")
        self.btn_toggle.configure(state="disabled", text="監視を開始",
                                  fg_color="#28a745", hover_color="#218838")
        self.canvas_indicator.itemconfig(self.indicator_oval, fill="gray")  # ← インジケーターをリセット
        self.combo_source.configure(state="disabled", values=[])
        self.label_status.configure(text="接続しています...", text_color="gray")

        self._stop_worker(join_timeout=3.0)

        self.worker = OCRWorker(
            config=self.config,
            on_status=self._safe_update_status,
            on_sources=self._safe_update_sources,
            on_id_found=self._safe_on_id_found,
            on_disconnected=self._safe_on_disconnected,
            template_1080p=self._resolve_template("arenahere.png"),
            template_720p=self._resolve_template("arenahere_720p.png"),
            on_detection_lamps=self._safe_update_detection_lamps,
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
            # 監視開始状態：赤系のボタン、赤丸
            self.btn_toggle.configure(text="監視を停止", fg_color="#dc3545", hover_color="#c82333")
            self.canvas_indicator.itemconfig(self.indicator_oval, fill="#ff4444")
            self.label_status.configure(
                text="👀 監視中... 部屋IDをスキャンしています", text_color="white"
            )
        else:
            self.worker.is_monitoring = False
            # 監視停止状態：緑系のボタン、灰丸
            self.btn_toggle.configure(text="監視を開始", fg_color="#28a745", hover_color="#218838")
            self.canvas_indicator.itemconfig(self.indicator_oval, fill="gray")
            self.label_status.configure(text="監視を停止しました。", text_color="gray")

    def _safe_update_detection_lamps(self, room: bool, id_ok: bool) -> None:
        if self._is_shutting_down:
            return
        def upd():
            self.canvas_lamp_room.itemconfig(
                self.oval_lamp_room, fill=LAMP_ROOM_ON if room else LAMP_ROOM_OFF
            )
            self.canvas_lamp_id.itemconfig(
                self.oval_lamp_id, fill=LAMP_ID_ON if id_ok else LAMP_ID_OFF
            )
        try:
            self.after(0, upd)
        except tk.TclError:
            pass

    def _safe_update_status(self, text: str):
        if self._is_shutting_down:
            return
        color = "#ff6b6b" if "エラー" in text else ("#cccccc" if "停止" in text or "接続中" in text else "white")

        def upd():
            self.label_status.configure(text=text, text_color=color)
            if self._connection_layout_mode == "setup" and "エラー" in text:
                try:
                    if self.winfo_exists():
                        messagebox.showerror("接続エラー", text, parent=self)
                except tk.TclError:
                    pass

        try:
            self.after(0, upd)
        except tk.TclError:
            pass

    def _safe_update_sources(self, sources: list[str]):
        if self._is_shutting_down:
            return
        def update():
            self.btn_connect.configure(state="normal", text="再接続")
            self.combo_source.configure(state="normal", values=sources)
            if self.config.target_source in sources:
                self.combo_source.set(self.config.target_source)
            elif sources:
                self.combo_source.set(sources[0])
                self.config.target_source = sources[0]
            self.btn_toggle.configure(state="normal", text="監視を開始",
                                      fg_color="#28a745", hover_color="#218838")
            self.canvas_indicator.itemconfig(self.indicator_oval, fill="gray")  # ← インジケーター確実にリセット
            self.label_status.configure(
                text="✅ 接続完了！「監視を開始」を押してください。",
                text_color="white",
            )
            self._apply_connection_layout("run")
        try:
            self.after(0, update)
        except tk.TclError:
            pass

    def _safe_on_id_found(self, room_id: str):
        if self._is_shutting_down:
            return
        def notify():
            # IDの表示状態・履歴を更新
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
            # 背景色を反転させる演出で完了を強調
            self._flash_main_id()

            if self._sound_enabled.get():
                # winsound.SND_ASYNC は単体で非同期なのでスレッド生成は不要
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        try:
            self.after(0, notify)
        except tk.TclError:
            pass

    def _safe_on_disconnected(self):
        if self._is_shutting_down:
            return
        def reset():
            self.btn_connect.configure(state="normal", text="OBS に接続")
            self.combo_source.configure(state="disabled", values=[])
            self.btn_toggle.configure(state="disabled", text="監視を開始",
                                      fg_color="#28a745", hover_color="#218838")
            self.canvas_indicator.itemconfig(self.indicator_oval, fill="gray")  # ← インジケーターをリセット
            self.label_status.configure(
                text="OBS との接続が切れました。再接続してください。", text_color="orange"
            )
            if self.worker:
                self.worker.is_monitoring = False
                self.worker.has_connected = False
            self.canvas_lamp_room.itemconfig(self.oval_lamp_room, fill=LAMP_ROOM_OFF)
            self.canvas_lamp_id.itemconfig(self.oval_lamp_id, fill=LAMP_ID_OFF)
            self._apply_connection_layout("setup")
            try:
                if self.winfo_exists():
                    messagebox.showwarning(
                        "OBS",
                        "OBS との接続が切れました。再接続してください。",
                        parent=self,
                    )
            except tk.TclError:
                pass
        try:
            self.after(0, reset)
        except tk.TclError:
            pass

    def destroy(self):
        """終了経路を統一し、二重実行を防ぎながら安全に破棄する。"""
        self._request_shutdown()


if __name__ == "__main__":
    app = SmashArenaIDScannerApp()
    app.mainloop()

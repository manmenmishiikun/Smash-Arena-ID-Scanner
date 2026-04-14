"""
OBS 接続設定・対象ソースの角丸カードと setup/run レイアウト切替。
"""

import tkinter as tk

import customtkinter as ctk

from gui.constants import (
    BOTTOM_SEPARATOR_PADY_BOTTOM,
    BOTTOM_SEPARATOR_PADY_TOP,
    CONNECTION_BODY_PACK_PAD_BOTTOM,
    CONNECTION_BTN_CONNECT_PADY,
    CONNECTION_CARD_CORNER_RADIUS,
    CONNECTION_CARD_INSET,
    CONNECTION_CARD_PEER_GAP,
    CONNECTION_CARD_UNIFORM_PAD,
    CONNECTION_CARET_COLOR,
    CONNECTION_CARET_H,
    CONNECTION_CARET_W,
    CONNECTION_COMBO_PADY,
    CONNECTION_HEADER_PADY,
    CONNECTION_HEADER_ROW_HEIGHT,
    CONNECTION_ROW_PADY,
    HEADER_CARET_PAD_X,
    RUN_MIDDLE_GRID_PADY,
    RUN_SPACER_WEIGHT_BOTTOM,
    RUN_SPACER_WEIGHT_TOP,
    WINDOW_WIDTH,
)


class ConnectionLayoutMixin:
    """`_build_connection_cards` と setup/run グリッド切替。`SmashArenaIDScannerApp` と組み合わせる。"""

    def _build_connection_cards(self) -> None:
        """OBS 設定・対象ソースを独立した角丸カードにし、ヘッダクリックで状態A/Bを切替。"""
        self._connection_layout_mode = "setup"
        caret_bg = self._get_bg_color()

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
        self.frame_obs_header.pack(
            fill="x",
            padx=CONNECTION_CARD_UNIFORM_PAD + 1,
            pady=(CONNECTION_HEADER_PADY, CONNECTION_HEADER_PADY),
        )
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
        self.label_setup_status = ctk.CTkLabel(
            self.frame_obs_body,
            text="",
            text_color="orange",
            wraplength=330,
            font=self.font_status,
        )

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
        self.frame_source_header.pack(
            fill="x",
            padx=CONNECTION_CARD_UNIFORM_PAD + 1,
            pady=(CONNECTION_HEADER_PADY, CONNECTION_HEADER_PADY),
        )
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

        self.frame_connection_spacer = tk.Frame(
            self.frame_dynamic,
            height=1,
            bg=self._get_bg_color(),
            highlightthickness=0,
        )

    def _draw_connection_caret(self, canvas: ctk.CTkCanvas, expanded: bool) -> None:
        canvas.delete("all")
        canvas.configure(bg=self._get_bg_color())
        if expanded:
            canvas.create_line(
                2,
                4,
                7,
                9,
                12,
                4,
                fill=CONNECTION_CARET_COLOR,
                width=2,
                capstyle="round",
                joinstyle="round",
            )
        else:
            canvas.create_line(
                4,
                2,
                9,
                6,
                4,
                10,
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

    def _set_setup_status_notice(self, text: str = "", color: str = "orange") -> None:
        try:
            if not text:
                self.label_setup_status.pack_forget()
                return
            self.label_setup_status.configure(text=text, text_color=color)
            if not self.label_setup_status.winfo_ismapped():
                self.label_setup_status.pack(fill="x", padx=12, pady=(0, 6))
        except tk.TclError:
            pass

    def _toggle_connection_layout(self) -> None:
        next_mode = "run" if self._connection_layout_mode == "setup" else "setup"
        self._apply_connection_layout(next_mode)

    def _apply_connection_layout(self, mode: str, *, skip_fit: bool = False) -> None:
        if mode not in ("setup", "run"):
            return
        self._connection_layout_mode = mode

        for w in (self.frame_connection_spacer, self.frame_run_middle):
            w.grid_forget()

        self.frame_dynamic.columnconfigure(0, weight=1)

        if mode == "setup":
            self._set_obs_card_expanded(True)
            self._set_source_card_expanded(False)
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
            self.frame_source_card.grid(
                row=1, column=0, sticky="ew", pady=(CONNECTION_CARD_PEER_GAP, CONNECTION_CARD_UNIFORM_PAD)
            )
            self.frame_run_middle.grid(row=2, column=0, sticky="nsew", pady=RUN_MIDDLE_GRID_PADY)
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

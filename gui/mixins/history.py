"""
右上の履歴ドロップダウン（トリガー幅・メニュー配置）。
"""

import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk
import pyperclip

from gui.constants import (
    HISTORY_CORNER_RADIUS,
    HISTORY_FG,
    HISTORY_GAP_TEXT_TO_CARET,
    HISTORY_HOVER,
    HISTORY_ITEM_HEIGHT,
    HISTORY_MENU_INNER_PAD,
    HISTORY_MIN_TRIGGER_WIDTH,
    HISTORY_TEXT_PAD_LEFT,
    HISTORY_TEXT_PAD_RIGHT,
    HISTORY_TRIGGER_HEIGHT,
    HISTORY_TRIGGER_TEXT,
    HISTORY_WINDOW_EDGE_LEFT,
    HISTORY_WINDOW_EDGE_RIGHT,
    HISTORY_CARET_CANVAS_W,
)


class HistoryMenuMixin:
    """履歴 UI。`SmashArenaIDScannerApp` と組み合わせる。"""

    def _measure_history_text(self, text: str) -> int:
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
        candidates = ["🕒 履歴", "履歴なし"] + list(self._recent_ids)
        key = tuple(self._recent_ids)
        cached = getattr(self, "_history_width_by_key", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        max_tw = (
            max(self._measure_history_text(s) for s in candidates)
            if candidates
            else self._measure_history_text("🕒 履歴")
        )
        w = (
            HISTORY_TEXT_PAD_LEFT
            + max_tw
            + HISTORY_GAP_TEXT_TO_CARET
            + HISTORY_CARET_CANVAS_W
            + HISTORY_TEXT_PAD_RIGHT
        )
        out = max(HISTORY_MIN_TRIGGER_WIDTH, w)
        self._history_width_by_key = (key, out)
        return out

    def _layout_history_trigger(self) -> None:
        w = self._compute_history_trigger_width()
        if w != self._history_trigger_width_cache:
            self._history_trigger_width_cache = w
            self.frame_history_trigger.configure(width=w)
            self.frame_history_trigger.update_idletasks()

    def _draw_history_caret(self, open_menu: bool) -> None:
        self.canvas_history_caret.delete("all")
        self.canvas_history_caret.configure(bg=HISTORY_FG)
        if open_menu:
            self.canvas_history_caret.create_line(
                2,
                7,
                6,
                3,
                10,
                7,
                fill=HISTORY_TRIGGER_TEXT,
                width=2,
                capstyle="round",
                joinstyle="round",
            )
        else:
            self.canvas_history_caret.create_line(
                2,
                3,
                6,
                7,
                10,
                3,
                fill=HISTORY_TRIGGER_TEXT,
                width=2,
                capstyle="round",
                joinstyle="round",
            )

    def _toggle_history_menu(self, event=None):
        if self.frame_history_menu.winfo_ismapped():
            self.frame_history_menu.place_forget()
            self._history_menu_open = False
            self._draw_history_caret(False)
            return

        self._layout_history_trigger()
        self.update_idletasks()
        self.frame_history_trigger.update_idletasks()
        tw = max(
            self.frame_history_trigger.winfo_width(),
            self.frame_history_trigger.winfo_reqwidth(),
        )
        menu_w = tw

        for widget in self.frame_history_menu_inner.winfo_children():
            widget.destroy()

        items = self._recent_ids if self._recent_ids else ["履歴なし"]
        n = len(items)
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
        _menu_border = int(self.frame_history_menu.cget("border_width") or 0)
        menu_outer_h = max(
            inner_h + 2 * HISTORY_MENU_INNER_PAD + 2 * _menu_border,
            HISTORY_TRIGGER_HEIGHT,
        )

        self.frame_history_menu.configure(width=menu_w, height=menu_outer_h)
        self.frame_history_menu.update_idletasks()

        tx = self.frame_history_trigger.winfo_x()
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

                if not (rx <= x <= rx + rw and ry <= y <= ry + rh) and not (
                    bx <= x <= bx + bw and by <= y <= by + bh
                ):
                    self.frame_history_menu.place_forget()
                    self._history_menu_open = False
                    self._draw_history_caret(False)
            except Exception:
                pass

"""ホバーで説明を表示するプレーンなツールチップ。"""

from typing import Optional

import tkinter as tk


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
        self.tw.wm_attributes("-topmost", True)

        label = tk.Label(
            self.tw,
            text=self.text,
            background="#333333",
            foreground="white",
            relief="solid",
            borderwidth=1,
            font=("Yu Gothic UI", 9),
            padx=6,
            pady=3,
        )
        label.pack()

        self.tw.update_idletasks()
        tw_width = self.tw.winfo_reqwidth()

        master = self.widget.winfo_toplevel()
        max_x = master.winfo_rootx() + master.winfo_width() - 20
        if x + tw_width > max_x:
            x = max_x - tw_width

        self.tw.wm_geometry(f"+{x}+{y}")

    def leave(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None

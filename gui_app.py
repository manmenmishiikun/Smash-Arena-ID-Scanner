"""
後方互換: `from gui_app import SmashArenaIDScannerApp` を維持する。
実装は `gui` パッケージ（`gui/main_window.py` 等）に分割済み。
"""

from gui.main_window import SmashArenaIDScannerApp

__all__ = ["SmashArenaIDScannerApp"]

"""
Windows のクリップボード履歴 (Win+V) から、指定テキストと一致する項目を 1 件削除する。

WinRT Clipboard.GetHistoryItemsAsync / DeleteItemFromHistory を利用。
履歴オフ・権限不足・環境差では失敗しうるため、例外は握りつぶす（ベストエフォート）。
Mac 等では import / プラットフォーム判定で何もしない。
"""

from __future__ import annotations

import sys


async def try_remove_text_from_clipboard_history(text: str) -> None:
    if sys.platform != "win32" or not (text or "").strip():
        return
    needle = text.strip()
    try:
        from winsdk.windows.applicationmodel.datatransfer import (
            Clipboard,
            ClipboardHistoryItemsResultStatus,
            StandardDataFormats,
        )
    except ImportError:
        return

    try:
        if not bool(Clipboard.is_history_enabled()):
            return
        result = await Clipboard.get_history_items_async()
        if result.status != ClipboardHistoryItemsResultStatus.SUCCESS:
            return
        items = result.items
        if not items:
            return
        fmt = StandardDataFormats.text
        for item in items:
            if item is None:
                continue
            view = item.content
            if view is None or not bool(view.contains(fmt)):
                continue
            try:
                t = await view.get_text_async()
            except Exception:
                continue
            if t is not None and t.strip() == needle:
                Clipboard.delete_item_from_history(item)
                return
    except Exception:
        return

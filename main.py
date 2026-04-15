import logging
import os
import sys
import threading
import ctypes

from gui.main_window import SmashArenaIDScannerApp


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0
SW_RESTORE = 9

MUTEX_NAME = r"Global\SmashArenaIDScanner_SingleInstance"
ACTIVATE_EVENT_NAME = r"Global\SmashArenaIDScanner_ActivateEvent"
MAIN_WINDOW_TITLE = "Smash Arena ID Scanner"


logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """ルートロガーと image_processor 用のレベルを設定する。"""
    level = (
        logging.DEBUG
        if os.environ.get("SMASH_ROOM_OCR_LOG", "").lower() in ("1", "debug", "true")
        else logging.INFO
    )
    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(h)
    root.setLevel(level)

    lg = logging.getLogger("image_processor")
    if not lg.handlers:
        h2 = logging.StreamHandler(sys.stderr)
        h2.setFormatter(logging.Formatter("%(message)s"))
        lg.addHandler(h2)
    lg.setLevel(level)
    lg.propagate = False


def _request_existing_instance_activation() -> None:
    """既存インスタンスへ前面表示要求を送る。失敗時はタイトル検索で復元を試みる。"""
    event_handle = kernel32.OpenEventW(0x00100002, False, ACTIVATE_EVENT_NAME)
    if event_handle:
        try:
            kernel32.SetEvent(event_handle)
        finally:
            kernel32.CloseHandle(event_handle)
        return

    hwnd = user32.FindWindowW(None, MAIN_WINDOW_TITLE)
    if hwnd:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)


def _start_activation_listener(app: SmashArenaIDScannerApp, stop_event: threading.Event) -> tuple[threading.Thread, int]:
    """前面表示要求イベントを待ち受け、要求が来たら既存ウィンドウを前面化する。"""
    event_handle = kernel32.CreateEventW(None, False, False, ACTIVATE_EVENT_NAME)
    if not event_handle:
        raise OSError("Activate event を作成できませんでした。")

    def _run() -> None:
        while not stop_event.is_set():
            try:
                wait_result = kernel32.WaitForSingleObject(event_handle, 250)
            except Exception:
                logger.exception("activate listener の待機で例外が発生しました。")
                return
            if wait_result == WAIT_OBJECT_0 and not stop_event.is_set():
                def _show() -> None:
                    if getattr(app, "_is_shutting_down", False):
                        return
                    if not app.winfo_exists():
                        return
                    app.deiconify()
                    app.lift()
                    app.attributes("-topmost", True)
                    app.after(120, lambda: app.attributes("-topmost", app.config.always_on_top))
                try:
                    app.after(0, _show)
                except Exception:
                    logger.exception("activate listener の UI 通知に失敗しました。")

    th = threading.Thread(target=_run, name="single-instance-activate-listener", daemon=True)
    th.start()
    return th, event_handle


def _close_handle_safely(handle: int | None, label: str) -> None:
    if not handle:
        return
    try:
        kernel32.CloseHandle(handle)
    except Exception:
        logger.exception("%s の CloseHandle に失敗しました。", label)


def main():
    _configure_logging()
    mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex_handle:
        raise OSError("Single-instance mutex の作成に失敗しました。")

    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        _request_existing_instance_activation()
        _close_handle_safely(mutex_handle, "mutex_handle")
        return

    listener_stop = threading.Event()
    listener_thread = None
    activate_event_handle = None
    app = SmashArenaIDScannerApp()
    try:
        listener_thread, activate_event_handle = _start_activation_listener(app, listener_stop)
        app.mainloop()
    finally:
        listener_stop.set()
        if activate_event_handle:
            try:
                kernel32.SetEvent(activate_event_handle)
            except Exception:
                logger.exception("activate_event_handle への SetEvent に失敗しました。")
        if listener_thread:
            try:
                listener_thread.join(timeout=1.0)
                if listener_thread.is_alive():
                    logger.warning("activate listener thread が停止待機 timeout 後も稼働中です。")
            except Exception:
                logger.exception("activate listener thread の join に失敗しました。")
        _close_handle_safely(activate_event_handle, "activate_event_handle")
        _close_handle_safely(mutex_handle, "mutex_handle")

if __name__ == "__main__":
    main()

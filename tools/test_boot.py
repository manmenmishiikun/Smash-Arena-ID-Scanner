import os
import sys
import customtkinter as ctk

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TOOLS_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from gui.main_window import SmashArenaIDScannerApp
    app = SmashArenaIDScannerApp()
    app.after(1500, app.destroy)
    app.mainloop()
    print("TEST_SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
    print("TEST_FAILED")
    sys.exit(1)

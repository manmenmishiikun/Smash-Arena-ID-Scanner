import sys
import customtkinter as ctk

try:
    from gui_app import SmashArenaIDScannerApp
    app = SmashArenaIDScannerApp()
    app.after(1500, app.destroy)
    app.mainloop()
    print("TEST_SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
    print("TEST_FAILED")
    sys.exit(1)

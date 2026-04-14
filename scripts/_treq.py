"""開発用: 接続カードの setup/run で要請高さを測るワンオフスクリプト。"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config_manager
_old = config_manager.ConfigManager.load
def _fake():
    c = _old()
    c.auto_start = False
    return c
config_manager.ConfigManager.load = _fake
from gui_app import SmashArenaIDScannerApp
app = SmashArenaIDScannerApp()
app.update_idletasks()
print('setup winfo_reqheight', app.winfo_reqheight(), 'winfo_height', app.winfo_height())
app._apply_connection_layout('run')
app.update_idletasks()
print('run winfo_reqheight', app.winfo_reqheight(), 'winfo_height', app.winfo_height())
app.destroy()

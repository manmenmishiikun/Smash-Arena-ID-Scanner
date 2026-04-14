"""開発用: 接続カードの setup/run で要請高さを測るワンオフスクリプト。"""
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

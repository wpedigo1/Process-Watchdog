"""
Process Watchdog
----------------
Runs in the system tray. Define Watchdogs like:
  "When claude.exe disappears, force-kill claude.exe / claude_helper.exe"
and it handles the cleanup automatically instead of you double-clicking
a .bat file every time.

This module is the application entry point and owns startup, tray behavior,
and the application lifecycle. Core process/config/watcher logic lives in
watchdog_core.py; windows and dialogs live in watchdog_ui.py.

Build to a Windows .exe with PyInstaller (see build.bat).
"""

import os
import sys
import time
import threading
import traceback

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None

from watchdog_core import (
    APP_NAME,
    APP_VERSION,
    CONFIG_PATH,
    load_config,
    Watcher,
    resource_path,
)
from watchdog_ui import ConfigWindow


def make_icon_image():
    """Tray icon. Uses the real logo (icon_tray.png, bundled alongside the
    exe) when available; falls back to a simple drawn shield if it's
    missing for any reason (e.g. running from source without the asset)."""
    try:
        return Image.open(resource_path("icon_tray.png")).convert("RGBA")
    except Exception:
        pass
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Shield outline — "guarding" motif
    shield = [(32, 3), (58, 14), (58, 33), (32, 61), (6, 33), (6, 14)]
    d.polygon(shield, fill=(32, 36, 46, 255), outline=(90, 150, 255, 255), width=3)
    # Eye — "watching" motif
    d.ellipse((16, 23, 48, 39), fill=(235, 240, 250, 255))
    d.ellipse((27, 26, 37, 36), fill=(32, 36, 46, 255))
    return img


def log_crash(text):
    """--windowed builds have no console, so an unhandled exception on
    launch is otherwise completely silent — exactly the 'nothing happens'
    symptom. Write it somewhere findable instead."""
    try:
        log_path = os.path.join(os.path.dirname(CONFIG_PATH), "crash.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{text}\n")
    except Exception:
        pass


def is_startup_registered():
    """Checks the HKCU Run key directly rather than trusting a saved flag,
    so the tray checkbox always reflects reality even if the registry was
    edited/cleared outside the app (e.g. by antivirus)."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        try:
            current, _ = winreg.QueryValueEx(key, APP_NAME)
        except FileNotFoundError:
            current = None
        winreg.CloseKey(key)
        return current == sys.executable
    except Exception:
        return False


def set_startup_registered(enabled):
    """User-triggered only (tray menu toggle) — NOT called automatically
    on launch. An unsigned exe silently writing itself into the Windows
    startup registry the moment it first runs is a classic antivirus
    false-positive trigger; making this opt-in avoids that entirely."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, sys.executable)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


def main():
    is_first_run = not os.path.exists(CONFIG_PATH)
    cfg = load_config()

    def on_kill(watchdog_name, count):
        print(f"[watchdog] {watchdog_name}: killed {count} process(es)")

    watcher = Watcher(get_config=lambda: config_window.cfg, on_kill=on_kill)
    config_window = ConfigWindow(cfg, on_change=lambda c: None, watcher=watcher)
    watcher.start()

    tray_ok = False
    if pystray:
        try:
            def open_config(icon=None, item=None):
                config_window.root.after(0, config_window.show)

            def quit_app(icon=None, item=None):
                watcher.stop()
                icon.stop()
                config_window.root.after(0, config_window.root.destroy)

            def toggle_startup(icon=None, item=None):
                set_startup_registered(not is_startup_registered())

            menu = pystray.Menu(
                pystray.MenuItem("Open the Doghouse", open_config, default=True),
                pystray.MenuItem("Start with Windows", toggle_startup,
                                  checked=lambda item: is_startup_registered()),
                pystray.MenuItem("Quit", quit_app),
            )
            icon = pystray.Icon(APP_NAME, make_icon_image(), APP_NAME, menu)
            threading.Thread(target=icon.run, daemon=True).start()
            tray_ok = True
        except Exception:
            log_crash(traceback.format_exc())

    if is_first_run or not tray_ok:
        # First launch ever (no config yet) — show the window so there's
        # actually something to set up watchdogs with, instead of silently
        # dropping into the tray with nothing configured. Every launch
        # after that stays hidden as usual. Also shown as a fallback if
        # the tray icon itself failed to start (see above).
        config_window.show()

    config_window.mainloop()
    watcher.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_crash(traceback.format_exc())
        raise

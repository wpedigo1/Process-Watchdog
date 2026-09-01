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
import subprocess
import sys
import time
import threading
import traceback
import xml.etree.ElementTree as ET

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


STARTUP_TASK_NAME = APP_NAME
_CREATE_NO_WINDOW = 0x08000000


def _run_schtasks(arguments):
    return subprocess.run(
        ["schtasks.exe", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_CREATE_NO_WINDOW,
    )


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
    """Check the current-user elevated logon task against this executable."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    try:
        result = _run_schtasks(["/Query", "/TN", STARTUP_TASK_NAME, "/XML"])
        if result.returncode != 0:
            return False
        command = ET.fromstring(result.stdout).find(".//{*}Command")
        if command is None or not command.text:
            return False
        configured = os.path.normcase(os.path.abspath(command.text.strip().strip('"')))
        current = os.path.normcase(os.path.abspath(sys.executable))
        return configured == current
    except Exception:
        return False


def set_startup_registered(enabled):
    """Create/delete the opt-in, highest-privilege current-user logon task."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    try:
        if enabled:
            result = _run_schtasks([
                "/Create", "/TN", STARTUP_TASK_NAME,
                "/SC", "ONLOGON", "/RL", "HIGHEST",
                "/TR", f'"{sys.executable}"', "/F",
            ])
        else:
            result = _run_schtasks(["/Delete", "/TN", STARTUP_TASK_NAME, "/F"])
        return result.returncode == 0
    except Exception:
        return False


def _read_legacy_startup():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ,
        )
        try:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return value
        except FileNotFoundError:
            return None
        finally:
            winreg.CloseKey(key)
    except Exception:
        return None


def _delete_legacy_startup():
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    try:
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
    finally:
        winreg.CloseKey(key)


def migrate_legacy_startup():
    """Preserve an opted-in legacy Run entry while moving it to Task Scheduler."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    legacy = _read_legacy_startup()
    if not legacy:
        return False
    legacy_path = os.path.normcase(os.path.abspath(str(legacy).strip().strip('"')))
    current_path = os.path.normcase(os.path.abspath(sys.executable))
    if legacy_path != current_path or not set_startup_registered(True):
        return False
    try:
        _delete_legacy_startup()
    except Exception:
        return False
    return True


def main():
    is_first_run = not os.path.exists(CONFIG_PATH)
    cfg = load_config()
    migrate_legacy_startup()

    def on_kill(rid, watchdog_name, killed, failed):
        # Fires on the watcher's background thread; marshal all UI-adjacent
        # work through root.after onto the Tkinter thread.
        config_window.root.after(0, config_window.record_kill_result,
                                 rid, watchdog_name, killed, failed)

    def on_close(rid):
        config_window.root.after(0, config_window.record_app_closed, rid)

    watcher = Watcher(
        get_config=lambda: config_window.cfg,
        on_kill=on_kill,
        on_close=on_close,
    )
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

"""The presenting switch: hide/show Home's Recent section (and frequent folders).

Uses the same values as Folder Options -> "Show recently used files" / "Show frequently
used folders". History is untouched. (Do NOT use Start's "Show recently opened items"
toggle for this — switching that off wipes the history.)
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
import winreg
from ctypes import wintypes
from pathlib import Path

KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer"
VALUES = ("ShowRecent", "ShowFrequent")
STATE_FILE = Path(os.environ["LOCALAPPDATA"]) / "recentctl" / "present-state.json"


def read() -> dict[str, int]:
    """Current values; a missing value means Windows' default, which is 1 (shown)."""
    out = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        for name in VALUES:
            try:
                out[name] = int(winreg.QueryValueEx(k, name)[0])
            except FileNotFoundError:
                out[name] = 1
    return out


def _write(values: dict[str, int]) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        for name, v in values.items():
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, int(v))
    _notify()


def _notify() -> None:
    """Tell running Explorer windows that shell settings changed."""
    user32 = ctypes.windll.user32
    result = wintypes.DWORD()
    user32.SendMessageTimeoutW(
        0xFFFF, 0x001A, 0, "ShellState", 0x0002, 2000, ctypes.byref(result)
    )  # HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED


def presenting() -> bool:
    return STATE_FILE.exists()


def on(frequent: bool) -> dict[str, int]:
    """Hide. Remembers the previous values so `off` restores exactly."""
    before = read()
    if not presenting():
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(before), encoding="utf-8")
    hide = {"ShowRecent": 0}
    if frequent:
        hide["ShowFrequent"] = 0
    _write(hide)
    return read()


def off() -> dict[str, int]:
    """Show again: restore what `on` saved, or Windows' defaults."""
    restore = {name: 1 for name in VALUES}
    if presenting():
        try:
            restore = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        STATE_FILE.unlink(missing_ok=True)
    _write(restore)
    return read()


def restart_explorer() -> None:
    """Heavy hammer: Windows restarts the shell by itself. Open Explorer windows close."""
    subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], capture_output=True)
    for _ in range(10):  # Windows normally relaunches the shell itself (AutoRestartShell)
        time.sleep(0.5)
        running = subprocess.run(
            ["tasklist", "/fi", "imagename eq explorer.exe", "/nh"],
            capture_output=True, text=True,
        ).stdout
        if "explorer.exe" in running.lower():
            return
    subprocess.Popen(["explorer.exe"])

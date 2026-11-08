"""Run a prune at every logon: a shortcut in the user's Startup folder.

A Startup shortcut needs no admin rights (a logon-triggered scheduled task usually
does), runs after Explorer is up, and is removed by deleting one file. It points at
`recentctlw.exe`, the windowless entry point, so nothing flashes on screen; output
goes to %LOCALAPPDATA%\\recentctl\\last-run.txt.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pythoncom
from win32com.shell import shell

STARTUP = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
SHORTCUT = STARTUP / "recentctl-logon.lnk"
DEFAULT_ARGS = "prune -r -al -y"
STGM_READ = 0


def exe() -> str | None:
    """recentctlw.exe on PATH (installed with the package), else None."""
    return shutil.which("recentctlw")


def install(args: str = DEFAULT_ARGS) -> Path:
    target = exe()
    if not target:
        raise FileNotFoundError(
            "recentctlw.exe is not on PATH — reinstall recentctl "
            "(uv tool install --force recentctl, or -e <checkout>)")
    pythoncom.CoInitialize()
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    link.SetPath(target)
    link.SetArguments(args)
    link.SetWorkingDirectory(str(Path.home()))
    link.SetDescription("recentctl: prune recently-used lists at logon")
    STARTUP.mkdir(parents=True, exist_ok=True)
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(SHORTCUT), 0)
    return SHORTCUT


def remove() -> bool:
    if SHORTCUT.exists():
        SHORTCUT.unlink()
        return True
    return False


def status() -> tuple[str, str] | None:
    """(target, arguments) of the installed shortcut, or None."""
    if not SHORTCUT.exists():
        return None
    pythoncom.CoInitialize()
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(SHORTCUT), STGM_READ)
    target, _ = link.GetPath(0)
    return target, link.GetArguments()

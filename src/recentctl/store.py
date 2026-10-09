"""Read and delete entries in Explorer's Recent list.

Explorer's Home page renders its Recent section from the shortcut files in
%APPDATA%\\Microsoft\\Windows\\Recent (the 20 newest file targets). Deleting a
shortcut removes the entry; see specs/recentctl.md for how that was established.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pythoncom
import win32com.client
from win32com.shell import shell, shellcon

RECENT_DIR = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Recent"
# "Recent Items Instance Folder" — exactly what Home shows under Recent.
HOME_RECENT_NS = "shell:::{4564b25e-30cd-4787-82ba-39e73a750b14}"

FILE_ATTRIBUTE_DIRECTORY = 0x10
STGM_READ = 0


@dataclass
class Entry:
    lnk: Path
    name: str
    target: str
    kind: str  # file | folder | other
    opened: datetime
    visible: bool = False

    @property
    def age(self) -> timedelta:
        return datetime.now() - self.opened

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "target": self.target,
            "kind": self.kind,
            "opened": self.opened.isoformat(timespec="seconds"),
            "visible": self.visible,
            "lnk": str(self.lnk),
        }


def _attributes(lnk: Path) -> int:
    """FileAttributes from the .lnk header (offset 0x18) — no access to the target."""
    with open(lnk, "rb") as f:
        head = f.read(0x1C)
    if len(head) < 0x1C:
        return 0
    return struct.unpack_from("<I", head, 0x18)[0]


def _target(lnk: Path) -> str:
    """The stored target, without resolving it (so offline shares don't stall us)."""
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
    )
    link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(lnk), STGM_READ)
    try:
        target, _ = link.GetPath(shell.SLGP_RAWPATH)
    except pythoncom.com_error:
        target = ""
    if target:
        return target
    # URLs and shell items have no file path; ask for the parsing name instead.
    try:
        pidl = link.GetIDList()
        return shell.SHGetNameFromIDList(pidl, shellcon.SIGDN_DESKTOPABSOLUTEPARSING)
    except Exception:
        return ""


def _kind(attrs: int, target: str) -> str:
    if attrs & FILE_ATTRIBUTE_DIRECTORY:
        return "folder"
    if len(target) > 2 and (target[1] == ":" or target.startswith("\\\\")):
        return "file"
    return "other"


def visible_lnks() -> set[str]:
    """Lower-cased .lnk paths of the entries Home currently shows."""
    folder = win32com.client.Dispatch("Shell.Application").Namespace(HOME_RECENT_NS)
    if folder is None:
        return set()
    return {item.Path.lower() for item in folder.Items()}


def load(recent_dir: Path = RECENT_DIR) -> list[Entry]:
    """All Recent entries, newest first."""
    pythoncom.CoInitialize()
    shown = visible_lnks() if recent_dir == RECENT_DIR else set()
    entries = []
    for lnk in recent_dir.glob("*.lnk"):
        try:
            target = _target(lnk)
            attrs = _attributes(lnk)
            opened = datetime.fromtimestamp(lnk.stat().st_mtime)
        except (OSError, pythoncom.com_error):
            continue
        entries.append(
            Entry(
                lnk=lnk,
                name=lnk.stem,
                target=target,
                kind=_kind(attrs, target),
                opened=opened,
                visible=str(lnk).lower() in shown,
            )
        )
    entries.sort(key=lambda e: e.opened, reverse=True)
    return entries


def remove(entry: Entry) -> None:
    entry.lnk.unlink()

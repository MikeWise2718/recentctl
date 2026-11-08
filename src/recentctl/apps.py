"""Recently-used lists kept by applications: Microsoft Office and VLC.

Each app keeps its own list, separate from Explorer's Recent folder, so pruning
Explorer leaves them untouched. All of them are rewritten by the app when it
exits, so an app that is running is skipped: editing its list would be undone.

Office (Word, Excel, PowerPoint, ... 16.0 = 2016/2019/2021/365):
    HKCU\\Software\\Microsoft\\Office\\16.0\\<App>\\User MRU\\<account>\\File MRU
    HKCU\\Software\\Microsoft\\Office\\16.0\\<App>\\User MRU\\<account>\\Place MRU
    (and the same two keys directly under <App> for the account-less list)
    values "Item N" = "[F00000000][T<FILETIME hex>][O00000000]*<path>",
    optional "Item Metadata N" alongside.
VLC:
    %APPDATA%\\vlc\\vlc-qt-interface.ini, section [RecentsMRL]:
    list=<uri>, <uri>, ...   times=<ms>, <ms>, ...   (parallel; commas inside
    a URI are percent-encoded, so ", " splits safely)
"""

from __future__ import annotations

import os
import re
import subprocess
import winreg
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

OFFICE_ROOT = r"Software\Microsoft\Office\16.0"
VLC_INI = Path(os.environ.get("APPDATA", "")) / "vlc" / "vlc-qt-interface.ini"

# app name -> the process that rewrites its list on exit
OFFICE_EXE = {
    "word": "winword.exe", "excel": "excel.exe", "powerpoint": "powerpnt.exe",
    "access": "msaccess.exe", "visio": "visio.exe", "publisher": "mspub.exe",
    "onenote": "onenote.exe", "project": "winproj.exe",
}
APPS = [*OFFICE_EXE, "vlc"]

_ITEM_RE = re.compile(r"^Item (\d+)$")
_VALUE_RE = re.compile(r"\[T([0-9A-Fa-f]{16})\].*?\*(.+)$")
_EPOCH_DIFF = 116444736000000000  # 1601-01-01 to 1970-01-01 in 100 ns ticks


@dataclass
class AppItem:
    app: str      # word | excel | ... | vlc
    list: str     # files | places | media
    target: str
    opened: datetime | None
    kind: str     # file | folder | other
    where: str    # registry key or ini path, for removal and display
    slot: int     # Office: the N in "Item N"; VLC: index in the list
    visible: bool = False

    @property
    def name(self) -> str:
        return re.split(r"[\\/]", self.target.rstrip("\\/"))[-1] or self.target

    @property
    def age(self) -> timedelta:
        return datetime.now() - self.opened if self.opened else timedelta(0)

    def as_dict(self) -> dict:
        return {
            "app": self.app, "list": self.list, "name": self.name, "target": self.target,
            "kind": self.kind,
            "opened": self.opened.isoformat(timespec="seconds") if self.opened else None,
            "where": self.where, "slot": self.slot,
        }


@dataclass
class Report:
    items: list[AppItem] = field(default_factory=list)
    running: set[str] = field(default_factory=set)   # apps skipped because running


# ---------------------------------------------------------------- processes

def running_exes() -> set[str]:
    """Lower-cased image names of running processes (no console window flashes)."""
    try:
        out = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
        ).stdout
    except OSError:
        return set()
    return {line.split('","')[0].strip('"').lower() for line in out.splitlines() if line}


def app_running(app: str, procs: set[str]) -> bool:
    exe = "vlc.exe" if app == "vlc" else OFFICE_EXE.get(app, "")
    return exe in procs


# ---------------------------------------------------------------- Office

def filetime(hex16: str) -> datetime | None:
    ticks = int(hex16, 16)
    if ticks <= _EPOCH_DIFF:
        return None
    return datetime.fromtimestamp((ticks - _EPOCH_DIFF) / 10_000_000)


def parse_office_value(value: str) -> tuple[datetime | None, str] | None:
    m = _VALUE_RE.search(value)
    if not m:
        return None
    return filetime(m.group(1)), m.group(2)


def _subkeys(root: int, path: str) -> list[str]:
    try:
        with winreg.OpenKey(root, path) as k:
            n = winreg.QueryInfoKey(k)[0]
            return [winreg.EnumKey(k, i) for i in range(n)]
    except OSError:
        return []


def _values(root: int, path: str) -> dict[str, object]:
    try:
        with winreg.OpenKey(root, path) as k:
            n = winreg.QueryInfoKey(k)[1]
            return {name: data for name, data, _ in (winreg.EnumValue(k, i) for i in range(n))}
    except OSError:
        return {}


def office_lists(root: int = winreg.HKEY_CURRENT_USER,
                 base: str = OFFICE_ROOT) -> list[tuple[str, str, str]]:
    """(app, list, key path) for every File MRU / Place MRU key that exists."""
    found = []
    for sub in _subkeys(root, base):
        app = sub.lower()
        if app not in OFFICE_EXE:
            continue
        parents = [f"{base}\\{sub}"]
        parents += [f"{base}\\{sub}\\User MRU\\{acct}"
                    for acct in _subkeys(root, f"{base}\\{sub}\\User MRU")]
        for parent in parents:
            present = set(_subkeys(root, parent))
            for leaf, kind in (("File MRU", "files"), ("Place MRU", "places")):
                if leaf in present:
                    found.append((app, kind, f"{parent}\\{leaf}"))
    return found


def load_office(root: int = winreg.HKEY_CURRENT_USER, base: str = OFFICE_ROOT) -> list[AppItem]:
    items = []
    for app, lst, path in office_lists(root, base):
        for name, data in _values(root, path).items():
            m = _ITEM_RE.match(name)
            if not m or not isinstance(data, str):
                continue
            parsed = parse_office_value(data)
            if not parsed:
                continue
            opened, target = parsed
            items.append(AppItem(
                app=app, list=lst, target=target, opened=opened,
                kind="folder" if lst == "places" else "file",
                where=path, slot=int(m.group(1)),
            ))
    return items


def remove_office(path: str, slots: set[int], root: int = winreg.HKEY_CURRENT_USER) -> int:
    """Drop "Item N" (and "Item Metadata N") for each N in slots; renumber the rest 1..n."""
    vals = _values(root, path)
    keep = sorted(
        (int(m.group(1)), name) for name in vals
        if (m := _ITEM_RE.match(name)) and int(m.group(1)) not in slots
    )
    removed = sum(1 for name in vals if (m := _ITEM_RE.match(name)) and int(m.group(1)) in slots)
    with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as k:
        old = {}
        for name in list(vals):
            if _ITEM_RE.match(name) or name.startswith("Item Metadata "):
                old[name] = winreg.QueryValueEx(k, name)
                winreg.DeleteValue(k, name)
        for new_n, (old_n, name) in enumerate(keep, start=1):
            data, typ = old[name]
            winreg.SetValueEx(k, f"Item {new_n}", 0, typ, data)
            meta = f"Item Metadata {old_n}"
            if meta in old:
                mdata, mtyp = old[meta]
                winreg.SetValueEx(k, f"Item Metadata {new_n}", 0, mtyp, mdata)
    return removed


# ---------------------------------------------------------------- VLC

def uri_to_path(uri: str) -> tuple[str, str]:
    """file:///C:/x -> C:\\x, file://host/share/x -> \\\\host\\share\\x; others unchanged.

    Returns (target, kind)."""
    if not uri.lower().startswith("file:"):
        return uri, "other"
    parts = urlsplit(uri)
    path = unquote(parts.path)
    if parts.netloc:
        return "\\\\" + parts.netloc + path.replace("/", "\\"), "file"
    path = path.lstrip("/")
    return path.replace("/", "\\"), "file"


def _split_list(value: str) -> list[str]:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    if not value or value == "@Invalid()":
        return []
    return value.split(", ")


def _read_vlc(ini: Path) -> tuple[list[str], int, int] | None:
    """(lines, index of the list= line, index of times= or -1); None when there is no list."""
    if not ini.exists():
        return None
    text = ini.read_bytes().decode("utf-8")  # bytes: keep the file's own line endings
    lines = text.splitlines(keepends=True)
    section = ""
    li = ti = -1
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s
        elif section == "[RecentsMRL]":
            if s.startswith("list="):
                li = i
            elif s.startswith("times="):
                ti = i
    if li < 0:
        return None
    return lines, li, ti


def load_vlc(ini: Path = VLC_INI) -> list[AppItem]:
    got = _read_vlc(ini)
    if not got:
        return []
    lines, li, _ = got
    items = []
    for i, uri in enumerate(_split_list(lines[li].strip()[len("list="):])):
        target, kind = uri_to_path(uri)
        items.append(AppItem(app="vlc", list="media", target=target, opened=None, kind=kind,
                             where=str(ini), slot=i))
    return items


def remove_vlc(slots: set[int], ini: Path = VLC_INI) -> int:
    got = _read_vlc(ini)
    if not got:
        return 0
    lines, li, ti = got

    def rewrite(idx: int, key: str) -> None:
        line = lines[idx]
        eol = line[len(line.rstrip("\r\n")):]
        vals = _split_list(line.strip()[len(key) + 1:])
        kept = [v for n, v in enumerate(vals) if n not in slots]
        lines[idx] = f"{key}={', '.join(kept) if kept else '@Invalid()'}{eol}"

    before = len(_split_list(lines[li].strip()[len("list="):]))
    rewrite(li, "list")
    if ti >= 0:
        rewrite(ti, "times")
    after = len(_split_list(lines[li].strip()[len("list="):]))
    ini.write_text("".join(lines), encoding="utf-8", newline="")
    return before - after


# ---------------------------------------------------------------- together

def load(apps: list[str] | None = None) -> Report:
    """Every app list item, newest first (VLC has no times; it keeps its own order)."""
    want = set(apps or APPS)
    procs = running_exes()
    rep = Report()
    if want & set(OFFICE_EXE):
        rep.items += [it for it in load_office() if it.app in want]
    if "vlc" in want:
        rep.items += load_vlc()
    rep.running = {it.app for it in rep.items if app_running(it.app, procs)}
    rep.items.sort(key=lambda it: (it.app, it.list,
                                   -(it.opened.timestamp() if it.opened else 0), it.slot))
    return rep


def remove(items: list[AppItem]) -> dict[str, int]:
    """Remove the given items, batched per list. Returns removed counts per app."""
    by_where: dict[tuple[str, str], set[int]] = {}
    for it in items:
        by_where.setdefault((it.app, it.where), set()).add(it.slot)
    counts: dict[str, int] = {}
    for (app, where), slots in by_where.items():
        n = remove_vlc(slots, Path(where)) if app == "vlc" else remove_office(where, slots)
        counts[app] = counts.get(app, 0) + n
    return counts

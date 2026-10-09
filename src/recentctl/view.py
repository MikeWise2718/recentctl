"""Colours and small formatting helpers shared by every command."""

from __future__ import annotations

import ntpath
from datetime import datetime, timedelta

from rich.text import Text

from .store import Entry

# extension -> category; category -> style
CATEGORIES: dict[str, tuple[str, set[str]]] = {
    "image": ("bright_green", {"png", "jpg", "jpeg", "gif", "webp", "heic", "bmp", "svg", "tif", "tiff", "ico"}),
    "video": ("bright_magenta", {"mp4", "mkv", "mov", "avi", "webm", "wmv", "m4v"}),
    "audio": ("magenta", {"mp3", "wav", "flac", "m4a", "ogg", "aac"}),
    "text": ("bright_cyan", {"md", "txt", "log", "rtf", "odt", "pdf", "doc", "docx"}),
    "office": ("dodger_blue1", {"xlsx", "xls", "csv", "pptx", "ppt", "msg", "eml", "one", "vsdx"}),
    "code": ("yellow", {"py", "js", "ts", "tsx", "json", "toml", "yaml", "yml", "ps1", "bat", "cmd",
                        "sh", "html", "htm", "css", "c", "cpp", "h", "cs", "ipynb", "xml", "ini", "cfg"}),
    "archive": ("orange3", {"zip", "7z", "rar", "tar", "gz", "iso"}),
    "binary": ("red", {"exe", "msi", "dll", "lnk", "apk"}),
}
EXT_CATEGORY = {ext: cat for cat, (_, exts) in CATEGORIES.items() for ext in exts}
CATEGORY_STYLE = {cat: style for cat, (style, _) in CATEGORIES.items()}
CATEGORY_STYLE.update({"folder": "bold gold1", "web/app": "orchid", "other": "white"})

KIND_STYLE = {"file": "bright_cyan", "folder": "bold gold1", "other": "orchid"}

BAR_STYLES = ["bright_cyan", "bright_magenta", "bright_green", "gold1", "dodger_blue1",
              "orange3", "orchid", "spring_green2", "deep_pink2", "turquoise2"]


def extension(e: Entry) -> str:
    if e.kind == "folder":
        return "(folder)"
    if e.kind == "other":
        scheme = e.target.split(":", 1)[0].lower() if ":" in e.target else ""
        return f"({scheme or 'shell'})"
    ext = ntpath.splitext(e.target)[1].lstrip(".").lower()
    return f".{ext}" if ext else "(none)"


def category(e: Entry) -> str:
    if e.kind == "folder":
        return "folder"
    if e.kind == "other":
        return "web/app"
    return EXT_CATEGORY.get(extension(e).lstrip("."), "other")


def style_of(e: Entry) -> str:
    return CATEGORY_STYLE.get(category(e), "white")


def tz_name(dt: datetime) -> str:
    """Short zone name. Windows reports long ones ("W. Europe Daylight Time"), so map those."""
    dt = dt.astimezone() if dt.tzinfo is None else dt
    name = dt.tzname() or ""
    if name and len(name) <= 5 and " " not in name:
        return name
    off = int(dt.utcoffset().total_seconds()) if dt.utcoffset() is not None else 0
    if off == 0:
        return "UTC"
    if "Europe" in name and off in (3600, 7200):
        return "CET" if off == 3600 else "CEST"
    sign = "+" if off >= 0 else "-"
    h, m = divmod(abs(off) // 60, 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


def stamp(dt: datetime) -> str:
    """2026-10-09 13:18 CEST — 24-hour clock with the zone."""
    return f"{dt:%Y-%m-%d %H:%M} {tz_name(dt)}"


def age_text(td: timedelta) -> str:
    s = int(td.total_seconds())
    if s < 3600:
        return f"{s // 60}min"
    if s < 86400:
        return f"{s // 3600}h"
    if s < 86400 * 60:
        return f"{s // 86400}d"
    return f"{s // (86400 * 30)}mo"


def age_style(td: timedelta) -> str:
    """Heat scale: fresh is bright green, old fades through yellow and orange to red."""
    d = td.total_seconds() / 86400
    if d < 1:
        return "bold bright_green"
    if d < 7:
        return "green"
    if d < 30:
        return "yellow"
    if d < 90:
        return "orange3"
    if d < 365:
        return "red"
    return "bold red3"


def age_cell(e: Entry) -> Text:
    return Text(age_text(e.age), style=age_style(e.age))


def name_cell(e: Entry) -> Text:
    return Text(e.name, style=style_of(e))


def kind_cell(e: Entry) -> Text:
    return Text(e.kind, style=KIND_STYLE.get(e.kind, "white"))


def target_cell(e: Entry) -> Text:
    """Directory dim, last component in the entry's colour."""
    t = e.target
    if e.kind == "other" or not t:
        return Text(t, style="orchid")
    head, tail = ntpath.split(t.rstrip("\\"))
    out = Text(head + ("\\" if head and not head.endswith("\\") else ""), style="grey50")
    out.append(tail, style=style_of(e))
    return out


def bar(fraction: float, width: int, style: str) -> Text:
    """A horizontal bar with eighth-block resolution."""
    blocks = " ▏▎▍▌▋▊▉█"
    cells = max(0.0, min(1.0, fraction)) * width
    full, rem = int(cells), int((cells - int(cells)) * 8)
    s = "█" * full + (blocks[rem] if rem and full < width else "")
    return Text(s.ljust(width), style=style)

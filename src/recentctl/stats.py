"""Group Recent entries for `recentctl stats`."""

from __future__ import annotations

import ntpath
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from .store import Entry
from .view import category, extension

PROFILE = os.environ.get("USERPROFILE", "").rstrip("\\").lower()

AGE_BUCKETS = [  # (upper bound in days, label)
    (1, "< 1 day"),
    (7, "1–7 days"),
    (30, "1–4 weeks"),
    (90, "1–3 months"),
    (365, "3–12 months"),
    (float("inf"), "> 1 year"),
]


def root(e: Entry, depth: int = 1) -> str:
    """Where an entry lives, `depth` components below its drive/share/profile.

    C:\\Users\\alice\\Videos\\x.mp4 -> ~\\Videos;  D:\\Work\\proj\\a.md -> D:\\Work;
    \\\\server\\share\\a\\b -> \\\\server\\share\\a;  https://host/... -> https://host
    """
    t = e.target
    if e.kind == "other" or not t:
        if "://" in t:
            scheme, rest = t.split("://", 1)
            host = rest.split("/", 1)[0].split("?", 1)[0]
            return f"{scheme}://{host}" if host else f"{scheme}:"
        return (t.split(":", 1)[0] + ":") if ":" in t else "(shell item)"
    if e.kind == "file":
        t = ntpath.dirname(t)
    t = t.rstrip("\\")
    if PROFILE and (t.lower() == PROFILE or t.lower().startswith(PROFILE + "\\")):
        base, rest = "~", t[len(PROFILE):]
    else:
        drive, rest = ntpath.splitdrive(t)
        base = drive or "?"
    parts = [p for p in rest.split("\\") if p]
    return "\\".join([base, *parts[:depth]]) if parts else base + "\\"


def age_bucket(e: Entry) -> str:
    days = e.age.total_seconds() / 86400
    return next(label for limit, label in AGE_BUCKETS if days < limit)


def month(e: Entry) -> str:
    return e.opened.strftime("%Y-%m")


@dataclass
class Group:
    key: str
    count: int = 0
    visible: int = 0
    newest: datetime | None = None
    sample: Entry | None = None  # for colouring the row
    targets: set = field(default_factory=set)


def group(entries: list[Entry], keyfn: Callable[[Entry], str]) -> list[Group]:
    groups: dict[str, Group] = defaultdict(lambda: Group(""))
    for e in entries:
        k = keyfn(e)
        g = groups[k]
        g.key = k
        g.count += 1
        g.visible += e.visible
        g.targets.add(e.target.lower())
        if g.newest is None or e.opened > g.newest:
            g.newest = e.opened
            g.sample = e
    return sorted(groups.values(), key=lambda g: (-g.count, g.key))


GROUPINGS: dict[str, tuple[str, Callable[[Entry, int], str]]] = {
    "kind": ("Kind", lambda e, d: e.kind),
    "category": ("Category", lambda e, d: category(e)),
    "ext": ("Extension", lambda e, d: extension(e)),
    "root": ("Root directory", root),
    "age": ("Last opened", lambda e, d: age_bucket(e)),
    "month": ("Month opened", lambda e, d: month(e)),
}
ORDERED = {"age": [label for _, label in AGE_BUCKETS]}  # natural order instead of by count

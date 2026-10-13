"""Quick access folders (pinned + frequent) on Explorer's Home page.

Unlike the Recent list, these live in a jump-list file
(AutomaticDestinations\\f01b4d95cf55d32a…), and the shell's own verbs do work from a
script: "Remove from Quick access" for frequent folders, "Unpin from Quick access" for
pinned ones. When a frequent folder goes, Windows promotes the next one, so pruning
repeats until nothing matching is left. Verb names are matched in English.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import pythoncom
import win32com.client

from .rules import Rules, matches

QUICK_NS = "shell:::{3936E9E4-D92C-4EEE-A85A-BC16D5EA0819}"
REMOVE = "remove from quick access"
UNPIN = "unpin from quick access"
MAX_PASSES = 10


@dataclass
class QuickItem:
    name: str
    target: str
    pinned: bool
    kind: str = "folder"  # lets the Recent-list pattern matching work unchanged

    def as_dict(self) -> dict:
        return {"name": self.name, "target": self.target, "pinned": self.pinned}


def _verbs(item) -> dict:
    return {v.Name.replace("&", "").strip().lower(): v for v in item.Verbs()}


def _folder():
    pythoncom.CoInitialize()
    return win32com.client.Dispatch("Shell.Application").Namespace(QUICK_NS)


def load() -> list[QuickItem]:
    folder = _folder()
    if folder is None:
        return []
    return [QuickItem(it.Name, it.Path, UNPIN in _verbs(it)) for it in folder.Items()]


def remove(target: str) -> bool:
    """Remove (frequent) or unpin (pinned) the folder with this path. True if a verb ran."""
    folder = _folder()
    for it in folder.Items():
        if it.Path.lower() == target.lower():
            verbs = _verbs(it)
            verb = verbs.get(REMOVE) or verbs.get(UNPIN)
            if verb is None:
                return False
            verb.DoIt()
            return True
    return False


def reason(item: QuickItem, patterns: list[str], rules: Rules | None) -> str | None:
    """Why this folder is selected: an -m pattern, or a rules-file `private` pattern.

    Quick access has no last-opened time, so ages and `max_age` don't apply.
    """
    if rules is not None and rules.kept(item):
        return None
    hits = [p for p in patterns if matches(p, item)]
    if hits:
        return "match: " + ", ".join(hits)
    if rules is not None:
        for p in rules.private:
            if matches(p, item):
                return f"private: {p}"
    return None


def select(
    items: list[QuickItem], patterns: list[str], rules: Rules | None, include_pinned: bool
) -> tuple[list[tuple[QuickItem, str]], list[QuickItem]]:
    """(selected, matching-but-pinned-and-skipped)."""
    picked, skipped = [], []
    for it in items:
        why = reason(it, patterns, rules)
        if not why:
            continue
        if it.pinned and not include_pinned:
            skipped.append(it)
        else:
            picked.append((it, why))
    return picked, skipped


def prune(
    choose: Callable[[list[QuickItem]], list[tuple[QuickItem, str]]],
    on_removed: Callable[[QuickItem, str], None],
) -> tuple[int, int]:
    """Remove until nothing chosen is left (Windows backfills). Returns (removed, failed)."""
    removed = failed = 0
    tried: set[str] = set()
    for _ in range(MAX_PASSES):
        todo = [(it, why) for it, why in choose(load()) if it.target.lower() not in tried]
        if not todo:
            break
        for it, why in todo:
            tried.add(it.target.lower())
            if remove(it.target):
                removed += 1
                on_removed(it, why)
            else:
                failed += 1
        time.sleep(1.0)  # let Explorer rewrite the list before looking again
    return removed, failed

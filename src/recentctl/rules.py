"""Matching: patterns, ages, and the rules file."""

from __future__ import annotations

import fnmatch
import re
import tomllib
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from .store import Entry
from .view import category

DEFAULT_RULES = Path.home() / ".config" / "recentctl" / "rules.toml"

_UNITS = {"min": "minutes", "h": "hours", "d": "days", "w": "weeks"}
_AGE_RE = re.compile(r"^\s*(\d+)\s*(min|h|d|w|y)\s*$", re.IGNORECASE)


def parse_age(text: str) -> timedelta:
    """'90min', '12h', '30d', '6w', '1y' -> timedelta."""
    m = _AGE_RE.match(text)
    if not m:
        raise ValueError(f"bad age {text!r} — use e.g. 90min, 12h, 30d, 6w, 1y")
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit == "y":
        return timedelta(days=365 * n)
    return timedelta(**{_UNITS[unit]: n})


def matches(pattern: str, entry: Entry) -> bool:
    """Case-insensitive. Wildcards (* ? [) -> glob over target and name; else substring.

    `*` also crosses backslashes, so 'D:\\Private\\*' covers everything below it.
    """
    p = pattern.lower()
    hay = (entry.target.lower(), entry.name.lower())
    if any(c in p for c in "*?["):
        return any(fnmatch.fnmatchcase(h, p) for h in hay)
    return any(p in h for h in hay)


@dataclass
class Rules:
    private: list[str] = field(default_factory=list)
    keep: list[str] = field(default_factory=list)
    max_age: timedelta | None = None
    max_age_text: str = ""
    path: Path | None = None

    @classmethod
    def load(cls, path: Path) -> "Rules":
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        max_age_text = data.get("max_age", "") or ""
        return cls(
            private=list(data.get("private", [])),
            keep=list(data.get("keep", [])),
            max_age=parse_age(max_age_text) if max_age_text else None,
            max_age_text=max_age_text,
            path=path,
        )

    def kept(self, entry: Entry) -> bool:
        return any(matches(p, entry) for p in self.keep)

    def reason(self, entry: Entry) -> str | None:
        """Why the rules select this entry, or None. `keep` is checked by the caller."""
        for p in self.private:
            if matches(p, entry):
                return f"private: {p}"
        if self.max_age is not None and entry.age > self.max_age:
            return f"older than {self.max_age_text}"
        return None


@dataclass
class Filters:
    patterns: list[str] = field(default_factory=list)
    older_than: timedelta | None = None
    newer_than: timedelta | None = None
    kinds: list[str] = field(default_factory=list)
    older_text: str = ""
    newer_text: str = ""
    categories: list[str] = field(default_factory=list)

    @property
    def selects_anything(self) -> bool:
        return bool(self.patterns or self.older_than or self.newer_than or self.categories)

    def accept(self, entry: Entry) -> bool:
        if self.kinds and entry.kind not in self.kinds:
            return False
        if self.categories and category(entry) not in self.categories:
            return False
        if self.patterns and not any(matches(p, entry) for p in self.patterns):
            return False
        if self.older_than is not None and entry.age <= self.older_than:
            return False
        if self.newer_than is not None and entry.age >= self.newer_than:
            return False
        return True

    def reason(self) -> str:
        parts = []
        if self.categories:
            parts.append(" or ".join(self.categories))
        if self.patterns:
            parts.append("match: " + ", ".join(self.patterns))
        if self.older_than is not None:
            parts.append(f"older than {self.older_text}")
        if self.newer_than is not None:
            parts.append(f"newer than {self.newer_text}")
        return "; ".join(parts) or "filter"


def select(
    entries: list[Entry], filters: Filters, rules: Rules | None, *, union: bool
) -> list[tuple[Entry, str]]:
    """Pick entries.

    union=False (list): the filters narrow; with rules, only rule hits are shown.
    union=True (prune): an entry goes if the filters select it OR the rules do.
    `keep` patterns always win, and `kinds` always narrows.
    """
    picked = []
    for e in entries:
        if filters.kinds and e.kind not in filters.kinds:
            continue
        if rules is not None and rules.kept(e):
            continue
        rule_reason = rules.reason(e) if rules is not None else None
        if union:
            if filters.selects_anything and filters.accept(e):
                picked.append((e, filters.reason()))
            elif rule_reason:
                picked.append((e, rule_reason))
        else:
            if not filters.accept(e):
                continue
            if rules is not None and not rule_reason:
                continue
            picked.append((e, rule_reason or ""))
    return picked

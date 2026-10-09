"""recentctl — dump, count and prune Explorer's Recent list; hide it while presenting."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich_argparse import RawDescriptionRichHelpFormatter

from . import __version__, stats, store, switch, view
from .rules import DEFAULT_RULES, Filters, Rules, parse_age, select

console = Console(highlight=False)
LOG_FILE = Path(os.environ["LOCALAPPDATA"]) / "recentctl" / "events.jsonl"

RawDescriptionRichHelpFormatter.styles.update({
    "argparse.prog": "bold bright_magenta",
    "argparse.args": "bold bright_cyan",
    "argparse.groups": "bold gold1",
    "argparse.metavar": "spring_green2",
    "argparse.help": "default",
    "argparse.text": "italic grey70",
    "argparse.syntax": "bold orchid",
})
RawDescriptionRichHelpFormatter.highlights.append(r"(?P<syntax>`[^`]+`)")

EXAMPLES = [
    ("recentctl list -vo", "what Explorer Home shows right now"),
    ("recentctl list -l 50", "the 50 newest entries of the full history"),
    ("recentctl list -m payslip -m *.mp4", "anything matching either pattern"),
    ("recentctl list -ot 6w -k file", "files not opened for 6 weeks"),
    ("recentctl list -ct image -ct video", "only pictures and videos"),
    ("recentctl list -r", "what the rules file would remove, and why"),
    ("recentctl stats", "counts by kind, category, extension, root dir, age"),
    ("recentctl stats -by root -dp 2 -t 30", "top 30 directories, two levels deep"),
    ("recentctl stats -m D:\\Work\\*", "statistics for one tree only"),
    ("recentctl prune -ot 60d", "DRY RUN: entries not opened for 60 days"),
    ("recentctl prune -r -y", "apply the rules file for real"),
    ("recentctl present on -f", "hide Recent + frequent folders for a screen share"),
    ("recentctl present off", "show them again"),
]
EPILOG = "examples:\n" + "\n".join(f"  `{c}`\n      {d}" for c, d in EXAMPLES) + """

patterns: case-insensitive; with * ? [ they are globs over the target path and the name
(* crosses backslashes, so D:\\Private\\* is the whole tree); otherwise a substring.
ages: 90min, 12h, 30d, 6w, 1y — counted from when the item was last opened.
`recentctl help` shows the illustrated overview."""


# ---------------------------------------------------------------- shared pieces

def _unquote(pattern: str) -> str:
    """cmd.exe passes single quotes through literally; no path contains them at both ends."""
    if len(pattern) >= 2 and pattern[0] == pattern[-1] and pattern[0] in "'\"":
        return pattern[1:-1]
    return pattern


def _filters(a: argparse.Namespace) -> Filters:
    try:
        return Filters(
            patterns=[_unquote(p) for p in a.match or []],
            older_than=parse_age(a.older_than) if a.older_than else None,
            newer_than=parse_age(a.newer_than) if a.newer_than else None,
            kinds=a.kind or [],
            older_text=a.older_than or "",
            newer_text=a.newer_than or "",
            categories=a.category or [],
        )
    except ValueError as exc:
        console.print(f"[bold red]✗[/] [red]{exc}[/]")
        sys.exit(2)


def _rules(a: argparse.Namespace) -> Rules | None:
    if not getattr(a, "rules", False):
        return None
    path = Path(a.rules_file) if a.rules_file else DEFAULT_RULES
    if not path.exists():
        console.print(
            f"[bold red]✗[/] No rules file at [bright_cyan]{path}[/] — copy "
            "[spring_green2]rules.example.toml[/] there to start."
        )
        sys.exit(2)
    try:
        return Rules.load(path)
    except (ValueError, OSError) as exc:
        console.print(f"[bold red]✗[/] Bad rules file [bright_cyan]{path}[/]: [red]{exc}[/]")
        sys.exit(2)


def _load() -> list[store.Entry]:
    with console.status("[bright_cyan]Reading the Recent list…[/]", spinner="dots"):
        return store.load()


def _table(rows: list[tuple[store.Entry, str]], show_reason: bool, title: str = "") -> Table:
    t = Table(box=box.ROUNDED, header_style="bold white on dark_blue", border_style="blue",
              title=title or None, title_style="bold bright_magenta", pad_edge=False)
    t.add_column("H", justify="center", no_wrap=True)
    t.add_column("opened", no_wrap=True, style="grey62")
    t.add_column("age", justify="right", no_wrap=True)
    t.add_column("kind", no_wrap=True)
    t.add_column("name", overflow="fold")
    t.add_column("target", overflow="fold")
    if show_reason:
        t.add_column("why", overflow="fold", style="bold deep_pink2")
    for e, why in rows:
        cells = [
            Text("●", style="bold bright_yellow") if e.visible else Text(""),
            view.stamp(e.opened),
            view.age_cell(e),
            view.kind_cell(e),
            view.name_cell(e),
            view.target_cell(e),
        ]
        if show_reason:
            cells.append(why)
        t.add_row(*cells)
    return t


def _legend() -> Text:
    out = Text("colours: ", style="grey50")
    for cat, style in view.CATEGORY_STYLE.items():
        out.append(f"■ {cat}  ", style=style)
    out.append("· age: ", style="grey50")
    for label, style in [("<1d", "bold bright_green"), ("<1w", "green"), ("<1mo", "yellow"),
                         ("<3mo", "orange3"), ("<1y", "red"), ("older", "bold red3")]:
        out.append(f"{label} ", style=style)
    return out


# ---------------------------------------------------------------- list

def cmd_list(a: argparse.Namespace) -> int:
    entries = _load()
    rules = _rules(a)
    rows = select(entries, _filters(a), rules, union=False)
    if a.visible_only:
        rows = [(e, w) for e, w in rows if e.visible]
    if a.limit:
        rows = rows[: a.limit]
    if a.json:
        print(json.dumps([dict(e.as_dict(), why=w) for e, w in rows], indent=2))
        return 0
    console.print(_table(rows, show_reason=rules is not None))
    shown = sum(1 for e in entries if e.visible)
    console.print(
        f"[bold bright_cyan]{len(rows)}[/] of [bold]{len(entries)}[/] entries · "
        f"[bold bright_yellow]●[/] = visible in Explorer Home ([bright_yellow]{shown}[/] now)"
    )
    console.print(_legend())
    return 0


# ---------------------------------------------------------------- stats

def _summary(entries: list[store.Entry]) -> Panel:
    kinds = {k: sum(1 for e in entries if e.kind == k) for k in ("file", "folder", "other")}
    distinct = len({e.target.lower() for e in entries})
    visible = sum(1 for e in entries if e.visible)
    grid = Table.grid(padding=(0, 3))
    grid.add_column(justify="right", style="grey70")
    grid.add_column()
    grid.add_column(justify="right", style="grey70")
    grid.add_column()
    newest = max((e.opened for e in entries), default=None)
    oldest = min((e.opened for e in entries), default=None)
    span = f"{(newest - oldest).days} days" if newest and oldest else "—"
    fmt = lambda d: view.stamp(d) if d else "—"  # noqa: E731
    grid.add_row("entries", f"[bold bright_white]{len(entries)}[/]",
                 "visible in Home", f"[bold bright_yellow]● {visible}[/]")
    grid.add_row("files", f"[bright_cyan]{kinds['file']}[/]",
                 "distinct targets", f"[spring_green2]{distinct}[/]")
    grid.add_row("folders", f"[bold gold1]{kinds['folder']}[/]",
                 "duplicates", f"[deep_pink2]{len(entries) - distinct}[/]")
    grid.add_row("web/app", f"[orchid]{kinds['other']}[/]",
                 "history span", f"[dodger_blue1]{span}[/]")
    grid.add_row("newest", f"[bold bright_green]{fmt(newest)}[/]",
                 "oldest", f"[bold red3]{fmt(oldest)}[/]")
    return Panel(grid, title="[bold bright_magenta]Recent list[/]", border_style="bright_magenta",
                 box=box.ROUNDED, expand=False, subtitle=f"[grey50]{store.RECENT_DIR}[/]")


def _key_style(by: str, g: stats.Group, idx: int) -> str:
    if by == "kind":
        return view.KIND_STYLE.get(g.key, "white")
    if by == "category":
        return view.CATEGORY_STYLE.get(g.key, "white")
    if by == "ext" and g.sample is not None:
        return view.style_of(g.sample)
    if by == "age" and g.sample is not None:
        return view.age_style(g.sample.age)
    return view.BAR_STYLES[idx % len(view.BAR_STYLES)]


def _group_table(by: str, groups: list[stats.Group], total: int, top: int) -> Table:
    title, _ = stats.GROUPINGS[by]
    if by in stats.ORDERED:
        order = stats.ORDERED[by]
        groups = sorted(groups, key=lambda g: order.index(g.key))
    elif by == "month":
        groups = sorted(groups, key=lambda g: g.key, reverse=True)
    biggest = max((g.count for g in groups), default=1)
    width = 14 if by in ("kind", "category", "age") else 24
    t = Table(box=box.SIMPLE_HEAD, title=f"[bold]{title}[/]", title_justify="left",
              header_style="bold gold1", border_style="grey35", pad_edge=False)
    t.add_column(title.split()[0].lower(), overflow="fold")
    t.add_column("n", justify="right")
    t.add_column("%", justify="right", style="grey62")
    t.add_column("", no_wrap=True)
    t.add_column("●", justify="right", style="bright_yellow")
    t.add_column("last opened", style="grey62", no_wrap=True)
    for i, g in enumerate(groups[:top]):
        style = _key_style(by, g, i)
        t.add_row(
            Text(g.key, style=style),
            Text(str(g.count), style="bold"),
            f"{100 * g.count / total:.1f}",
            view.bar(g.count / biggest, width, style),
            str(g.visible or ""),
            view.age_text(datetime.now() - g.newest) + " ago" if g.newest else "",
        )
    if len(groups) > top:
        rest = sum(g.count for g in groups[top:])
        t.add_row(Text(f"… {len(groups) - top} more", style="italic grey50"),
                  Text(str(rest), style="grey50"), f"{100 * rest / total:.1f}", "", "", "")
    return t


def cmd_stats(a: argparse.Namespace) -> int:
    entries = _load()
    filters = _filters(a)
    entries = [e for e, _ in select(entries, filters, None, union=False)]
    if a.visible_only:
        entries = [e for e in entries if e.visible]
    if not entries:
        console.print("[yellow]No entries match.[/]")
        return 0
    by = a.by or ["kind", "category", "ext", "root", "age"]
    if a.json:
        out = {}
        for b in by:
            _, keyfn = stats.GROUPINGS[b]
            out[b] = [{"key": g.key, "count": g.count, "visible": g.visible,
                       "newest": g.newest.isoformat(timespec="seconds")}
                      for g in stats.group(entries, lambda e: keyfn(e, a.depth))]
        print(json.dumps({"total": len(entries), "groups": out}, indent=2))
        return 0

    console.print(_summary(entries))
    tables = []
    for b in by:
        _, keyfn = stats.GROUPINGS[b]
        groups = stats.group(entries, lambda e, f=keyfn: f(e, a.depth))
        tables.append(_group_table(b, groups, len(entries), a.top))
    small = [t for b, t in zip(by, tables) if b in ("kind", "category", "age")]
    large = [t for b, t in zip(by, tables) if b not in ("kind", "category", "age")]
    if small:
        console.print(Columns(small, padding=(0, 4)))
    for t in large:
        console.print(t)
    if filters.selects_anything or filters.kinds:
        console.print("[grey50]Scoped by your filters.[/]")
    return 0


# ---------------------------------------------------------------- prune

def _log(entry: store.Entry, why: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "event": "recent.removed",
        "message": f"removed {entry.name}",
        "why": why,
        **entry.as_dict(),
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cmd_prune(a: argparse.Namespace) -> int:
    filters = _filters(a)
    rules = _rules(a)
    if not filters.selects_anything and rules is None:
        console.print("[bold red]✗[/] prune needs [bright_cyan]-m[/], [bright_cyan]-ot[/]/"
                      "[bright_cyan]-nt[/], or [bright_cyan]-r[/] — refusing to remove everything")
        return 2
    entries = _load()
    rows = select(entries, filters, rules, union=True)
    if not rows:
        if not a.quiet:
            console.print("[bold bright_green]✓ Nothing to remove.[/]")
        return 0
    if not a.yes:
        console.print(_table(rows, show_reason=True, title="Would remove"))
        console.print(Panel(
            f"[bold gold1]DRY RUN[/] — would remove [bold deep_pink2]{len(rows)}[/] of "
            f"[bold]{len(entries)}[/] entries. Add [bold bright_cyan]-y[/] to do it.",
            border_style="gold1", expand=False))
        return 0
    removed = failed = 0
    for e, why in rows:
        try:
            store.remove(e)
            _log(e, why)
            removed += 1
        except OSError as exc:
            failed += 1
            console.print(f"[bold red]✗[/] could not remove [bright_cyan]{e.lnk.name}[/]: {exc}")
    if not a.quiet or failed:
        msg = f"[bold bright_green]✓ Removed {removed}[/] of {len(entries)} entries"
        if failed:
            msg += f", [bold red]{failed} failed[/]"
        console.print(msg + f"\n[grey50]log: {LOG_FILE}[/]")
    return 1 if failed else 0


# ---------------------------------------------------------------- present

def cmd_present(a: argparse.Namespace) -> int:
    if a.state == "on":
        vals = switch.on(frequent=a.frequent)
    elif a.state == "off":
        vals = switch.off()
    else:
        vals = switch.read()
    if a.restart_explorer and a.state != "status":
        with console.status("[bright_cyan]Restarting Explorer…[/]"):
            switch.restart_explorer()

    def word(v: int) -> str:
        return "[bold bright_green]shown[/]" if v else "[bold gold1]hidden[/]"

    presenting = switch.presenting()
    body = (f"recent files      {word(vals['ShowRecent'])}\n"
            f"frequent folders  {word(vals['ShowFrequent'])}")
    if a.state != "status" and not a.restart_explorer:
        body += ("\n[grey50]An already-open Explorer window may need F5; "
                 "-re restarts Explorer.[/]")
    console.print(Panel(
        body,
        title="[bold black on gold1] PRESENTING [/]" if presenting else "[bold black on bright_green] normal [/]",
        border_style="gold1" if presenting else "bright_green", expand=False))
    return 0


# ---------------------------------------------------------------- help

def show_overview() -> None:
    console.print(Panel(
        Text.assemble(("recentctl ", "bold bright_magenta"), (f"v{__version__}\n", "grey50"),
                      ("Dump, count and prune File Explorer's ", "white"),
                      ("Recent", "bold bright_cyan"), (" list — and hide it while you share "
                                                        "your screen.", "white")),
        border_style="bright_magenta", box=box.DOUBLE, expand=False))

    cmds = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
    cmds.add_column(style="bold bright_cyan", no_wrap=True)
    cmds.add_column()
    cmds.add_row("list", "show entries newest first, [bright_yellow]●[/] = visible in Home "
                 "[grey50](alias: dump)[/]")
    cmds.add_row("stats", "counts by kind, category, extension, root dir, age, month")
    cmds.add_row("prune", "remove entries — [bold gold1]dry run[/] unless [bright_cyan]-y[/]")
    cmds.add_row("present", "[gold1]on[/] hides Recent for screen sharing, "
                 "[bright_green]off[/] restores, no argument = status")
    cmds.add_row("help", "this page; [bright_cyan]help <command>[/] for its options")
    console.print(Panel(cmds, title="[bold gold1]commands[/]", border_style="gold1",
                        title_align="left", expand=False))

    sel = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
    sel.add_column(style="bold spring_green2", no_wrap=True)
    sel.add_column()
    sel.add_row("-m PAT", "pattern; repeat for OR. [orchid]D:\\Private\\*[/] glob (crosses "
                "backslashes), [orchid]payslip[/] substring. Case-insensitive.")
    sel.add_row("-ot AGE / -nt AGE", "last opened longer ago / more recently than "
                "[orchid]90min 12h 30d 6w 1y[/]")
    sel.add_row("-k KIND", "[bright_cyan]file[/], [bold gold1]folder[/] or [orchid]other[/] "
                "(URLs, app links)")
    cats = " ".join(f"[{view.CATEGORY_STYLE[c]}]{c}[/]" for c in view.CATEGORY_STYLE)
    sel.add_row("-ct CAT", f"file category, repeat for OR: {cats}")
    sel.add_row("-r [-rf PATH]", f"use the rules file [grey50]({DEFAULT_RULES})[/]")
    console.print(Panel(sel, title="[bold spring_green2]selecting entries[/] "
                        "[grey50](list, stats, prune)[/]", border_style="spring_green2",
                        title_align="left", expand=False))

    rules = Text.assemble(
        ("max_age", "bold bright_cyan"), (" = ", "grey50"), ('"60d"', "orchid"),
        ("            # anything older goes\n", "grey50"),
        ("private", "bold bright_cyan"), (" = [", "grey50"), ("'D:\\Private\\*'", "orchid"),
        (", ", "grey50"), ("'payslip'", "orchid"), ("]  # always goes\n", "grey50"),
        ("keep", "bold bright_cyan"), ("    = [", "grey50"), ("'D:\\Work\\*'", "orchid"),
        ("]                # never goes — beats everything", "grey50"))
    console.print(Panel(rules, title="[bold dodger_blue1]rules file[/] [grey50](TOML)[/]",
                        border_style="dodger_blue1", title_align="left", expand=False))

    ex = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
    ex.add_column(style="bold bright_white", no_wrap=True)
    ex.add_column(style="grey70")
    for c, d in EXAMPLES:
        ex.add_row(c, d)
    console.print(Panel(ex, title="[bold deep_pink2]examples[/]", border_style="deep_pink2",
                        title_align="left", expand=False))
    console.print(Group(
        _legend(),
        Text.assemble(("Removed entries are logged to ", "grey50"), (str(LOG_FILE), "grey62"),
                      (". Pinned folders, favourites and the files themselves are never "
                       "touched.", "grey50"))))


def cmd_help(a: argparse.Namespace) -> int:
    if a.topic:
        parser = build_parser()
        sub = parser._subparsers._group_actions[0].choices.get(a.topic)  # noqa: SLF001
        if sub is None:
            console.print(f"[bold red]✗[/] no command [bright_cyan]{a.topic}[/]")
            return 2
        sub.print_help()
        return 0
    show_overview()
    return 0


# ---------------------------------------------------------------- parser

def _add_selectors(p: argparse.ArgumentParser, rules: bool = True) -> None:
    g = p.add_argument_group("selecting entries")
    g.add_argument("-m", "--match", action="append", metavar="PAT",
                   help="pattern on target path or name; repeat for OR")
    g.add_argument("-ot", "--older-than", metavar="AGE", help="last opened longer ago than AGE")
    g.add_argument("-nt", "--newer-than", metavar="AGE", help="last opened within AGE")
    g.add_argument("-k", "--kind", action="append", choices=["file", "folder", "other"],
                   help="only this kind; repeatable")
    g.add_argument("-ct", "--category", action="append", choices=list(view.CATEGORY_STYLE),
                   metavar="CAT",
                   help="file category; repeat for OR: " + ", ".join(view.CATEGORY_STYLE)
                   + " (see `recentctl stats -by category`)")
    if rules:
        g.add_argument("-r", "--rules", action="store_true", help="apply the rules file")
        g.add_argument("-rf", "--rules-file", metavar="PATH",
                       help=f"rules file (default {DEFAULT_RULES})")


def build_parser() -> argparse.ArgumentParser:
    fmt = RawDescriptionRichHelpFormatter
    ap = argparse.ArgumentParser(prog="recentctl", description=__doc__, epilog=EPILOG,
                                 formatter_class=fmt)
    ap.add_argument("-V", "--version", action="version", version=f"recentctl {__version__}")
    sub = ap.add_subparsers(dest="cmd", metavar="COMMAND")

    p = sub.add_parser("list", aliases=["dump"], help="show entries, newest first",
                       description="Show Recent entries, newest first. ● marks the ones "
                       "Explorer Home shows right now.", formatter_class=fmt, epilog=EPILOG)
    _add_selectors(p)
    p.add_argument("-vo", "--visible-only", action="store_true",
                   help="only what Explorer Home shows right now")
    p.add_argument("-l", "--limit", type=int, metavar="N", help="at most N rows")
    p.add_argument("-j", "--json", action="store_true", help="JSON instead of a table")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("stats", help="counts by kind, category, extension, root dir, age",
                       description="Count entries by kind, category, extension, root "
                       "directory, age bucket or month.", formatter_class=fmt, epilog=EPILOG)
    _add_selectors(p, rules=False)
    p.add_argument("-by", "--by", action="append", choices=list(stats.GROUPINGS),
                   help="grouping; repeatable (default: kind category ext root age)")
    p.add_argument("-t", "--top", type=int, default=12, metavar="N",
                   help="rows per table (default 12)")
    p.add_argument("-dp", "--depth", type=int, default=1, metavar="N",
                   help="directory levels for root grouping (default 1)")
    p.add_argument("-vo", "--visible-only", action="store_true",
                   help="only what Explorer Home shows right now")
    p.add_argument("-j", "--json", action="store_true", help="JSON instead of tables")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("prune", help="remove entries (dry run unless -y)",
                       description="Remove Recent entries. Dry run unless -y. Needs at least "
                       "one selector.", formatter_class=fmt, epilog=EPILOG)
    _add_selectors(p)
    p.add_argument("-y", "--yes", action="store_true", help="really remove")
    p.add_argument("-q", "--quiet", action="store_true", help="print only failures")
    p.set_defaults(func=cmd_prune)

    p = sub.add_parser("present", help="hide/show the Recent section for screen sharing",
                       description="Hide or show Explorer Home's Recent section. History is "
                       "kept.", formatter_class=fmt, epilog=EPILOG)
    p.add_argument("state", choices=["on", "off", "status"], nargs="?", default="status",
                   help="on = hide (presenting), off = show, status = report")
    p.add_argument("-f", "--frequent", action="store_true",
                   help="with on: also hide frequent folders in Quick access")
    p.add_argument("-re", "--restart-explorer", action="store_true",
                   help="restart Explorer so every window picks it up")
    p.set_defaults(func=cmd_present)

    p = sub.add_parser("help", help="illustrated overview, or help for one command",
                       formatter_class=fmt)
    p.add_argument("topic", nargs="?", metavar="COMMAND", help="list, stats, prune, present")
    p.set_defaults(func=cmd_help)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    if not getattr(a, "func", None):
        show_overview()
        return 0
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())

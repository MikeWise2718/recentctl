# recentctl

**Dump, count and prune Windows File Explorer's _Recent_ list — and hide it while you share
your screen.**

File Explorer's Home page shows a *Recent* section with everything you've opened lately. If
you use the same PC for work and private things and share your screen in meetings, that list
is a liability: it fills up constantly, and when you remove an entry by hand, an older one
scrolls up to take its place. Checking it before every call is slow and never certain.

`recentctl` is a small command-line tool that lets you:

- **see** the whole history, not just the 20 entries Home shows, with the visible ones marked;
- **count** it by kind, file type, folder, age or month;
- **prune** it with patterns, age limits and a rules file — dry run by default;
- **hide** the Recent section with one command before a call, and bring it back afterwards.

It only removes entries from the list. **Your files, pinned folders and favourites are never
touched.**

## Requirements

- Windows 11 (developed and tested on 24H2/25H2; Windows 10 untested)
- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) (recommended) or [pipx](https://pipx.pypa.io/)

No administrator rights are needed: everything lives in your own user profile.

## Install

With uv, straight from GitHub:

```powershell
uv tool install git+https://github.com/MikeWise2718/recentctl
```

or with pipx:

```powershell
pipx install git+https://github.com/MikeWise2718/recentctl
```

Either puts `recentctl.exe` on your PATH. If the command isn't found afterwards, run
`uv tool update-shell` (or `pipx ensurepath`) and open a new terminal.

From a clone, for hacking on it:

```powershell
git clone https://github.com/MikeWise2718/recentctl
cd recentctl
uv tool install -e .          # editable: source changes take effect immediately
```

Upgrade with `uv tool upgrade recentctl`; remove with `uv tool uninstall recentctl`.

## Quick start

```powershell
recentctl                         # illustrated overview of every command
recentctl list -vo                # exactly what Explorer Home shows right now
recentctl stats                   # what's in the whole history
recentctl prune -ot 90d           # DRY RUN: entries not opened for 90 days
recentctl prune -ot 90d -y        # ...and really remove them
recentctl present on              # hide Recent before a screen share
recentctl present off             # show it again
```

Colours work in Windows Terminal and any modern console.

## Commands

### `list` (alias `dump`) — show entries

Newest first. A yellow **●** marks the entries Explorer Home is showing right now. Names are
coloured by file type and ages run from green (today) to red (over a year).

```powershell
recentctl list -l 50                  # the 50 newest entries
recentctl list -m payslip -m *.mp4    # either pattern
recentctl list -ot 6w -k file         # files not opened for six weeks
recentctl list -ct image -ct video    # only pictures and videos
recentctl list -r                     # what your rules file would remove, and why
recentctl list -j                     # JSON, for scripts
```

### `stats` — count entries

A summary (entries, files/folders/links, duplicates, history span) followed by bar charts.

```powershell
recentctl stats                       # kind, category, extension, root folder, age
recentctl stats -by root -dp 2 -t 30  # top 30 folders, two levels deep
recentctl stats -by month             # history by month
recentctl stats -m D:\Work\*          # statistics for one tree only
```

Groupings (`-by`, repeatable): `kind`, `category` (image, video, text, office, code, …),
`ext`, `root` (drive, network share or `~` for your profile, plus `-dp` levels; web links by
host, app links by scheme), `age`, `month`.

### `prune` — remove entries

Always needs at least one selector, and is a **dry run unless you add `-y`**. Every removal
is logged as one JSON line to `%LOCALAPPDATA%\recentctl\events.jsonl`.

```powershell
recentctl prune -m *\Videos\*         # shows what would go
recentctl prune -m *\Videos\* -y      # removes it
recentctl prune -r -y                 # apply your rules file
recentctl prune -ct video -y          # every video, whatever its age
```

`-m`, `-ot`, `-nt` and `-ct` each count as a selector. `-k` on its own doesn't, because
`prune -k file` would empty almost the whole list.

### `present` — the screen-sharing switch

```powershell
recentctl present on                  # hide the Recent section
recentctl present on -f               # ...and frequent folders in Quick access too
recentctl present off                 # restore exactly the previous settings
recentctl present                     # status
```

This flips the same settings as *Folder Options → Show recently used files / Show frequently
used folders*. Nothing is deleted. An Explorer window that is already open may need F5; `-re`
restarts Explorer so every window picks it up.

> Don't use the Start-menu setting *"Show recently opened items in Start, Jump Lists, and
> File Explorer"* as a quick hide — switching it off **wipes** the history.

### `help`

`recentctl` or `recentctl help` shows an illustrated overview; `recentctl help prune` (or
`recentctl prune -h`) shows one command's options.

## Selecting entries

`list`, `stats` and `prune` share these options:

| Option | Meaning |
|---|---|
| `-m PAT` | Pattern on the target path or the entry name. Repeat for OR. |
| `-ot AGE` | Last opened **longer ago** than AGE. |
| `-nt AGE` | Last opened **more recently** than AGE. |
| `-k KIND` | `file`, `folder` or `other` (web and app links). Repeatable. |
| `-ct CAT` | File category: `image`, `video`, `audio`, `text`, `office`, `code`, `archive`, `binary`, `folder`, `web/app`, `other`. Repeat for OR. |
| `-r`, `-rf PATH` | Use the rules file (`list` and `prune`). |

- **Patterns** are case-insensitive. With `*`, `?` or `[` they are globs, and `*` also
  crosses backslashes, so `D:\Private\*` covers the whole tree. Without wildcards they match
  as a substring: `payslip` hits any path or name containing it.
- **Ages** are `90min`, `12h`, `30d`, `6w` or `1y`, counted from when the item was last
  opened.
- `-m` and the age options combine with AND. For `prune -r`, entries the rules select are
  added (OR).

## Rules file

Keep your standing rules in `%USERPROFILE%\.config\recentctl\rules.toml`. Start from
[`rules.example.toml`](rules.example.toml):

```toml
max_age = "60d"                        # anything not opened for 60 days goes

private = [                            # always goes, whatever its age
    'D:\Private\*',
    '*\Bank statements\*',
    'payslip',
]

keep = [                               # never goes — beats everything else
    'D:\Work\*',
]
```

Check what it selects with `recentctl list -r`, then apply it with `recentctl prune -r -y`.

Running that on a schedule keeps the list clean without thinking about it. For example, Task
Scheduler can run `recentctl prune -r -y -q` at logon and every 15 minutes.

## How it works

Explorer builds the Recent section from the shortcut files in
`%APPDATA%\Microsoft\Windows\Recent`. Home shows the 20 newest that point at files. Removing
the shortcut removes the entry, and a shortcut's modification time is when its target was
last opened. Details, and what was tried and rejected, are in
[docs/how-it-works.md](docs/how-it-works.md).

### Not covered

- **Taskbar jump lists** (right-click an app's taskbar icon) keep their own history in
  `AutomaticDestinations`. They are binary compound files and are left alone.
- **Office.com / OneDrive recents** come from your Microsoft account, not this PC. Turn off
  *Folder Options → Show files from Office.com* if they appear.

## Development

```powershell
uv sync
uv run --group dev pytest
```

## License

[MIT](LICENSE)

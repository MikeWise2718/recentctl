# recentctl — notes for Claude Code

⚠️ **This is a PUBLIC repository.** Never commit personal paths, hostnames, IPs, usernames
or real Recent-list output — use generic examples (`D:\Private\*`, `D:\Work\*`, `alice`,
`nas`). Before every push, grep the diff for anything that came from a real machine.

- Python ≥ 3.12, `uv`; CLI built on `rich` + `rich-argparse`; every option has a short form.
- `src/recentctl/`: `store.py` (read/delete `.lnk`), `rules.py` (patterns, ages, rules
  file), `stats.py` (groupings), `view.py` (colours, time format), `switch.py` (present
  on/off), `cli.py`.
- Times shown to people: 24-hour clock with a short zone name (`view.stamp`), never AM/PM.
- Bump `__version__` in `src/recentctl/__init__.py` with every code change.
- Tests: `uv run --group dev pytest`. `test_store.py` writes real shortcuts into a temp dir.
- How Windows stores the list, and what was tried: `docs/how-it-works.md`.

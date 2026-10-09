from datetime import datetime, timedelta
from pathlib import Path

import pytest

from recentctl.rules import Filters, Rules, matches, parse_age, select
from recentctl.store import Entry


def entry(target, days=0, kind="file", name=None):
    return Entry(
        lnk=Path(f"C:/x/{name or Path(target).name}.lnk"),
        name=name or Path(target).name,
        target=target,
        kind=kind,
        opened=datetime.now() - timedelta(days=days, minutes=1),
    )


def test_parse_age():
    assert parse_age("90min") == timedelta(minutes=90)
    assert parse_age("12h") == timedelta(hours=12)
    assert parse_age("30d") == timedelta(days=30)
    assert parse_age("6w") == timedelta(weeks=6)
    assert parse_age("1y") == timedelta(days=365)
    with pytest.raises(ValueError):
        parse_age("3 months")


def test_glob_crosses_backslashes_and_ignores_case():
    e = entry(r"D:\Private\scans\2026\mri.png")
    assert matches(r"d:\private\*", e)
    assert not matches(r"D:\Work\*", e)


def test_substring_and_name():
    e = entry("", kind="other", name="search?q=garmin connect")
    assert matches("garmin", e)
    assert matches("search*", e)


def test_rules_private_age_keep():
    r = Rules(private=[r"*\Videos\*"], keep=[r"D:\Work\*"], max_age=timedelta(days=60),
              max_age_text="60d")
    vid, old, kept, fresh = (
        entry(r"C:\Users\alice\Videos\a.mp4"),
        entry(r"D:\Projects\x.md", days=90),
        entry(r"D:\Work\old.md", days=400),
        entry(r"D:\Projects\new.md", days=1),
    )
    rows = select([vid, old, kept, fresh], Filters(), r, union=True)
    assert [(e.name, why.split(":")[0]) for e, why in rows] == [
        ("a.mp4", "private"), ("x.md", "older than 60d"),
    ]


def test_list_filters_narrow_and_prune_unions():
    a, b = entry(r"D:\a\one.md", days=10), entry(r"D:\b\two.md", days=1)
    f = Filters(patterns=[r"D:\a\*"], older_than=timedelta(days=5))
    assert [e.name for e, _ in select([a, b], f, None, union=False)] == ["one.md"]
    # prune with only a kind filter selects nothing by itself
    assert select([a, b], Filters(kinds=["file"]), None, union=True) == []


def test_keep_beats_cli_filter():
    e = entry(r"D:\Work\x.md", days=100)
    r = Rules(keep=[r"D:\Work\*"])
    assert select([e], Filters(older_than=timedelta(days=1)), r, union=True) == []


def test_category_filter_selects_and_narrows():
    pic, vid, doc = entry(r"D:\a\p.JPG"), entry(r"D:\a\v.mp4"), entry(r"D:\a\d.md")
    f = Filters(categories=["image", "video"])
    assert [e.name for e, _ in select([pic, vid, doc], f, None, union=False)] == ["p.JPG", "v.mp4"]
    assert [e.name for e, _ in select([pic, vid, doc], f, None, union=True)] == ["p.JPG", "v.mp4"]

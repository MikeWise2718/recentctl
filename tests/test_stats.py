from datetime import datetime, timedelta
from pathlib import Path

from recentctl import stats
from recentctl.store import Entry
from recentctl.view import category, extension


def entry(target, kind="file", days=0, name=None):
    return Entry(lnk=Path("x.lnk"), name=name or Path(target).name, target=target, kind=kind,
                 opened=datetime.now() - timedelta(days=days, minutes=1))


def test_root_profile_drive_unc_url(monkeypatch):
    monkeypatch.setattr(stats, "PROFILE", r"c:\users\alice")
    assert stats.root(entry(r"C:\Users\alice\Videos\Holiday\a.mp4")) == r"~\Videos"
    assert stats.root(entry(r"C:\Users\alice\Videos\Holiday\a.mp4"), 2) == r"~\Videos\Holiday"
    assert stats.root(entry(r"D:\Work\proj\docs\a.md")) == r"D:\Work"
    assert stats.root(entry(r"D:\top.txt")) == "D:\\"
    assert stats.root(entry(r"D:\Work", kind="folder")) == r"D:\Work"
    assert stats.root(entry(r"\\nas\transfer\x\y.pdf")) == r"\\nas\transfer\x"
    assert stats.root(entry("https://www.bing.com/search?q=x", kind="other")) == "https://www.bing.com"
    assert stats.root(entry("ms-screenclip:///?source=HotKey", kind="other")) == "ms-screenclip:"


def test_extension_and_category():
    assert extension(entry(r"D:\a\b.MP4")) == ".mp4" and category(entry(r"D:\a\b.MP4")) == "video"
    assert extension(entry(r"D:\a\Makefile")) == "(none)"
    assert extension(entry(r"D:\a", kind="folder")) == "(folder)"
    assert extension(entry("https://x.org/", kind="other")) == "(https)"


def test_group_counts_and_age_buckets():
    es = [entry(r"D:\a\1.md"), entry(r"D:\a\2.md", days=3), entry(r"D:\b\3.png", days=400)]
    g = stats.group(es, lambda e: stats.root(e))
    assert [(x.key, x.count) for x in g] == [(r"D:\a", 2), (r"D:\b", 1)]
    assert [stats.age_bucket(e) for e in es] == ["< 1 day", "1–7 days", "> 1 year"]

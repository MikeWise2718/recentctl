import uuid
import winreg
from datetime import timedelta

import pytest

from recentctl import apps
from recentctl.rules import Filters, Rules, select

ITEM = "[F00000000][T01DB0A1B2C3D4E50][O00000000]*{}"


@pytest.fixture
def office_root():
    """A scratch HKCU tree shaped like Office\\16.0, deleted afterwards."""
    base = rf"Software\recentctl-test-{uuid.uuid4().hex[:8]}\16.0"
    files = rf"{base}\Word\User MRU\LiveId_TEST\File MRU"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, files) as k:
        for n, path in enumerate([r"C:\Work\a.docx", r"D:\Private\b.docx", r"C:\Work\c.docx"], 1):
            winreg.SetValueEx(k, f"Item {n}", 0, winreg.REG_SZ, ITEM.format(path))
            winreg.SetValueEx(k, f"Item Metadata {n}", 0, winreg.REG_SZ, f"<meta {n}>")
        winreg.SetValueEx(k, "FOLDERID_Documents", 0, winreg.REG_SZ, "keep me")
    yield base, files
    root = base.rsplit("\\", 1)[0]

    def wipe(path):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
                subs = [winreg.EnumKey(k, i) for i in range(winreg.QueryInfoKey(k)[0])]
        except OSError:
            return
        for s in subs:
            wipe(rf"{path}\{s}")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)

    wipe(root)


def test_office_parse_and_remove_renumbers(office_root):
    base, files = office_root
    items = apps.load_office(base=base)
    assert [i.target for i in sorted(items, key=lambda i: i.slot)] == [
        r"C:\Work\a.docx", r"D:\Private\b.docx", r"C:\Work\c.docx"]
    assert all(i.app == "word" and i.list == "files" and i.opened for i in items)

    victim = [i for i in items if "Private" in i.target]
    assert apps.remove_office(files, {victim[0].slot}) == 1
    vals = apps._values(winreg.HKEY_CURRENT_USER, files)
    assert vals["Item 1"].endswith(r"C:\Work\a.docx")
    assert vals["Item 2"].endswith(r"C:\Work\c.docx")
    assert "Item 3" not in vals
    assert vals["Item Metadata 2"] == "<meta 3>"  # metadata follows its item
    assert vals["FOLDERID_Documents"] == "keep me"


def test_filetime():
    dt = apps.filetime("01DB0A1B2C3D4E50")
    assert dt is not None and 2024 <= dt.year <= 2025
    assert apps.filetime("0000000000000000") is None


VLC = (
    "[General]\r\nfoo=1\r\n\r\n[RecentsMRL]\r\n"
    "list=file:///C:/Videos/holiday.mp4, file://nas/share/Private/x%2C%20y.mkv, "
    "https://example.com/stream\r\ntimes=10, 20, 30\r\n\r\n[Other]\r\nbar=2\r\n"
)


def test_vlc_parse(tmp_path):
    ini = tmp_path / "vlc-qt-interface.ini"
    ini.write_bytes(VLC.encode())
    items = apps.load_vlc(ini)
    assert [(i.target, i.kind) for i in items] == [
        (r"C:\Videos\holiday.mp4", "file"),
        (r"\\nas\share\Private\x, y.mkv", "file"),
        ("https://example.com/stream", "other"),
    ]


def test_vlc_remove_keeps_times_parallel_and_rest_of_file(tmp_path):
    ini = tmp_path / "vlc-qt-interface.ini"
    ini.write_bytes(VLC.encode())
    assert apps.remove_vlc({1}, ini) == 1
    text = ini.read_bytes().decode()
    assert "list=file:///C:/Videos/holiday.mp4, https://example.com/stream\r\n" in text
    assert "times=10, 30\r\n" in text
    assert text.startswith("[General]\r\nfoo=1\r\n") and text.endswith("[Other]\r\nbar=2\r\n")
    apps.remove_vlc({0, 1}, ini)
    text = ini.read_bytes().decode()
    assert "list=@Invalid()\r\n" in text and "times=@Invalid()\r\n" in text
    assert apps.load_vlc(ini) == []


def test_rules_and_age_on_undated_items(tmp_path):
    ini = tmp_path / "vlc-qt-interface.ini"
    ini.write_bytes(VLC.encode())
    items = apps.load_vlc(ini)
    rules = Rules(private=[r"*\private\*"])
    picked = select(items, Filters(), rules, union=True)
    assert [i.name for i, _ in picked] == ["x, y.mkv"]
    # VLC keeps no times, so an age must never select its items
    f = Filters(newer_than=timedelta(days=1), newer_text="1d")
    assert select(items, f, None, union=True) == []

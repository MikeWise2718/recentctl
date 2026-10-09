"""Reads real .lnk files written by Windows' own shortcut API into a temp dir."""

import os
from datetime import datetime

import win32com.client

from recentctl import store


def _mk(dirpath, name, target):
    sc = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(dirpath / f"{name}.lnk"))
    sc.TargetPath = str(target)
    sc.Save()


def test_load_reads_targets_kinds_and_order(tmp_path):
    rec = tmp_path / "Recent"
    rec.mkdir()
    f = tmp_path / "doc.txt"
    f.write_text("x")
    _mk(rec, "doc.txt", f)
    _mk(rec, "folder", tmp_path)
    old = datetime(2025, 1, 1).timestamp()
    os.utime(rec / "folder.lnk", (old, old))

    entries = store.load(rec)
    assert [e.name for e in entries] == ["doc.txt", "folder"]
    assert entries[0].kind == "file" and entries[0].target.lower() == str(f).lower()
    assert entries[1].kind == "folder"
    assert not any(e.visible for e in entries)

    store.remove(entries[1])
    assert [e.name for e in store.load(rec)] == ["doc.txt"]

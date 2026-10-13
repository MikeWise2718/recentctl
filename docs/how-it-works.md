# How Explorer's Recent list works

Observed on Windows 11 25H2 (build 26200). Earlier builds may differ in detail.

## Where the entries live

| What you see | Backing store |
|---|---|
| **Recent** files on Explorer's Home page | Shortcut (`.lnk`) files in `%APPDATA%\Microsoft\Windows\Recent`. Home shows the **20 newest** that point at files, through the shell folder `shell:::{4564b25e-30cd-4787-82ba-39e73a750b14}` ("Recent Items Instance Folder"). |
| Recent folders | The same `.lnk` folder (shortcuts whose target is a directory); shell folder `shell:::{22877a6d-37a1-461a-91b0-dbda5aaebc99}`. |
| Quick access (pinned + frequent folders) | `Recent\AutomaticDestinations\f01b4d95cf55d32a.automaticDestinations-ms`. |
| Explorer's own jump-list history | `Recent\AutomaticDestinations\5f7b5f1e01b83767.automaticDestinations-ms`, an OLE compound file. It is **not** what Home's Recent section renders from. |

The `.lnk` folder also collects web pages, screen-snip links, Teams links and other app
URIs, so on a PC that has been in use for a year it typically holds well over a thousand
shortcuts. Windows appends ` (2)`, ` (3)`, … to repeated names.

A shortcut's **modification time** is bumped every time its target is reopened, so it means
"last opened". That's what `recentctl` uses for ages.

## Removing entries: what works

These were tested with dummy files added through `SHAddToRecentDocs`:

- **Deleting the `.lnk`** removes the entry from Home immediately. ✅ `recentctl` does this.
- **Invoking the "Remove from list" verb** through `Shell.Application` from a script does
  *not* remove the entry from Home; it only rewrites the `5f7b…` jump-list file. ❌
- `SHAddToRecentDocs` silently ignores files under `%TEMP%`, so test fixtures must live
  elsewhere.

`recentctl` reads each shortcut's stored target with `IShellLink::GetPath(SLGP_RAWPATH)` and
the file-attribute field of the `.lnk` header. Neither touches the target, so shortcuts to
an offline network share don't stall it.

## Quick access folders

Quick access (shell folder `shell:::{3936E9E4-D92C-4EEE-A85A-BC16D5EA0819}`) is a separate
list backed by `f01b4d95cf55d32a.automaticDestinations-ms`. Here the shell verbs **do**
work from a script: "Remove from Quick access" for frequent folders and "Unpin from Quick
access" for pinned ones. A pinned folder offers the second verb, a frequent one the first,
which is how `recentctl quick` tells them apart. Removing a frequent folder makes Windows
promote the next most-used folder into the free slot.

## Hiding the section

`HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer` holds `ShowRecent` and
`ShowFrequent` (DWORD; missing means 1, shown). They are the values behind Folder Options'
*Show recently used files* and *Show frequently used folders*, and an ordinary user can
write them. `recentctl present on` saves the old values, writes 0, and broadcasts
`WM_SETTINGCHANGE("ShellState")` plus `SHChangeNotify(SHCNE_ASSOCCHANGED)`.

Some taskbar settings, such as `TaskbarDa` for the Widgets button, are protected by
Windows' UCPD driver and reject scripted writes. These two are not.

The Start setting *"Show recently opened items in Start, Jump Lists, and File Explorer"*
(`Start_TrackDocs`) clears the history when switched off, so it can't serve as a temporary
hide.

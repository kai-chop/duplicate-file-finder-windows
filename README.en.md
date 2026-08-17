# duplicate-file-finder-windows

日本語版: [README.md](README.md)

**A duplicate file finder and remover for Windows.** It walks a folder tree recursively, finds files that are **byte-for-byte identical**, keeps exactly one file per identical group and sends the rest to the Recycle Bin. It is not limited to images — zip archives, videos, documents, anything.

- **Dry run by default** (it lists what it would delete and touches nothing)
- Deletes to the **Recycle Bin**, so every removal is reversible
- Writes a CSV log pairing each deleted file with the file that was kept
- Bonus: renders image and video entries of the Recycle Bin as a **thumbnail gallery**

## Requirements

| | |
|---|---|
| OS | Windows 10 / 11 |
| Python | verified on 3.14.3 (3.9+ expected, untested) |
| Pillow | only for the thumbnail gallery (`pip install pillow`) |
| ffmpeg | only for video thumbnails (must be on PATH) |

Finding and deleting duplicates needs no third-party package — the standard library is enough.

## Usage

### Double-click

| File | Action | Result |
|---|---|---|
| `重複ファイル削除.bat` (dedupe launcher) | drag a folder onto it | scans the tree, prints the list, deletes on `y` |
| `ごみ箱サムネ表示.bat` (gallery launcher) | double-click | builds a thumbnail HTML of images/videos in the Recycle Bin and opens it |
| `ごみ箱サムネ表示.bat` | drop a `logs\dedupe_*.csv` on it | rebuilds the view of already deleted files using their identical twins |

### Command line

```bat
python dedupe.py "D:\photos"                 :: dry run, deletes nothing
python dedupe.py "D:\photos" --ask           :: show the list, then confirm with y/N
python dedupe.py "D:\photos" --delete        :: delete without asking
python dedupe.py "D:\photos" --images        :: images only
python dedupe.py "D:\photos" --media --quiet :: images + videos, no per-group listing

python recycle_gallery.py                    :: thumbnails of the current Recycle Bin
python recycle_gallery.py --match Dropbox    :: filter by original location
python recycle_gallery.py --from-csv logs\dedupe_20260101_120000.csv
```

## How duplicates are decided, and what keeps you safe

**A duplicate must pass all three stages**: identical file size → identical partial hash (first and last 64 KB) → identical full BLAKE2b digest. **Visually similar images are out of scope** (resized, re-encoded, different EXIF) — a single differing byte means the file is never deleted.

**Which copy is kept** (first rule that decides, wins):

1. the one whose name does *not* look like a copy — `photo (1).jpg`, `report - Copy.zip`, `写真 - コピー.png`
2. the one at the shallower path
3. the older modification time
4. path order (so the result is fully deterministic)

**Never touched**: empty files (all zero-byte files would count as identical to each other), symlinks, `Thumbs.db` / `desktop.ini` / `.DS_Store`, and housekeeping folders such as `.git` and `$RECYCLE.BIN`.

**How deletion happens**: through `Microsoft.VisualBasic.FileIO.FileSystem::DeleteFile` with the Recycle Bin option. Nothing is erased permanently. Inside a synced folder such as Dropbox, the provider's own deletion history remains as a second recovery path.

## Logs

Every run writes `logs\dedupe_<timestamp>.csv` (with a `_dryrun` suffix for dry runs). Columns are `deleted, kept, bytes`. **These CSV files and the generated HTML galleries contain real file paths and your own pictures**, so they are excluded in `.gitignore`.

## Files

```
dedupe.py              duplicate detection and deletion (standard library only)
recycle_gallery.py     thumbnail HTML of the Recycle Bin (Pillow / ffmpeg)
dump_recyclebin.ps1    read-only dump of Recycle Bin entries
重複ファイル削除.bat     launcher for dedupe.py
ごみ箱サムネ表示.bat     launcher for recycle_gallery.py
```

## Limitations

- Windows only (deleting to and reading the Recycle Bin rely on Windows APIs)
- No HEIC/HEIF thumbnails yet (installing `pillow-heif` would extend it)
- Exact matches only; no similar-image detection

## License

MIT

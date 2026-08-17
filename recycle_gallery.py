"""Build an HTML thumbnail gallery of image/video files sitting in the Recycle Bin.

Explorer shows no thumbnails for recycled files, so this reads each entry's backing
$R file directly (read-only), renders a thumbnail with Pillow (ffmpeg for video) and
embeds them into one self-contained HTML page next to the original path and delete date.

The Recycle Bin itself is never modified.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import os
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".avif"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg"}

HERE = Path(__file__).resolve().parent
DUMP_PS1 = HERE / "dump_recyclebin.ps1"
OUT_DIR = HERE / "logs"
THUMB_PX = 320
BIDI_MARKS = "".join(chr(c) for c in (0x200E, 0x200F, 0x202A, 0x202B, 0x202C))


@dataclass
class Entry:
    name: str
    origin: str
    deleted: str
    real: Path   # file the thumbnail is rendered from
    size: int
    note: str = ""

    @property
    def ext(self) -> str:
        return Path(self.name).suffix.lower()


def read_bin() -> list[Entry]:
    """Enumerate Recycle Bin entries through the shell namespace."""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(DUMP_PS1)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        raise SystemExit("ごみ箱の一覧取得に失敗しました")

    entries: list[Entry] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        name, origin, deleted, real, size = (p.strip(BIDI_MARKS).strip() for p in parts)
        entries.append(Entry(name, origin, deleted, Path(real), int(size or 0)))
    return entries


def read_dedupe_csv(csv_path: Path) -> list[Entry]:
    """Rebuild the deleted files' view from a dedupe log.

    The deleted file is gone (Recycle Bin emptied), but it was byte-identical to the
    kept twin, so the twin renders exactly the same picture.
    """
    import csv as _csv

    stamp = re.search(r"(\d{8})_(\d{6})", csv_path.name)
    when = (f"{stamp[1][:4]}/{stamp[1][4:6]}/{stamp[1][6:]} "
            f"{stamp[2][:2]}:{stamp[2][2:4]}") if stamp else ""

    entries: list[Entry] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in _csv.DictReader(f):
            deleted, kept = Path(row["deleted"]), Path(row["kept"])
            if not kept.is_file():
                print(f"  残存側が見つからずスキップ: {kept}", file=sys.stderr)
                continue
            entries.append(Entry(
                name=deleted.name,
                origin=str(deleted.parent),
                deleted=when,
                real=kept,
                size=int(row["bytes"]),
                note=f"内容は残存ファイルと完全一致: {kept.name}",
            ))
    return entries


def sort_key(e: Entry):
    """Newest first; unparsable dates sink to the bottom."""
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", e.deleted)
    if not m:
        return (0,)
    return (1, datetime(*(int(g) for g in m.groups())))


def thumb_image(path: Path) -> bytes | None:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((THUMB_PX, THUMB_PX))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=78)
        return buf.getvalue()


def thumb_video(path: Path) -> bytes | None:
    """Grab a frame ~1s in; falls back to the first frame for very short clips."""
    for seek in ("1", "0"):
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", seek, "-i", str(path), "-frames:v", "1",
             "-vf", f"scale={THUMB_PX}:-1", "-f", "image2", "-vcodec", "mjpeg", "-"],
            capture_output=True,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout
    return None


def make_thumb(e: Entry) -> tuple[Entry, str | None]:
    try:
        data = thumb_video(e.real) if e.ext in VIDEO_EXTS else thumb_image(e.real)
    except Exception as ex:  # unreadable or unsupported codec: card shows a placeholder
        print(f"  サムネ生成失敗: {e.name} — {ex}", file=sys.stderr)
        data = None
    return e, base64.b64encode(data).decode() if data else None


def human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


CSS = """
* { box-sizing: border-box; }
body { margin:0; padding:24px; background:#14161a; color:#e6e8eb;
       font-family:"Segoe UI","Yu Gothic UI",system-ui,sans-serif; }
h1 { font-size:18px; margin:0 0 4px; font-weight:600; }
.sub { color:#98a2b3; font-size:13px; margin-bottom:20px; }
.grid { display:grid; gap:14px; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); }
.card { background:#1c2027; border:1px solid #2a3039; border-radius:10px; overflow:hidden;
        display:flex; flex-direction:column; }
.thumb { aspect-ratio:1/1; background:#0f1114; display:flex; align-items:center;
         justify-content:center; overflow:hidden; }
.thumb img { width:100%; height:100%; object-fit:contain; }
.none { color:#5b6472; font-size:12px; }
.meta { padding:8px 10px; font-size:11px; line-height:1.5; }
.name { color:#e6e8eb; font-size:12px; font-weight:600; word-break:break-all; margin-bottom:3px; }
.path { color:#8b95a5; word-break:break-all; }
.tag { display:inline-block; margin-top:4px; padding:1px 6px; border-radius:4px;
       background:#2a3039; color:#98a2b3; font-size:10px; }
"""


def build_html(cards: list[tuple[Entry, str | None]], title_note: str) -> str:
    parts = [
        "<!doctype html><html lang='ja'><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>ごみ箱サムネ一覧</title><style>{CSS}</style>",
        "<h1>ごみ箱の中身（サムネ表示）</h1>",
        f"<div class='sub'>{html.escape(title_note)}</div><div class='grid'>",
    ]
    for e, b64 in cards:
        thumb = (f"<img src='data:image/jpeg;base64,{b64}' loading='lazy' alt=''>"
                 if b64 else "<span class='none'>サムネなし</span>")
        kind = "動画" if e.ext in VIDEO_EXTS else "画像"
        parts.append(
            "<div class='card'>"
            f"<div class='thumb'>{thumb}</div>"
            f"<div class='meta'><div class='name'>{html.escape(e.name)}</div>"
            f"<div class='path'>{html.escape(e.origin)}</div>"
            f"<div class='path'>{html.escape(e.deleted)}</div>"
            + (f"<div class='path'>{html.escape(e.note)}</div>" if e.note else "")
            +
            f"<span class='tag'>{kind} / {human(e.size)}</span></div></div>"
        )
    parts.append("</div></html>")
    return "".join(parts)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="ごみ箱の画像・動画をサムネ一覧HTMLで見る")
    ap.add_argument("--from-csv", type=Path, default=None,
                    help="dedupe.py のログCSVから、削除済みファイルを残存側の絵で再現表示")
    ap.add_argument("--match", default="", help="元の場所にこの文字列を含むものだけ表示")
    ap.add_argument("--all-types", action="store_true", help="画像・動画以外も一覧に載せる")
    ap.add_argument("--limit", type=int, default=0, help="表示件数の上限（0=無制限）")
    ap.add_argument("--no-open", action="store_true", help="ブラウザを自動で開かない")
    args = ap.parse_args()

    if args.from_csv:
        entries = read_dedupe_csv(args.from_csv)
        source = f"削除ログ {args.from_csv.name}（絵は完全一致の残存ファイルから生成）"
        print(f"削除ログの項目数: {len(entries)}件")
    else:
        entries = read_bin()
        source = "ごみ箱の実体"
        print(f"ごみ箱の総項目数: {len(entries)}件")

    def wanted(e: Entry) -> bool:
        if args.match and args.match.lower() not in unicodedata.normalize("NFC", e.origin).lower():
            return False
        return args.all_types or e.ext in IMAGE_EXTS | VIDEO_EXTS

    targets = sorted([e for e in entries if wanted(e)], key=sort_key, reverse=True)
    if args.limit:
        targets = targets[: args.limit]
    if not targets:
        print("該当する項目がありませんでした。")
        return 0
    print(f"サムネ生成対象: {len(targets)}件（画像/動画）")

    with ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 4))) as ex:
        cards = list(ex.map(make_thumb, targets))

    ok = sum(1 for _, b in cards if b)
    note = (f"{source} / {len(cards)}件 / サムネ生成 {ok}件"
            + (f" / 絞り込み: 「{args.match}」" if args.match else "")
            + f" / 作成 {datetime.now():%Y-%m-%d %H:%M}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"recyclebin_{datetime.now():%Y%m%d_%H%M%S}.html"
    out.write_text(build_html(cards, note), encoding="utf-8")
    print(f"サムネ生成: {ok}/{len(cards)}件")
    print(f"HTML: {out}")

    if not args.no_open:
        os.startfile(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

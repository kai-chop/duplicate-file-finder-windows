"""Find byte-identical files under a folder tree and send the extras to the Recycle Bin.

Matching is exact: files are grouped by size, then by a partial hash (head+tail),
then confirmed with a full BLAKE2b digest. No perceptual/similar-image matching.

Dry run is the default; deletion happens only with --delete.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".heic", ".heif", ".avif", ".tif", ".tiff",
}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg"}

SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
SKIP_DIRS = {".dropbox.cache", "$recycle.bin", "system volume information", ".git"}

# Filename patterns that mark a file as a copy, so it loses the "keeper" contest.
COPY_MARKERS = (
    re.compile(r"\s*\(\d+\)$"),
    re.compile(r"\s*-\s*コピー$"),
    re.compile(r"\s*-\s*Copy$", re.IGNORECASE),
    re.compile(r"\s*のコピー$"),
    re.compile(r"\s*copy\s*\d*$", re.IGNORECASE),
)

HEAD_TAIL = 64 * 1024
PARTIAL_THRESHOLD = 2 * HEAD_TAIL
LOG_DIR = Path(__file__).resolve().parent / "logs"


def is_copy_named(path: Path) -> bool:
    stem = path.stem
    return any(p.search(stem) for p in COPY_MARKERS)


def scan(root: Path, exts: set[str] | None) -> list[Path]:
    """Walk root and return regular files matching exts (None = every file)."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]
        for name in filenames:
            if name.lower() in SKIP_NAMES:
                continue
            p = Path(dirpath) / name
            if exts is not None and p.suffix.lower() not in exts:
                continue
            try:
                if p.is_symlink() or not p.is_file():
                    continue
            except OSError:
                continue
            found.append(p)
    return found


def partial_hash(path: Path, size: int) -> str:
    h = hashlib.blake2b(digest_size=16)
    with path.open("rb") as f:
        h.update(f.read(HEAD_TAIL))
        if size > PARTIAL_THRESHOLD:
            f.seek(-HEAD_TAIL, os.SEEK_END)
            h.update(f.read(HEAD_TAIL))
    return h.hexdigest()


def full_hash(path: Path) -> str:
    h = hashlib.blake2b(digest_size=32)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def group_duplicates(files: list[Path]) -> list[tuple[int, list[Path]]]:
    """Return [(size, [identical paths...]), ...] for groups of 2 or more."""
    by_size: dict[int, list[Path]] = defaultdict(list)
    for p in files:
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size == 0:  # empty files are all "identical"; never touch them
            continue
        by_size[size].append(p)

    candidates = [(s, ps) for s, ps in by_size.items() if len(ps) > 1]
    groups: list[tuple[int, list[Path]]] = []
    for size, paths in candidates:
        by_partial: dict[str, list[Path]] = defaultdict(list)
        for p in paths:
            try:
                by_partial[partial_hash(p, size)].append(p)
            except OSError as e:
                print(f"  読取失敗（スキップ）: {p} — {e}", file=sys.stderr)
        for part in by_partial.values():
            if len(part) < 2:
                continue
            by_full: dict[str, list[Path]] = defaultdict(list)
            for p in part:
                try:
                    by_full[full_hash(p)].append(p)
                except OSError as e:
                    print(f"  読取失敗（スキップ）: {p} — {e}", file=sys.stderr)
            for same in by_full.values():
                if len(same) > 1:
                    groups.append((size, same))
    groups.sort(key=lambda g: g[0] * (len(g[1]) - 1), reverse=True)
    return groups


def pick_keeper(paths: list[Path]) -> Path:
    """Deterministic winner: original-looking name > shallowest > oldest > path order."""
    def rank(p: Path):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            mtime = float("inf")
        return (is_copy_named(p), len(p.parts), mtime, str(p))

    return min(paths, key=rank)


def recycle(paths: list[Path]) -> tuple[int, str]:
    """Send paths to the Recycle Bin via PowerShell; returns (exit code, output)."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8",
                                     delete=False, newline="\n") as tf:
        tf.write("\n".join(str(p) for p in paths))
        list_file = tf.name

    ps = (
        "$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8;"
        "Add-Type -AssemblyName Microsoft.VisualBasic;"
        f"$paths = Get-Content -LiteralPath '{list_file}' -Encoding UTF8;"
        "$ok = 0; $ng = 0;"
        "foreach ($p in $paths) {"
        "  if ([string]::IsNullOrWhiteSpace($p)) { continue }"
        "  try {"
        "    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile("
        "      $p, 'OnlyErrorDialogs', 'SendToRecycleBin', 'ThrowException'); $ok++"
        "  } catch { $ng++; Write-Output ('FAIL ' + $p + ' :: ' + $_.Exception.Message) }"
        "};"
        "Write-Output ('DONE ok=' + $ok + ' ng=' + $ng)"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    finally:
        os.unlink(list_file)


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n}B"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="完全同一ファイルを見つけてごみ箱へ送る")
    ap.add_argument("root", type=Path, help="走査するフォルダ（配下すべてを再帰的に走査）")
    ap.add_argument("--images", action="store_true", help="画像のみに絞る")
    ap.add_argument("--media", action="store_true", help="画像+動画に絞る")
    ap.add_argument("--delete", action="store_true", help="確認なしでごみ箱へ送る")
    ap.add_argument("--ask", action="store_true", help="一覧を見せてから y/N で確認して削除")
    ap.add_argument("--quiet", action="store_true", help="重複グループの一覧を表示しない")
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"フォルダが見つかりません: {root}", file=sys.stderr)
        return 2

    if args.images:
        exts, label = IMAGE_EXTS, "画像のみ"
    elif args.media:
        exts, label = IMAGE_EXTS | VIDEO_EXTS, "画像+動画"
    else:
        exts, label = None, "全ファイル（拡張子問わず）"

    print(f"走査: {root}")
    print(f"対象: {label} / モード: {'実削除（ごみ箱）' if args.delete else 'ドライラン'}")

    files = scan(root, exts)
    print(f"対象ファイル: {len(files)}件")

    groups = group_duplicates(files)
    victims: list[tuple[Path, Path, int]] = []  # (delete, keep, size)
    for size, paths in groups:
        keeper = pick_keeper(paths)
        for p in paths:
            if p != keeper:
                victims.append((p, keeper, size))

    reclaim = sum(v[2] for v in victims)
    print(f"\n重複グループ: {len(groups)}件 / 削除候補: {len(victims)}件 / 回収容量: {human(reclaim)}")

    if not victims:
        print("重複はありませんでした。")
        return 0

    if not args.quiet:
        for i, (size, paths) in enumerate(groups, 1):
            keeper = pick_keeper(paths)
            print(f"\n[{i}] {human(size)} x {len(paths)}")
            print(f"   残す: {keeper.relative_to(root)}")
            for p in paths:
                if p != keeper:
                    print(f"   削除: {p.relative_to(root)}")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = LOG_DIR / f"dedupe_{stamp}{'' if args.delete else '_dryrun'}.csv"
    with log.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["deleted", "kept", "bytes"])
        for p, keeper, size in victims:
            w.writerow([str(p), str(keeper), size])
    print(f"\n一覧CSV: {log}")

    if not args.delete:
        if not args.ask:
            print("ドライランです。実行するには --delete を付けて再実行してください。")
            return 0
        print(f"\n上記 {len(victims)}件をごみ箱へ送ります（各グループ1件は必ず残ります）。")
        try:
            answer = input("実行しますか? [y/N]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("中止しました。1件も削除していません。")
            return 0

    code, out = recycle([v[0] for v in victims])
    print(out.strip())
    if code != 0 or "ng=0" not in out:
        print("一部の削除に失敗しました（上の FAIL 行を確認）", file=sys.stderr)
        return 1
    print(f"完了: {len(victims)}件をごみ箱へ送りました（{human(reclaim)} 回収）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

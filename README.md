# duplicate-file-finder-windows

**Windows用の重複ファイル検索・削除ツール** — Find and delete byte-identical duplicate files on Windows. Dry run by default, deletes to the Recycle Bin, works on any file type (images, videos, zip, documents).

指定フォルダの配下を再帰的に走査し、**バイト単位で完全に同一のファイル**を見つけて、各グループから1件だけ残して残りをごみ箱へ送ります。画像に限らず、zip・動画・ドキュメントなど**種類を問わず**扱えます。

- 既定は**ドライラン**（一覧を出すだけ・何も消さない）
- 削除は**ごみ箱送り**なので元に戻せる
- 「消した/残した」の対応表をCSVで残す
- おまけ: ごみ箱にある画像・動画を**サムネ一覧HTML**で確認できる

## 必要なもの

| | |
|---|---|
| OS | Windows 10 / 11 |
| Python | 3.14.3 で動作確認（3.9 以上を想定・未検証） |
| Pillow | サムネ機能を使う場合のみ（`pip install pillow`） |
| ffmpeg | 動画のサムネを出す場合のみ（PATHに通っていること） |

重複の検出・削除だけなら追加インストールは不要です（標準ライブラリのみ）。

## 使い方

### ダブルクリックで使う

| ファイル | 操作 | 動作 |
|---|---|---|
| `重複ファイル削除.bat` | フォルダをドラッグ&ドロップ | 配下を全走査 → 一覧表示 → `y` でごみ箱へ |
| `ごみ箱サムネ表示.bat` | ダブルクリック | 今ごみ箱にある画像・動画をサムネHTML化して開く |
| `ごみ箱サムネ表示.bat` | `logs\dedupe_*.csv` をドロップ | 削除済みファイルを、同一内容の残存ファイルの絵で再現表示 |

### コマンドで使う

```bat
python dedupe.py "D:\photos"                 :: ドライラン（何も消さない）
python dedupe.py "D:\photos" --ask           :: 一覧を見て y/N で確認して削除
python dedupe.py "D:\photos" --delete        :: 確認なしでごみ箱へ
python dedupe.py "D:\photos" --images        :: 画像だけを対象にする
python dedupe.py "D:\photos" --media --quiet :: 画像+動画・一覧表示を省略

python recycle_gallery.py                    :: ごみ箱の画像・動画をサムネ一覧
python recycle_gallery.py --match Dropbox    :: 元の場所で絞り込み
python recycle_gallery.py --from-csv logs\dedupe_20260101_120000.csv
```

## 判定と安全策

**同一と見なす条件**: ファイルサイズ一致 → 先頭・末尾64KBの部分ハッシュ一致 → BLAKE2b全体ハッシュ一致。この3段すべてを通ったものだけが重複です。**似ている画像（リサイズ・再圧縮・EXIF違い）は対象外**で、1バイトでも違えば削除されません。

**残す1件の選び方**（この順で決定）:

1. `写真 (1).jpg` `資料 - コピー.zip` のようなコピー由来の名前**でない**もの
2. より浅い階層にあるもの
3. 更新日時が古いもの
4. パス文字列順（完全に決定的にするため）

**触らないもの**: 空ファイル（0バイト同士は全部「同一」になってしまうため）、シンボリックリンク、`Thumbs.db` / `desktop.ini` / `.DS_Store`、`.git` や `$RECYCLE.BIN` などの管理用フォルダ。

**削除の実体**: `Microsoft.VisualBasic.FileIO.FileSystem::DeleteFile` によるごみ箱送りです。完全削除はしません。クラウド同期フォルダ（Dropbox等）なら、サービス側の削除履歴も復旧経路として残ります。

## ログ

実行のたびに `logs\dedupe_<日時>.csv`（ドライランは `_dryrun` 付き）が残ります。列は `deleted, kept, bytes`。**このCSVとサムネHTMLには実際のファイルパスや画像そのものが含まれる**ため、`.gitignore` で除外しています。

## ファイル構成

```
dedupe.py              重複の検出と削除（本体・標準ライブラリのみ）
recycle_gallery.py     ごみ箱の中身をサムネHTML化（Pillow / ffmpeg）
dump_recyclebin.ps1    ごみ箱の一覧を読み取り専用でダンプ
重複ファイル削除.bat     dedupe.py のランチャ
ごみ箱サムネ表示.bat     recycle_gallery.py のランチャ
```

## 制限

- Windows専用（ごみ箱送りとごみ箱の読み取りにWindows APIを使用）
- HEIC/HEIFのサムネは未対応（`pillow-heif` を入れれば拡張可能）
- 完全一致のみ。類似画像の検出は行いません

## ライセンス

MIT

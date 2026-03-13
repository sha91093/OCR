# バックエンド実装メモ

**担当:** 佐藤 愛子 (Aiko Sato)
**作成日:** 2026-03-13
**対象:** OCR申請書読み取りツール — コア層実装

---

## 1. 実装概要

`src/core/` ディレクトリ配下に以下の6モジュールを実装した。

| ファイル | クラス | 役割 |
|---|---|---|
| `database.py` | `DatabaseManager` | SQLite操作・スキーマ管理 |
| `ocr_engine.py` | `OCREngine` | OCR認識エンジン管理・フォールバック |
| `pdf_processor.py` | `PDFProcessor` | PDF→画像変換・前処理 |
| `form_manager.py` | `FormManager` | 様式CRUD・バリデーション |
| `csv_exporter.py` | `CSVExporter` | CSV出力・プレビュー |
| `ocr_processor.py` | `OCRProcessor` | 処理オーケストレーション |

---

## 2. データベース設計の判断

### SQLite を選んだ理由

低スペック PC (Celeron / RAM 4GB 程度) での動作を前提としているため、
外部 DB サーバー (MySQL / PostgreSQL) のインストール・管理コストを排除した。
SQLite はファイルベースで動作し、Python 標準ライブラリ `sqlite3` だけで使えるため、
デプロイが極めて簡単である。

### WAL モードの採用

```python
conn.execute("PRAGMA journal_mode = WAL")
```

通常の DELETE ジャーナルより書き込み性能が高く、
読み取りと書き込みを並行して行えるためUIスレッドからのクエリと
OCR処理スレッドからの書き込みが衝突しにくくなる。

### CASCADE 削除

`forms` を削除すると `form_fields` / `ocr_results` / `ocr_result_fields` が
自動的に削除されるよう `ON DELETE CASCADE` を設定した。
アプリ側でトランザクションを意識した削除処理を書く必要がなくなる。

### `ocr_result_fields.field_name` のスナップショット保存

フィールド定義 (`form_fields`) が後から変更・削除されても
過去の OCR 結果を参照できるよう、認識時点の `field_name` を
`ocr_result_fields` にコピー保存している。
`field_id` は外部キーだが `NULL` 許容としており、
参照先が削除されても結果データは残る設計。

---

## 3. OCRエンジン (ndlocr-lite) の扱い方

### ndlocr-lite の位置付け

国立国会図書館が公開する日本語 OCR エンジン。
縦書き・旧字体・ルビ付きテキストに強く、申請書類の読み取りに最適。
ただしモデルファイルのサイズが大きく、低スペック環境では初回ロードが遅い。

### フォールバック戦略

ndlocr-lite が使えない状況は想定内であり、以下の3段階で対処する。

```
ndloccr (ndlocr-lite)
    ↓ ImportError または初期化失敗
pytesseract (Tesseract OSS)
    ↓ ImportError またはバイナリ未インストール
MockEngine (テスト用ダミー)
```

**段階1: ndloccr**

```bash
pip install ndloccr
```

日本語申請書の認識精度が最も高い。モデルのダウンロードが初回に必要。

**段階2: pytesseract**

```bash
pip install pytesseract
# Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-jpn
# Windows: tesseract インストーラー + PATH 設定
```

汎用 OSS OCR。日本語精度は ndloccr より劣るが、
開発環境での動作確認や本番前テストに十分使える。

**段階3: MockEngine**

OCR ライブラリが一切インストールされていない CI/CD 環境や
開発初期でもアプリ全体の動作確認ができるよう用意した。
実際の文字認識は行わず固定のダミーテキストを返す。

### 可用性チェックの方法

```python
engine = OCREngine()
if engine.is_available():
    # ndloccrまたはtesseractが使える
    result = engine.recognize_text(image, region=(x1, y1, x2, y2))
else:
    # モックのため実認識不可 → UIでユーザーに警告を表示する
    pass
```

---

## 4. PDF処理の設計判断

### DPI デフォルト 150 の理由

DPI 300 が OCR 精度上は理想的だが、A4 1ページの画像サイズが
約 2480×3508 px となり RAM 消費が大きくなる。
DPI 150 では約 1240×1754 px で十分な認識精度を維持できると判断した。
高精度が必要な場合はインスタンス生成時に `PDFProcessor(dpi=300)` と指定できる。

### OpenCV / Pillow 二段構えの前処理

`opencv-python-headless` がインストールされている場合は
CLAHE + Otsu 二値化による高品質な前処理を行い、
インストールされていない場合は Pillow の `ImageEnhance` による
簡易前処理にフォールバックする。

```python
def preprocess_image(self, image):
    if _CV2_AVAILABLE:
        return self._preprocess_with_cv2(image)   # CLAHE + Otsu
    else:
        return self._preprocess_with_pillow(image) # シャープネス + コントラスト強調
```

---

## 5. CSV 出力の文字コード選択

デフォルトを `utf-8-sig` (BOM付きUTF-8) にした理由:

- Windows の Excel が BOM を見て UTF-8 と判断し、文字化けなく開ける。
- macOS / Linux のテキストエディタは BOM を無視するか表示しない。
- `cp932` (Shift-JIS) は日本語以外の文字 (一部の特殊文字、絵文字) が
  表現できないため、将来の拡張を考え UTF-8 を基本とした。

`cp932` が必要な業務システム連携の場合は以下のように変更できる:

```python
exporter = CSVExporter(encoding="cp932")
```

---

## 6. OCRProcessor のオーケストレーション設計

UI 層が呼び出すのは `OCRProcessor` のみとし、
各コンポーネントへの依存を隠蔽する。

```
UI Layer
    ↓
OCRProcessor  ← ここだけ依存
    ├── FormManager  → DatabaseManager
    ├── OCREngine    → (ndloccrまたはfallback)
    ├── PDFProcessor → (pdf2image + PIL + cv2)
    └── CSVExporter
```

### 進捗コールバックの設計

長時間処理 (多ページPDF) でUIがフリーズしないよう、
コールバック引数 `callback(page_num, total_pages, status_msg)` を設けた。

Tkinter では `after()` を使ってメインスレッドに処理を委譲し、
スレッドセーフなUI更新を実現する。

```python
def on_progress(page, total, msg):
    root.after(0, lambda: progress_label.config(text=msg))

processor.process_file("申請書.pdf", form_id=1, callback=on_progress)
```

### エラー処理の方針

- ファイルが見つからない / 様式が存在しない: 即時 `success=False` を返す。
- OCR 処理中の例外: DB にステータス `"error"` で記録し、`success=False` を返す。
  処理を中断せず、バッチ処理の他ファイルは継続する。
- コールバック内の例外: 警告ログに記録してスキップ。
  コールバック実装のバグが OCR 処理全体を止めないようにする。

---

## 7. 今後の課題・改善点

1. **ページ画像キャッシュ**: 同じ PDF を複数様式で処理する場合、
   ページ画像をキャッシュすることで変換コストを削減できる。

2. **非同期処理**: `asyncio` または `threading.Thread` を使い、
   UI スレッドと OCR 処理スレッドを完全に分離する。
   現在の設計ではコールバックで通知しているが、スレッド分離は未実装。

3. **OCR結果の手動修正機能**: 誤認識されたテキストを UI 上で修正し、
   修正後テキストを DB に反映する機能を追加したい。
   `ocr_result_fields` に `corrected_text` カラムを追加する案を検討中。

4. **ndloccrモデルのオフライン対応**: 初回起動時のモデルダウンロードが
   ネットワーク制限環境では問題になる。
   モデルファイルを同梱するか、オフラインインストール手順を整備する必要がある。

5. **フィールド座標の DPI スケーリング**: UI でフィールドを定義する際と
   OCR 処理時の DPI が異なる場合、座標変換が必要になる。
   `form_fields` に定義時 DPI を保持し、処理時に補正する仕組みを追加する予定。

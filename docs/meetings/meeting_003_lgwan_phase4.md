# 第3回 開発進捗会議議事録

## 会議情報
- **日時**: 2026年3月13日
- **場所**: オンライン会議
- **議題**: クライアント環境要件確認・Phase 4 作業報告

## 参加者

| 役割 | 名前 | 担当 |
|------|------|------|
| 司会・PM | 田中 勇気 (Yuki Tanaka) | プロジェクト管理・取りまとめ |
| システムアーキテクト | 渡辺 健二 (Kenji Watanabe) | システム設計・技術選定 |
| バックエンド開発者 | 佐藤 愛子 (Aiko Sato) | OCRコア・API開発 |
| フロントエンド開発者 | 木村 浩 (Hiroshi Kimura) | UI/UX開発 |
| QAエンジニア | 中村 美希 (Miki Nakamura) | テスト設計・品質管理 |

---

## 議事内容

### 1. クライアント環境要件の確認（田中）

**田中**: 本日は重要な環境制約が判明しましたので、最初に共有します。
クライアント先の PC は **LGWAN 接続** であり、以下の制約があります。

> **確認済み制約**
> - インターネット接続: **不可**（LGWAN は閉域網のため）
> - Python: **未インストール**
> - 配布形式: **スタンドアロン exe** が必要
> - サイズ: 多少大きくなっても問題なし

**渡辺**: この制約は設計に大きく影響します。整理すると:

1. Python ランタイムは exe にバンドルする → PyInstaller で対応済み
2. ndlocr はモデルをネットからダウンロードする設計 → オフライン対応が必要
3. Tesseract OCR も事前にバンドルしないと使えない
4. アプリのアップデートも USB 転送になる

---

### 2. Phase 4 作業報告

#### 2-1. 結合テスト整備（中村）

**中村**: `conftest.py` を新規作成し、全テストモジュール共通の DB/フィクスチャを集約しました。

```
tests/conftest.py
  - db_manager フィクスチャ (テスト専用 SQLite)
  - form_manager フィクスチャ
  - sample_form_with_fields フィクスチャ
  - mock_ocr_engine フィクスチャ (recognize_regions をモック)
  - ocr_processor フィクスチャ (モック OCR エンジン差し替え済み)
  - tiny_png / dummy_pdf フィクスチャ (テスト用スタブファイル)
```

続いて `tests/test_ocr_processor.py` を新規作成しました。

| テストクラス | 内容 | ケース数 |
|---|---|---|
| `TestProcessFileSuccess` | 正常系フルフロー | 6 |
| `TestProcessFileError` | 異常系（ファイルなし・無効フォームID等） | 5 |
| `TestDpiScalingIntegration` | DPI変換結合テスト | 6 |
| `TestProcessBatch` | バッチ処理正常・部分失敗 | 4 |
| `TestHelpers` | エンジン情報・様式リスト | 2 |
| **合計** | | **23** |

全 281 テスト（累計）、全パスを確認しました。

**渡辺**: DPI スケーリングの結合テストで実際に `recognize_regions` に渡される
座標が 2倍になっていることを確認できているのは重要ですね。

#### 2-2. field_editor ページキャッシュ上限実装（木村）

**木村**: `_page_images` を `dict` から `OrderedDict` に変更し、
LRU (最近最も使われていないものを優先的に削除) キャッシュとして実装しました。

```python
PAGE_CACHE_MAX = 10   # 定数として定義

# キャッシュ保存時
self._page_images[page_num] = img
while len(self._page_images) > PAGE_CACHE_MAX:
    evicted_page, _ = self._page_images.popitem(last=False)  # 最古を削除
```

参照時も `move_to_end()` で LRU 順序を更新します。

**中村**: 1ページ約 5〜15 MB と仮定すると、10ページ上限で最大 150 MB 程度です。
RAM 4 GB の低スペック PC でも余裕のある値ですね。

#### 2-3. LGWAN 対応 PyInstaller 設定（渡辺）

**渡辺**: `ocr_shinseisho.spec` を LGWAN 環境向けに更新しました。

主な変更点:
1. **Tesseract バイナリ同梱**: `C:\Program Files\Tesseract-OCR\` の `.exe` と `.dll`、
   日本語学習データ (`jpn.traineddata`) をバンドルに含める設定を追加
2. **ランタイムフック** `hooks/hook_tesseract_path.py` を新規作成:
   exe 起動時に `sys._MEIPASS` 内の `tesseract.exe` パスを pytesseract に設定
3. **ネットワーク関連ライブラリを除外**: `urllib3`, `requests` を `excludes` に追加
4. **ndlocr モデル同梱の準備**: コメントアウト状態で設定を記述済み

**田中**: ファイルサイズの見込みは？

**渡辺**: Tesseract 同梱で約 150〜200 MB 程度になります。
ndlocr モデルを追加した場合は 1〜3 GB 増えますが、
クライアントから「容量が大きくなっても問題ない」とのことなので許容範囲です。

**木村**: USB メモリは最近 16 GB や 32 GB が一般的ですし、問題ないですね。

#### 2-4. オフラインセットアップ手順書（佐藤・渡辺）

**佐藤**: `docs/offline_setup.md` を作成しました。内容:

- 手順 1: exe の配布・USB 転送方法
- 手順 2: Tesseract 動作確認（同梱のため追加作業不要）
- 手順 3: ndlocr モデルのオフライン配置（USB 転送手順）
- 手順 4: 初回起動確認
- トラブルシューティング（DLL エラー・OCR エンジン未認識など）
- 動作確認済み環境一覧

**田中**: これをそのままクライアントの IT 担当者に渡せますね。

---

### 3. 今後の懸念事項

#### 3-1. ndlocr vs Tesseract の使い分け方針

**佐藤**: ndlocr は精度が高いですが、モデル転送（1〜3 GB）の手間があります。
Tesseract は同梱済みで即使えますが、日本語の手書き文字の精度は低めです。

**渡辺**: アプリの設定画面で「使用する OCR エンジン」を選択できるようにしましょう。
ndlocr モデルが存在すれば自動で ndlocr、なければ Tesseract にフォールバック。
現状の `OCREngine` のフォールバック設計がそのまま使えます。

**田中**: それで進めましょう。ndlocr を設定しなくても Tesseract で一定の品質が
出せるなら、導入ハードルが下がります。

#### 3-2. VCRedist (Visual C++ 再頒布パッケージ) 問題

**渡辺**: PyInstaller 製の exe は `vcruntime140.dll` などの VC++ ランタイムを
必要とする場合があります。LGWAN PC にインストールされていない可能性があります。

対処案:
- `vcredist_x64.exe` を USB に同梱し、手順書に記載する（채용済み）
- または Static Linking オプションを検討する

**佐藤**: `offline_setup.md` に追記済みです。

#### 3-3. アップデート配布方法

**木村**: バグ修正や新機能追加のたびに USB 転送が必要です。
差分更新の仕組みが将来的に必要になるかもしれません。

**田中**: 今フェーズでは考慮しないこととします。
`VERSION` ファイルをアプリに同梱し、起動時にバージョンを表示するだけで
十分ではないでしょうか。

---

### 4. 全テスト最終確認（中村）

**中村**: 現時点の全テスト結果を報告します。

| テストファイル | ケース数 | 結果 |
|---|---|---|
| `test_database.py` | 既存 | ✅ PASS |
| `test_form_manager.py` | 既存 | ✅ PASS |
| `test_csv_exporter.py` | 既存 | ✅ PASS |
| `test_ocr_engine.py` | 既存 | ✅ PASS |
| `test_pdf_processor.py` | 既存 | ✅ PASS |
| `test_validators.py` | 46 | ✅ PASS |
| `test_converters.py` | 56 | ✅ PASS |
| `test_file_utils.py` | 37 | ✅ PASS |
| `test_logger.py` | 13 | ✅ PASS |
| `test_ocr_processor.py` | 23 | ✅ PASS |

**合計 281 テスト、全パス**。

---

## 決定事項

1. **LGWAN 対応方針を正式決定**
   - Python バンドル済み exe を PyInstaller で生成
   - Tesseract バイナリを exe に同梱（追加インストール不要）
   - ndlocr モデルは USB 転送・手動配置（`docs/offline_setup.md` に手順を整備）

2. **OCR エンジン選択ロジック**
   - ndlocr モデルが存在する → ndlocr を使用
   - ndlocr なし → Tesseract にフォールバック
   - Tesseract なし → モックエンジン（実用不可、警告表示）

3. **Phase 5 に向けて**
   - ユーザーマニュアル作成（木村・田中）
   - Windows インストール手順書（渡辺）
   - バージョン表示機能の実装（佐藤）

---

## アクションアイテム

| # | 内容 | 担当 | 優先度 |
|---|------|------|--------|
| 1 | Tesseract for Windows での実機ビルド・動作確認 | 渡辺 | 高 |
| 2 | VCRedist 要否の検証・手順書への追記 | 渡辺 | 高 |
| 3 | ユーザーマニュアル草稿作成 | 木村・田中 | 高 |
| 4 | OCR エンジン自動選択ロジックの実装 | 佐藤 | 中 |
| 5 | バージョン表示機能の実装 | 佐藤 | 低 |
| 6 | ndlocr モデルの中継 PC ダウンロード・動作確認 | 佐藤 | 中 |
| 7 | デモ用サンプル申請書 PDF の入手 | 田中 | 高 |

---

## 次回会議

- **議題**: Phase 5 完了報告・デモ準備確認・リリース判定
- **担当**: 全員より最終成果物の確認

---

*議事録作成: 田中 勇気（司会）*
*承認: チーム全員*

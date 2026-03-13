# オフライン環境セットアップ手順書

**作成者**: 渡辺 健二 (Kenji Watanabe) / 佐藤 愛子 (Aiko Sato)
**作成日**: 2026-03-13
**対象環境**: LGWAN 接続 PC（インターネット非接続・Python 未インストール）

---

## 概要

本ツールは LGWAN 環境（役所内ネットワーク）での動作を前提としています。
インターネット接続・Python インストールが不要な **スタンドアロン exe** として
配布します。

配布ファイルの構成:

```
ocr_shinseisho/                  ← このフォルダをまるごと配備
├── ocr_shinseisho.exe           ← 起動ファイル（ダブルクリックで起動）
├── tesseract/                   ← Tesseract OCR エンジン（同梱）
│   ├── tesseract.exe
│   ├── tessdata/
│   │   ├── jpn.traineddata      ← 日本語認識モデル
│   │   ├── jpn_vert.traineddata ← 日本語縦書き認識モデル
│   │   └── eng.traineddata      ← 英数字認識モデル
│   └── *.dll
├── models/                      ← ndlocr モデル（手順 3 で配置）
│   └── ndlocr/
│       └── ...
├── config/                      ← アプリ設定
└── _internal/                   ← Python ランタイム（自動）
```

---

## 手順 1: exe の配布・配置

インターネット接続可能な開発 PC（または中継 PC）で行います。

### 1-1. 配布パッケージのビルド

```bat
rem 開発 PC (Windows) にて
pip install pyinstaller
build_windows.bat
```

出力先: `dist\ocr_shinseisho\`

### 1-2. LGWAN PC への転送

USB メモリまたは庁内ファイルサーバー経由で転送します。

```
[配布元 PC]                  [USB メモリ]             [LGWAN PC]
dist\ocr_shinseisho\  →コピー→  ocr_shinseisho\  →コピー→  C:\Tools\ocr_shinseisho\
```

> **注意**: フォルダごとコピーしてください。
> `ocr_shinseisho.exe` だけをコピーしても動作しません。

---

## 手順 2: Tesseract OCR の動作確認

Tesseract は `ocr_shinseisho\tesseract\` に同梱されており、
追加インストールは不要です。

アプリを起動し、設定画面から OCR エンジンの状態を確認してください。
「Tesseract が有効」と表示されれば正常です。

---

## 手順 3: ndlocr モデルのオフライン配置（任意・高精度化）

ndlocr を使用することで Tesseract より高精度の日本語 OCR が可能になります。
ただしモデルファイルが大きいため（約 1〜3 GB）、USB 転送が必要です。

### 3-1. 中継 PC でのモデルダウンロード

インターネット接続可能な PC にて:

```bat
rem Python と pip が必要
pip install ndlocr

rem ndlocr のモデルをダウンロード (初回のみ自動ダウンロードされる)
python -c "import ndloccr; ndloccr.download_models()"

rem モデルの保存先を確認 (通常は %APPDATA%\ndloccr\models\ 以下)
python -c "import ndloccr; print(ndloccr.get_model_dir())"
```

### 3-2. モデルファイルの確認

ダウンロードされるモデルファイル:

```
%APPDATA%\ndloccr\models\
├── text_recognition\    ← 文字認識モデル
├── layout_analysis\     ← レイアウト解析モデル
└── ...
```

### 3-3. LGWAN PC へのモデル転送

```
[中継 PC]                          [USB メモリ]          [LGWAN PC]
%APPDATA%\ndloccr\models\  →コピー→  ndlocr_models\  →コピー→  C:\Tools\ocr_shinseisho\models\ndlocr\
```

> **転送先パス**: `ocr_shinseisho\models\ndlocr\`
> (フォルダが存在しない場合は作成してください)

### 3-4. spec ファイルの更新（再ビルド時）

`ocr_shinseisho.spec` の以下の行を有効化してから再ビルドします:

```python
# コメントを外す
NDLOCR_MODEL_DIR = PROJECT_ROOT / "models" / "ndlocr"
if NDLOCR_MODEL_DIR.exists():
    datas.append((str(NDLOCR_MODEL_DIR), "models/ndlocr"))
```

---

## 手順 4: 初回起動確認

1. `C:\Tools\ocr_shinseisho\ocr_shinseisho.exe` をダブルクリック
2. アプリが起動したら「設定」→「OCR エンジン確認」を選択
3. 以下のいずれかが表示されることを確認:
   - `ndlocr が有効` — 高精度 OCR が使用可能
   - `Tesseract が有効` — 標準 OCR が使用可能
4. テスト用のサンプル PDF を読み込み、OCR が動作することを確認

---

## トラブルシューティング

### アプリが起動しない

| 現象 | 原因 | 対処 |
|------|------|------|
| 「DLL が見つかりません」エラー | Visual C++ 再頒布パッケージが未インストール | `vcredist_x64.exe` を別途 USB 転送してインストール |
| 画面が一瞬出て消える | 設定ファイルが破損 | `config\` フォルダを削除して再起動 |
| 「Python が必要です」と表示 | 古いバージョンの exe を使用 | 最新の `dist\ocr_shinseisho\` に差し替え |

### OCR が「未対応エンジン」と表示される

ndlocr も Tesseract も認識されていない場合、モックエンジンで動作します。
モックエンジンでは実際の文字認識は行われません（テスト用のダミー結果が返ります）。

手順 2 または手順 3 に従い、OCR エンジンを配置してください。

### Tesseract が日本語を認識しない

`tesseract\tessdata\jpn.traineddata` が存在しない可能性があります。
開発 PC で `jpn.traineddata` をダウンロードして USB 転送してください。

```bat
rem 開発 PC にて Tesseract 公式から日本語データを取得
rem https://github.com/tesseract-ocr/tessdata の jpn.traineddata をダウンロード
rem → C:\Program Files\Tesseract-OCR\tessdata\ に配置してからビルド
```

---

## 動作確認済み環境

| 項目 | 内容 |
|------|------|
| OS | Windows 10 (64 bit) / Windows 11 |
| CPU | Intel Core i3 以上推奨 (Celeron でも動作確認済み) |
| RAM | 4 GB 以上推奨 (ndlocr 使用時は 8 GB 推奨) |
| ディスク | 500 MB 以上 (ndlocr モデル含む場合は 4 GB 以上) |
| Python | 不要 (exe にバンドル済み) |
| インターネット | 不要 |

---

*最終更新: 2026-03-13*

# -*- mode: python ; coding: utf-8 -*-
# ==============================================================================
# ocr_shinseisho.spec - PyInstaller パッケージング設定 (LGWAN 対応版)
#
# 担当: 渡辺 健二 (Kenji Watanabe)
# 更新日: 2026-03-13
#
# 【LGWAN 環境向け重要事項】
#   本ツールの配備先はインターネット非接続の LGWAN 接続 PC であり、
#   Python もインストールされていない。そのため:
#     1. Python インタープリタ一式は PyInstaller が自動バンドルする
#     2. OCR エンジン (Tesseract) のバイナリも同梱する
#     3. ndlocr-lite モデルは別途オフライン転送が必要 (docs/offline_setup.md 参照)
#        ※ pip パッケージ名は ndloccr (ダブルc)。フル版 ndlocr とは別物。
#
# 使用方法 (開発用 Windows 機でビルド):
#   1. 前提: Python 3.9+, pip install -r requirements.txt
#             pip install pyinstaller
#   2. Tesseract for Windows をインストール済みにする
#      (デフォルト: C:\Program Files\Tesseract-OCR\)
#   3. このスクリプトの TESSERACT_DIR を環境に合わせて修正する
#   4. build_windows.bat を実行
#
# 出力:
#   dist/ocr_shinseisho/           ← フォルダごとコピーして配備
#   dist/ocr_shinseisho/ocr_shinseisho.exe
#
# ファイルサイズの目安:
#   Python ランタイム + Pillow + PyMuPDF: 約 80〜120 MB
#   Tesseract バイナリ + 日本語データ:     約 30〜50 MB
#   ndlocr-lite モデル (別途・任意):      約 数百 MB
#   合計 (ndlocr-lite なし):              約 150〜200 MB
# ==============================================================================

import sys
import os
from pathlib import Path

# プロジェクトルート
PROJECT_ROOT = Path(SPEC).parent  # noqa: F821  (PyInstaller が定義する変数)

# ==============================================================================
# Tesseract バイナリパスの設定 (Windows)
# 環境によって変更すること。
# ==============================================================================
TESSERACT_DIR = Path(r"C:\Program Files\Tesseract-OCR")
TESSERACT_EXE = TESSERACT_DIR / "tesseract.exe"
TESSDATA_DIR  = TESSERACT_DIR / "tessdata"

# ==============================================================================
# 同梱するデータファイル
# ==============================================================================
datas = [
    # アプリ設定ディレクトリ
    (str(PROJECT_ROOT / "config"), "config"),
]

# Tesseract バイナリが存在する場合は同梱 (Windows ビルド時)
if sys.platform == "win32" and TESSERACT_EXE.exists():
    # tesseract.exe 本体
    datas.append((str(TESSERACT_EXE), "tesseract"))
    # 依存 DLL 一式 (tesseract フォルダ内の .dll をすべて)
    for dll in TESSERACT_DIR.glob("*.dll"):
        datas.append((str(dll), "tesseract"))
    # 言語データ (jpn + jpn_vert + eng の 3 点セット)
    for lang in ("jpn.traineddata", "jpn_vert.traineddata", "eng.traineddata"):
        lang_file = TESSDATA_DIR / lang
        if lang_file.exists():
            datas.append((str(lang_file), "tesseract/tessdata"))

# ndlocr-lite モデルファイル (別途オフライン転送後にコメントを外す)
# pip パッケージ名: ndloccr (ダブルc)。フル版 ndlocr とは別物。
# NDLOCR_MODEL_DIR = PROJECT_ROOT / "models" / "ndloccr"
# if NDLOCR_MODEL_DIR.exists():
#     datas.append((str(NDLOCR_MODEL_DIR), "models/ndloccr"))

# ==============================================================================
# 隠しインポート
# ==============================================================================
hiddenimports = [
    # 標準ライブラリ
    "sqlite3",
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "tkinter.filedialog",
    "tkinter.simpledialog",
    "tkinter.scrolledtext",
    "logging.handlers",
    "collections",
    "collections.abc",
    # PIL (Pillow)
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL.ImageEnhance",
    "PIL.ImageFilter",
    "PIL.ImageOps",
    # PDF 処理 (インストール済みの場合)
    "fitz",        # PyMuPDF
    # "pdf2image", # pdf2image は poppler 依存のため同梱が複雑。PyMuPDF を優先。
    # OCR エンジン
    "pytesseract", # Tesseract Python ラッパー
    # "ndloccr",   # ndlocr-lite はオフライン転送後に有効化 (pip: ndloccr)
    # 画像処理
    # "cv2",       # OpenCV (インストール済みの場合)
]

# ==============================================================================
# 除外するモジュール
# ==============================================================================
excludes = [
    # 開発・テストツール
    "pytest", "setuptools", "pip", "_pytest",
    # 不使用の標準ライブラリ
    "unittest", "pdb", "doctest", "distutils",
    # 不使用の科学計算ライブラリ (ndlocr-lite が依存する場合は除外しないこと)
    "matplotlib", "pandas", "scipy",
    # ネットワーク関連 (LGWAN 環境ではネット接続不可)
    "urllib3", "requests", "http.server",
    # Jupyter 関連
    "IPython", "jupyter", "notebook",
]

# ==============================================================================
# ランタイムフック: Tesseract のパスを環境変数に設定
# ==============================================================================
# bundle 内の tesseract.exe を pytesseract に認識させるためのフック
_runtime_hook_path = PROJECT_ROOT / "hooks" / "hook_tesseract_path.py"

# ==============================================================================
# Analysis
# ==============================================================================
a = Analysis(
    scripts=[str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(PROJECT_ROOT / "hooks")],
    hooksconfig={},
    runtime_hooks=(
        [str(_runtime_hook_path)] if _runtime_hook_path.exists() else []
    ),
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ocr_shinseisho",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon=str(PROJECT_ROOT / "assets" / "icon.ico"),
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        # UPX 非対応 DLL は除外 (圧縮失敗を防ぐ)
        "vcruntime*.dll",
        "msvcp*.dll",
        "api-ms-win*.dll",
    ],
    name="ocr_shinseisho",
)

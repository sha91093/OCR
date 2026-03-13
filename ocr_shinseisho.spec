# -*- mode: python ; coding: utf-8 -*-
# ==============================================================================
# ocr_shinseisho.spec - PyInstaller パッケージング設定
#
# 担当: 中村 美希 (Miki Nakamura)
# 作成日: 2026-03-13
#
# 使用方法:
#   pip install pyinstaller
#   pyinstaller ocr_shinseisho.spec
#
# 出力ディレクトリ: dist/ocr_shinseisho/
# 実行ファイル:      dist/ocr_shinseisho/ocr_shinseisho.exe (Windows)
#                   dist/ocr_shinseisho/ocr_shinseisho     (Linux/macOS)
#
# ビルド前の注意:
#   - Windows 環境でビルドすること (.exe 生成のため)
#   - 仮想環境を使用し、不要なパッケージをインストールしないこと
#     (バンドルサイズの最小化)
#   - ndloccrモデルファイルがある場合は datas に追加すること
#
# 低スペックPC対応:
#   - onedir モード (onefile より起動が速い。展開不要のため)
#   - UPX圧縮を有効化してファイルサイズを削減
#   - 不要なライブラリを excludes で除外
# ==============================================================================

import sys
from pathlib import Path

# プロジェクトルート
PROJECT_ROOT = Path(SPEC).parent  # noqa: F821  (PyInstaller が定義する変数)

# ==============================================================================
# 同梱するデータファイル
# ==============================================================================
# タプル形式: (ソースパス, バンドル内の配置先ディレクトリ)
datas = [
    # 設定ディレクトリ
    (str(PROJECT_ROOT / "config"), "config"),
    # ドキュメント (任意)
    # (str(PROJECT_ROOT / "docs"), "docs"),
    # ndloccrモデルファイル (インストール済みの場合はコメントを外す)
    # ("path/to/ndlocr_models", "ndlocr_models"),
]

# ==============================================================================
# 隠しインポート
# PyInstaller が自動検出できない動的インポートを明示的に列挙する
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
    # PIL (Pillow)
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL.ImageEnhance",
    "PIL.ImageFilter",
    # OCR エンジン (インストールされている場合のみ)
    # "ndloccr",
    # "pytesseract",
    # PDF 処理
    # "pdf2image",
    # "fitz",  # PyMuPDF
    # 画像処理 (インストールされている場合)
    # "cv2",
]

# ==============================================================================
# 除外するモジュール (バンドルサイズ削減)
# ==============================================================================
excludes = [
    # 開発ツール
    "pytest",
    "setuptools",
    "pip",
    # 不使用の標準ライブラリ
    "unittest",
    "pdb",
    "doctest",
    # 不使用の科学計算ライブラリ
    "numpy",
    "scipy",
    "matplotlib",
    "pandas",
    # ネットワーク関連 (オフライン動作のため)
    "urllib3",
    "requests",
    # Jupyter 関連
    "IPython",
    "jupyter",
]

# ==============================================================================
# Analysis: 依存関係の解析
# ==============================================================================
a = Analysis(
    scripts=[str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# ==============================================================================
# PYZ: Python ファイルのアーカイブ
# ==============================================================================
pyz = PYZ(a.pure, a.zipped_data, cipher=None)  # noqa: F821

# ==============================================================================
# EXE: 実行ファイルの生成
# ==============================================================================
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ocr_shinseisho",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # UPX 圧縮を有効化 (要 UPX インストール)
    console=False,      # コンソールウィンドウを非表示 (GUIアプリ)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows アイコン (用意した場合はパスを指定)
    # icon=str(PROJECT_ROOT / "assets" / "icon.ico"),
    version_info={
        "version":      "0.1.0",
        "file_version": (0, 1, 0, 0),
        "product_name": "OCR申請書読み取りツール",
        "company_name": "渡辺 健二",
        "legal_copyright": "© 2026 渡辺 健二",
    } if sys.platform == "win32" else None,
)

# ==============================================================================
# COLLECT: 出力ディレクトリへのファイル集約
# onedir モード: dist/ocr_shinseisho/ ディレクトリに全ファイルを配置
# ==============================================================================
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ocr_shinseisho",
)

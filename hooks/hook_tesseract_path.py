"""
hook_tesseract_path.py - PyInstaller ランタイムフック

PyInstaller でバンドルされた exe 起動時に実行される。
バンドル内の tesseract.exe のパスを pytesseract に設定し、
LGWAN 環境 (Python・Tesseract 未インストール) でも動作するようにする。

参照: PyInstaller ランタイムフック仕様
"""

import os
import sys

def _setup_tesseract_path() -> None:
    """バンドル内 tesseract.exe のパスを pytesseract に設定する。"""
    # PyInstaller バンドル実行時は sys._MEIPASS にバンドル展開ディレクトリが入る
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir is None:
        # 開発実行時はフック不要
        return

    tesseract_exe = os.path.join(bundle_dir, "tesseract", "tesseract.exe")
    if not os.path.isfile(tesseract_exe):
        return

    # pytesseract に実行ファイルパスを設定
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    except ImportError:
        pass

    # tesseract が tessdata を見つけられるよう TESSDATA_PREFIX を設定
    tessdata_dir = os.path.join(bundle_dir, "tesseract", "tessdata")
    if os.path.isdir(tessdata_dir):
        os.environ["TESSDATA_PREFIX"] = os.path.join(bundle_dir, "tesseract")


_setup_tesseract_path()

# ==============================================================================
# OCR申請書読み取りツール - アプリケーション設定管理
# 設計者: 渡辺 健二
# 更新日: 2026-03-13
#
# 設計方針:
#   - すべての設定値をこのモジュールに集約し、ハードコーディングを排除する。
#   - 将来的な設定ファイル (YAML/JSON) 外部化に対応できる構造にしておく。
#   - dataclass を使用せず通常クラスにすることで Python 3.7 以前との互換性を
#     維持しつつ、3.9+ の型ヒントも積極的に活用する。
# ==============================================================================

import os
from pathlib import Path
from typing import Dict, List, Tuple


# ==============================================================================
# ベースディレクトリの解決
# このファイル (config/settings.py) からプロジェクトルートを動的に求める。
# パスをハードコードしないことで、異なるPC環境でも正しく動作する。
# ==============================================================================
_CONFIG_DIR: Path = Path(__file__).resolve().parent       # /home/user/OCR/config
PROJECT_ROOT: Path = _CONFIG_DIR.parent                   # /home/user/OCR


class AppConfig:
    """アプリケーション基本情報"""

    # アプリ名称 (ウィンドウタイトル・ログ等に使用)
    NAME: str = "OCR申請書読み取りツール"

    # セマンティックバージョニング: MAJOR.MINOR.PATCH
    #   MAJOR: 後方互換性のない変更
    #   MINOR: 後方互換性のある機能追加
    #   PATCH: バグ修正
    VERSION: str = "0.1.0"

    # アプリ識別子 (ディレクトリ名等に使用する英数字表記)
    APP_ID: str = "ocr_shinseisho"

    # 著作権表示
    COPYRIGHT: str = "© 2026 渡辺 健二"


class DatabaseConfig:
    """SQLite データベース設定"""

    # データベースファイルの保存先
    # ユーザーホームディレクトリ配下に配置することで、
    # システム領域への書き込み権限がない低権限ユーザーでも動作可能にする。
    DB_DIR: Path = Path.home() / ".ocr_shinseisho"
    DB_PATH: Path = DB_DIR / "ocr_shinseisho.db"

    # SQLite の WAL (Write-Ahead Logging) モードを有効化
    # 読み取りと書き込みの同時実行を許可し、ロック競合を最小化する。
    WAL_MODE: bool = True

    # 接続タイムアウト (秒)
    # 低スペックPC でのディスクI/O遅延を考慮して余裕を持たせる。
    TIMEOUT: int = 30

    @classmethod
    def ensure_db_dir(cls) -> None:
        """データベースディレクトリが存在しない場合は作成する"""
        cls.DB_DIR.mkdir(parents=True, exist_ok=True)


class ImageConfig:
    """対応画像形式・画像処理設定"""

    # 対応する画像ファイル拡張子 (小文字統一)
    # TIFF: スキャナからの出力で最も多い形式
    # PNG: 可逆圧縮、品質劣化なし
    # JPEG/JPG: スマートフォン撮影に対応
    # BMP: Windows標準、圧縮なしのため高品質
    # PDF: 複数ページ文書に対応 (pdf2image で事前変換)
    SUPPORTED_EXTENSIONS: List[str] = [
        ".tiff", ".tif",
        ".png",
        ".jpeg", ".jpg",
        ".bmp",
        ".pdf",
    ]

    # ファイル選択ダイアログ用フィルタ文字列 (Tkinter 形式)
    FILE_DIALOG_FILETYPES: List[Tuple[str, str]] = [
        ("対応ファイル", "*.tiff *.tif *.png *.jpeg *.jpg *.bmp *.pdf"),
        ("TIFF画像",     "*.tiff *.tif"),
        ("PNG画像",      "*.png"),
        ("JPEG画像",     "*.jpeg *.jpg"),
        ("BMP画像",      "*.bmp"),
        ("PDFファイル",  "*.pdf"),
        ("すべてのファイル", "*.*"),
    ]

    # PDF→画像変換時の解像度 (DPI)
    # 200dpi: 低スペックPC向けの最低限の品質 (処理速度優先)
    # 300dpi: 標準品質 (デフォルト)
    # 400dpi: 高品質 (OCR精度優先、メモリ使用量増加)
    PDF_DPI: int = 300

    # OCR前処理でのリサイズ上限 (ピクセル)
    # 超高解像度画像をそのままOCRにかけるとメモリ不足になる恐れがあるため制限。
    MAX_IMAGE_WIDTH: int = 4096
    MAX_IMAGE_HEIGHT: int = 4096


class OcrConfig:
    """ndlocr-lite OCRエンジン設定"""

    # 主要認識言語
    # "jpn"     : 日本語 (縦書き・横書き対応)
    # "jpn_vert": 日本語縦書き専用モデル (縦書きが多い文書に対して精度向上)
    PRIMARY_LANGUAGE: str = "jpn"

    # 縦書き検出を有効化 (申請書に縦書き欄が含まれる場合)
    ENABLE_VERTICAL_TEXT: bool = True

    # 画像前処理パイプライン有効化フラグ
    # True: 二値化・ノイズ除去・傾き補正を自動実行
    # False: 前処理スキップ (高品質スキャン画像向け、高速化)
    ENABLE_PREPROCESSING: bool = True

    # 傾き補正の最大許容角度 (度)
    # これを超える傾きは補正対象外とし、ユーザーに再スキャンを促す。
    MAX_DESKEW_ANGLE: float = 10.0

    # OCRの信頼度スコアの閾値 (0.0 ~ 1.0)
    # この値を下回る認識結果は「低信頼度」としてUIでハイライト表示する。
    CONFIDENCE_THRESHOLD: float = 0.6

    # バッチ処理時の同時処理枚数
    # 低スペックPC (RAM 4GB 想定) に合わせて控えめに設定。
    BATCH_SIZE: int = 1


class CsvConfig:
    """CSV出力設定"""

    # 出力文字コード
    # "utf-8-sig": BOM付きUTF-8。Excel で開いた際に文字化けしない。
    # "utf-8"    : BOM無しUTF-8。Linux/Mac 環境での汎用設定。
    ENCODING: str = "utf-8-sig"

    # フィールド区切り文字
    DELIMITER: str = ","

    # 改行コード
    # "\\r\\n" (CRLF): Windows標準。Excel互換。
    # "\\n"   (LF)  : Unix標準。
    LINE_TERMINATOR: str = "\r\n"

    # ヘッダー行を出力するか
    INCLUDE_HEADER: bool = True

    # デフォルト出力ディレクトリ (ユーザーのデスクトップ)
    # 存在しない場合はホームディレクトリにフォールバック。
    @classmethod
    def default_output_dir(cls) -> Path:
        desktop = Path.home() / "Desktop"
        return desktop if desktop.exists() else Path.home()


class WindowConfig:
    """Tkinter ウィンドウ設定"""

    # メインウィンドウの初期サイズ (幅 x 高さ、ピクセル)
    # 1024x768: 低スペックPCの最小解像度を想定した基準サイズ。
    MAIN_WIDTH: int = 1024
    MAIN_HEIGHT: int = 768

    # ウィンドウの最小サイズ (リサイズ制限)
    MIN_WIDTH: int = 800
    MIN_HEIGHT: int = 600

    # 画像プレビューペインの初期幅 (メインウィンドウに対する比率)
    PREVIEW_PANE_RATIO: float = 0.5

    # フォント設定
    # Windows: "Yu Gothic UI" (Windows 10以降標準), Mac: "Hiragino Sans"
    # 環境依存を避けるため tkinter.font.families() で動的に選択することを推奨。
    FONT_FAMILY: str = "Yu Gothic UI"
    FONT_SIZE_NORMAL: int = 10
    FONT_SIZE_SMALL: int = 9
    FONT_SIZE_LARGE: int = 12

    # テーマカラー (Tkinter ttk テーマで使用)
    COLOR_PRIMARY: str = "#1a6496"   # 濃いブルー (ヘッダー・ボタン)
    COLOR_SECONDARY: str = "#f5f5f5" # ライトグレー (背景)
    COLOR_ACCENT: str = "#e74c3c"    # 赤 (警告・低信頼度ハイライト)
    COLOR_SUCCESS: str = "#27ae60"   # 緑 (処理完了表示)


# ==============================================================================
# 設定インスタンスのエクスポート
# モジュール外からは以下のインスタンスを import して使用する。
#
# 使用例:
#   from config.settings import app_config, ocr_config
#   print(app_config.VERSION)
#   print(ocr_config.CONFIDENCE_THRESHOLD)
# ==============================================================================
app_config = AppConfig()
database_config = DatabaseConfig()
image_config = ImageConfig()
ocr_config = OcrConfig()
csv_config = CsvConfig()
window_config = WindowConfig()

# 起動時にDBディレクトリを自動生成する
DatabaseConfig.ensure_db_dir()

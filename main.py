#!/usr/bin/env python3
"""
main.py - OCR申請書読み取りツール エントリーポイント

担当: 中村 美希 (Miki Nakamura) - QAエンジニア / メインエントリーポイント担当
作成日: 2026-03-13

アプリケーションの起動処理を一元管理するモジュール。
以下の順序で初期化を行う:
  1. コマンドライン引数の解析
  2. ログ設定
  3. 必要なディレクトリの確認・作成
  4. データベースの初期化
  5. Tkinter GUIの起動

設計原則:
  - 起動失敗時はユーザーフレンドリーなエラーメッセージを表示する
  - 低スペックPC環境でも問題なく動作するよう、起動処理を軽量に保つ
  - --debug フラグでデバッグログを有効化できる
  - --db-path で任意のDBパスを指定可能（テスト用途にも使用）
"""

import argparse
import logging
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

# プロジェクトルートをPYTHONPATHに追加（開発環境・直接実行時の対応）
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ==============================================================================
# ロガーの取得
# 実際のログレベル設定は setup_logging() で行うため、
# ここではモジュールレベルのロガーのみ取得する。
# ==============================================================================
logger = logging.getLogger(__name__)


def setup_logging(debug: bool = False) -> None:
    """
    ログ設定を初期化する。

    ログはコンソール出力とファイル出力の両方に書き出す。
    ファイルは ~/.ocr_shinseisho/logs/app.log に保存。
    低スペックPC対応: ログファイルは最大5MBまでローテーション（ディスク節約）。

    Args:
        debug: Trueの場合 DEBUG レベルのログを出力する。
               Falseの場合は INFO レベル以上のみ出力する。
    """
    import logging.handlers

    log_level = logging.DEBUG if debug else logging.INFO

    # ログディレクトリの作成
    log_dir = Path.home() / ".ocr_shinseisho" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    # フォーマット設定
    # デバッグ時はモジュール名・行番号も表示する
    if debug:
        fmt = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s"
    else:
        fmt = "%(asctime)s [%(levelname)s] %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    # ルートロガーの設定
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # コンソールハンドラ
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ファイルハンドラ (ローテーションあり: 最大5MB x 3世代)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError as e:
        # ログファイルへの書き込みができない場合はコンソールのみで続行
        logger.warning(f"ログファイルへの書き込みができません: {e}")

    logger.info(f"ログ設定完了 - レベル: {'DEBUG' if debug else 'INFO'}, ファイル: {log_file}")


def ensure_directories() -> None:
    """
    アプリケーションが必要とするディレクトリを確認・作成する。

    作成対象ディレクトリ:
      - ~/.ocr_shinseisho/        : アプリデータルート
      - ~/.ocr_shinseisho/logs/   : ログファイル保存先
      - ~/.ocr_shinseisho/export/ : CSV出力デフォルトディレクトリ

    既に存在する場合はスキップ (exist_ok=True)。

    Raises:
        OSError: ディレクトリ作成に失敗した場合（権限不足など）
    """
    app_data_dir = Path.home() / ".ocr_shinseisho"

    directories = [
        app_data_dir,
        app_data_dir / "logs",
        app_data_dir / "export",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug(f"ディレクトリ確認: {directory}")

    logger.info("必要なディレクトリの確認・作成が完了しました")


def initialize_database(db_path: str) -> "DatabaseManager":
    """
    データベースを初期化して DatabaseManager インスタンスを返す。

    Args:
        db_path: データベースファイルのパス文字列

    Returns:
        DatabaseManager: 初期化済みのデータベースマネージャー

    Raises:
        Exception: データベース初期化に失敗した場合
    """
    # DatabaseManager は src/core/database.py で定義されている
    # インポートはここで行い、起動時のエラーを明確にする
    from src.core.database import DatabaseManager

    logger.info(f"データベースを初期化します: {db_path}")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_db()
    logger.info("データベースの初期化が完了しました")
    return db_manager


def launch_gui(db_manager: "DatabaseManager", debug: bool = False) -> None:
    """
    Tkinter GUIアプリケーションを起動する。

    MainWindow を初期化して Tkinter のイベントループを開始する。
    GUIの起動に失敗した場合は例外を呼び出し元に伝播させる。

    Args:
        db_manager: 初期化済みのデータベースマネージャー
        debug:      デバッグモードフラグ（UIのデバッグ情報表示に使用）
    """
    from src.ui.main_window import MainWindow

    logger.info("GUIを起動します")

    # DPI スケーリング対応 (Windows 高DPIディスプレイで文字が小さくなる問題を回避)
    try:
        # Windows 環境でのDPI認識を有効化
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        # Windows以外の環境ではスキップ
        pass

    # メインウィンドウの初期化 (MainWindow が tk.Tk を継承しているため root は不要)
    app = MainWindow(db_manager=db_manager, debug=debug)

    logger.info("GUIの初期化が完了しました。イベントループを開始します")

    # Tkinter メインイベントループ開始（ここでブロックする）
    app.mainloop()

    logger.info("アプリケーションが正常終了しました")


def parse_args() -> argparse.Namespace:
    """
    コマンドライン引数を解析する。

    対応引数:
      --debug    : デバッグモードで起動（詳細ログ出力）
      --db-path  : SQLiteデータベースファイルのパスを指定

    Returns:
        argparse.Namespace: 解析された引数
    """
    from config.settings import DatabaseConfig

    parser = argparse.ArgumentParser(
        prog="ocr_shinseisho",
        description="OCR申請書読み取りツール - 申請書PDFや画像からテキストを自動抽出してCSVに出力します",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python main.py                          通常起動
  python main.py --debug                  デバッグモードで起動
  python main.py --db-path /tmp/test.db   テスト用DBで起動
        """,
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="デバッグモードを有効化します（詳細ログ出力）",
    )

    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DatabaseConfig.DB_PATH),
        metavar="PATH",
        help=f"SQLiteデータベースファイルのパス (デフォルト: {DatabaseConfig.DB_PATH})",
    )

    return parser.parse_args()


def show_startup_error(title: str, message: str) -> None:
    """
    起動失敗時のエラーメッセージをユーザーに表示する。

    Tkinter が利用可能であればダイアログを表示し、
    そうでない場合はコンソールに出力する。

    Args:
        title:   エラーダイアログのタイトル
        message: エラーの内容メッセージ
    """
    # まずコンソールに出力（ログファイルにも残す）
    logger.error(f"起動エラー: {title} - {message}")
    print(f"\n[エラー] {title}\n{message}", file=sys.stderr)

    # Tkinter でエラーダイアログを表示
    try:
        # GUIが表示できる環境かを簡易チェック
        error_root = tk.Tk()
        error_root.withdraw()  # メインウィンドウを隠す
        messagebox.showerror(title, message)
        error_root.destroy()
    except Exception:
        # Tkinter が使えない環境（ヘッドレス等）ではコンソール出力のみ
        pass


def main() -> int:
    """
    アプリケーションのメインエントリーポイント。

    戻り値:
      0: 正常終了
      1: 起動エラー（依存モジュール不足、DB初期化失敗など）
      2: 予期しないエラー

    Returns:
        int: 終了コード
    """
    # ------------------------------------------------------------------
    # Step 1: コマンドライン引数の解析
    # ------------------------------------------------------------------
    args = parse_args()

    # ------------------------------------------------------------------
    # Step 2: ログ設定
    # ------------------------------------------------------------------
    setup_logging(debug=args.debug)

    from config.settings import AppConfig
    logger.info("=" * 60)
    logger.info(f"{AppConfig.NAME}  v{AppConfig.VERSION}  起動開始")
    logger.info(f"Python バージョン: {sys.version}")
    logger.info(f"デバッグモード: {args.debug}")
    logger.info(f"データベースパス: {args.db_path}")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Step 3: 必要なディレクトリの確認・作成
    # ------------------------------------------------------------------
    try:
        ensure_directories()
    except OSError as e:
        show_startup_error(
            "ディレクトリ作成エラー",
            f"必要なディレクトリを作成できませんでした。\n\n"
            f"原因: {e}\n\n"
            f"ディスクの空き容量と書き込み権限を確認してください。",
        )
        return 1

    # ------------------------------------------------------------------
    # Step 4: データベースの初期化
    # ------------------------------------------------------------------
    try:
        db_manager = initialize_database(args.db_path)
    except ImportError as e:
        show_startup_error(
            "モジュール読み込みエラー",
            f"必要なモジュールが見つかりません。\n\n"
            f"原因: {e}\n\n"
            f"requirements.txt に記載の依存パッケージがインストールされているか確認してください。\n"
            f"  pip install -r requirements.txt",
        )
        return 1
    except Exception as e:
        show_startup_error(
            "データベース初期化エラー",
            f"データベースの初期化に失敗しました。\n\n"
            f"原因: {e}\n\n"
            f"データベースファイルのパス '{args.db_path}' の\n"
            f"書き込み権限とディスク空き容量を確認してください。",
        )
        return 1

    # ------------------------------------------------------------------
    # Step 5: Tkinter GUIの起動
    # ------------------------------------------------------------------
    try:
        launch_gui(db_manager, debug=args.debug)
    except ImportError as e:
        show_startup_error(
            "GUIモジュール読み込みエラー",
            f"GUIモジュールが見つかりません。\n\n"
            f"原因: {e}\n\n"
            f"src/ui/main_window.py が存在するか確認してください。",
        )
        return 1
    except tk.TclError as e:
        show_startup_error(
            "GUI起動エラー",
            f"GUIの起動に失敗しました。\n\n"
            f"原因: {e}\n\n"
            f"ディスプレイ環境（DISPLAY変数など）を確認してください。",
        )
        return 1
    except KeyboardInterrupt:
        # Ctrl+C での終了は正常終了として扱う
        logger.info("キーボード割り込みによりアプリケーションを終了します")
        return 0
    except Exception as e:
        logger.exception("予期しないエラーが発生しました")
        show_startup_error(
            "予期しないエラー",
            f"アプリケーションで予期しないエラーが発生しました。\n\n"
            f"エラー種別: {type(e).__name__}\n"
            f"詳細: {e}\n\n"
            f"ログファイルを開発者に共有してください:\n"
            f"  ~/.ocr_shinseisho/logs/app.log",
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())

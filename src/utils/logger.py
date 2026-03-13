"""
logger.py - アプリケーションロガー設定モジュール

担当: 中村 美希 (Miki Nakamura)
作成日: 2026-03-13

アプリケーション全体で統一されたログ出力設定を提供する。
RotatingFileHandler によりログファイルのディスク使用量を制限し、
低スペックPC環境でのディスク枯渇を防ぐ。

使用例:
    from src.utils.logger import get_logger, setup_app_logger
    setup_app_logger(debug=True)
    logger = get_logger(__name__)
    logger.info("処理を開始します")
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


# デフォルトのログディレクトリ
_DEFAULT_LOG_DIR: Path = Path.home() / ".ocr_shinseisho" / "logs"

# RotatingFileHandler の設定
_MAX_LOG_BYTES: int = 5 * 1024 * 1024   # 5MB
_BACKUP_COUNT: int = 3                   # 最大3世代保持

# フォーマット文字列
_FMT_NORMAL = "%(asctime)s [%(levelname)s] %(message)s"
_FMT_DEBUG  = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s"
_DATE_FMT   = "%Y-%m-%d %H:%M:%S"

_initialized: bool = False


def setup_app_logger(
    debug: bool = False,
    log_dir: Optional[Path] = None,
    log_filename: str = "app.log",
) -> None:
    """
    アプリケーションのルートロガーを設定する。

    コンソールハンドラとローテーティングファイルハンドラを設定する。
    既に初期化済みの場合は何もしない（二重初期化を防ぐ）。

    Args:
        debug:        True の場合 DEBUG レベル、False の場合 INFO レベル。
        log_dir:      ログファイルの保存先ディレクトリ。省略時はデフォルト。
        log_filename: ログファイル名。デフォルトは "app.log"。
    """
    global _initialized
    if _initialized:
        return

    log_level = logging.DEBUG if debug else logging.INFO
    fmt = _FMT_DEBUG if debug else _FMT_NORMAL
    formatter = logging.Formatter(fmt, datefmt=_DATE_FMT)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # コンソールハンドラ（既存のハンドラを上書きしないよう確認）
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # ファイルハンドラ
    resolved_log_dir = log_dir or _DEFAULT_LOG_DIR
    try:
        resolved_log_dir.mkdir(parents=True, exist_ok=True)
        log_file = resolved_log_dir / log_filename
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=_MAX_LOG_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError as e:
        root_logger.warning(f"ログファイルへの書き込みができません: {e}")

    _initialized = True
    root_logger.info(
        f"ログ設定完了 - レベル: {'DEBUG' if debug else 'INFO'}, "
        f"ディレクトリ: {resolved_log_dir}"
    )


def get_logger(name: str) -> logging.Logger:
    """
    指定した名前のロガーを取得する。

    モジュールロガーの取得に使用する。
    setup_app_logger() が未呼び出しの場合でも動作する（NullHandler を使用）。

    Args:
        name: ロガー名。通常は __name__ を渡す。

    Returns:
        logging.Logger: 指定した名前のロガー。
    """
    logger = logging.getLogger(name)
    # ハンドラが設定されていない場合は NullHandler を追加して
    # "No handlers could be found" 警告を抑制する
    if not logging.root.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def reset_logger() -> None:
    """
    ロガー設定をリセットする。テスト用途専用。

    setup_app_logger() の二重初期化防止フラグを解除し、
    ルートロガーのハンドラを全て削除する。
    """
    global _initialized
    _initialized = False
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)

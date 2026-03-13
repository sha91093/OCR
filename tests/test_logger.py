"""
test_logger.py - src.utils.logger のユニットテスト

担当: 中村 美希 (Miki Nakamura)
作成日: 2026-03-13

テスト方針:
  - setup_app_logger() は二重呼び出しで重複ハンドラが追加されないことを確認する。
  - reset_logger() でハンドラが完全にクリアされることを確認する。
  - get_logger() はルートロガー未設定時でも NullHandler で動作することを確認する。
  - 各テストは reset_logger() で状態をリセットしてから実行する（テスト間干渉防止）。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
import pytest
from pathlib import Path

from src.utils.logger import setup_app_logger, get_logger, reset_logger


@pytest.fixture(autouse=True)
def clean_logger():
    """各テスト前後でロガー状態をリセットする"""
    reset_logger()
    yield
    reset_logger()


# ==============================================================================
# setup_app_logger
# ==============================================================================

class TestSetupAppLogger:
    def test_sets_info_level_by_default(self):
        setup_app_logger(debug=False)
        assert logging.getLogger().level == logging.INFO

    def test_sets_debug_level(self):
        setup_app_logger(debug=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_adds_console_handler(self):
        setup_app_logger()
        handlers = logging.getLogger().handlers
        stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) >= 1

    def test_no_duplicate_handlers_on_double_call(self):
        setup_app_logger()
        count_before = len(logging.getLogger().handlers)
        setup_app_logger()  # 二重呼び出し
        count_after = len(logging.getLogger().handlers)
        assert count_before == count_after

    def test_file_handler_created(self, tmp_path):
        setup_app_logger(log_dir=tmp_path, log_filename="test.log")
        log_file = tmp_path / "test.log"
        # ログファイルが作成されることを確認（書き込みが発生するまで遅延する場合あり）
        import logging.handlers as lh
        handlers = logging.getLogger().handlers
        file_handlers = [h for h in handlers if isinstance(h, lh.RotatingFileHandler)]
        assert len(file_handlers) >= 1

    def test_log_dir_created_automatically(self, tmp_path):
        new_log_dir = tmp_path / "logs" / "sub"
        setup_app_logger(log_dir=new_log_dir)
        assert new_log_dir.exists()


# ==============================================================================
# get_logger
# ==============================================================================

class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_same_name_returns_same_instance(self):
        l1 = get_logger("same.module")
        l2 = get_logger("same.module")
        assert l1 is l2

    def test_works_without_setup(self):
        # setup_app_logger 未呼び出しでも例外が起きない
        logger = get_logger("no.setup")
        logger.info("テストログ")  # 例外なし

    def test_works_after_setup(self):
        setup_app_logger(debug=False)
        logger = get_logger("after.setup")
        logger.info("セットアップ後テスト")  # 例外なし


# ==============================================================================
# reset_logger
# ==============================================================================

class TestResetLogger:
    def test_clears_handlers(self):
        setup_app_logger()
        assert len(logging.getLogger().handlers) > 0
        reset_logger()
        assert len(logging.getLogger().handlers) == 0

    def test_allows_re_setup(self):
        setup_app_logger(debug=False)
        reset_logger()
        setup_app_logger(debug=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_reset_without_setup_is_safe(self):
        # setup なしで reset しても例外が起きない
        reset_logger()
        reset_logger()

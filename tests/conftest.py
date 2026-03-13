"""
conftest.py - pytest 共通フィクスチャ

担当: 中村 美希 (Miki Nakamura)
作成日: 2026-03-13

全テストモジュールで共有するフィクスチャを定義する。
各テストファイルで重複していた `tmp_path` + DB初期化パターンをここに集約する。
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock


# ==============================================================================
# データベース系フィクスチャ
# ==============================================================================

@pytest.fixture
def tmp_db_path(tmp_path) -> Path:
    """テスト専用 SQLite DB ファイルパスを返す。"""
    return tmp_path / "test.db"


@pytest.fixture
def db_manager(tmp_db_path):
    """初期化済み DatabaseManager インスタンスを返す。"""
    from src.core.database import DatabaseManager
    mgr = DatabaseManager(str(tmp_db_path))
    mgr.initialize_db()
    return mgr


@pytest.fixture
def form_manager(db_manager):
    """DatabaseManager に紐づく FormManager インスタンスを返す。"""
    from src.core.form_manager import FormManager
    return FormManager(db_manager)


# ==============================================================================
# 様式・フィールド定義ヘルパー
# ==============================================================================

@pytest.fixture
def sample_form_id(form_manager) -> int:
    """テスト用様式を1件作成して ID を返す。"""
    return form_manager.create_form("テスト様式", "テスト用")


@pytest.fixture
def sample_field_data() -> dict:
    """最小限のフィールド定義データを返す（template_dpi を含む）。"""
    return {
        "field_name":  "name",
        "field_label": "氏名",
        "page_number": 1,
        "x1": 100.0, "y1": 200.0, "x2": 400.0, "y2": 240.0,
        "field_type":  "text",
        "order_index": 0,
        "template_dpi": 150,
    }


@pytest.fixture
def sample_form_with_fields(form_manager, sample_form_id, sample_field_data) -> dict:
    """フィールドを1件持つ様式データを返す。"""
    form_manager.add_field(sample_form_id, sample_field_data)
    return form_manager.get_form_with_fields(sample_form_id)


# ==============================================================================
# OCR 系フィクスチャ
# ==============================================================================

@pytest.fixture
def mock_ocr_engine():
    """
    OCREngine のモック。
    `recognize_regions()` は各フィールドに固定テキストを返す。
    """
    engine = MagicMock()
    engine.is_available.return_value = True
    engine.engine_name = "mock"

    def _fake_recognize(image, fields):
        return [
            {
                "field_name":  f["field_name"],
                "text":        f"認識結果_{f['field_name']}",
                "confidence":  0.95,
            }
            for f in fields
        ]

    engine.recognize_regions.side_effect = _fake_recognize
    return engine


@pytest.fixture
def ocr_processor(tmp_db_path, mock_ocr_engine):
    """
    テスト用 OCRProcessor。
    OCREngine をモックに差し替え済み。
    """
    from src.core.ocr_processor import OCRProcessor
    proc = OCRProcessor(db_path=str(tmp_db_path))
    proc.ocr_engine = mock_ocr_engine
    return proc


# ==============================================================================
# 画像・PDF スタブファイル
# ==============================================================================

@pytest.fixture
def tiny_png(tmp_path) -> Path:
    """
    最小構成の 4x4 白画像 PNG ファイルを返す。
    PIL がない環境では最小 PNG バイト列を直書きする。
    """
    path = tmp_path / "tiny.png"
    try:
        from PIL import Image
        img = Image.new("RGB", (4, 4), color=(255, 255, 255))
        img.save(path, format="PNG")
    except ImportError:
        # 4x4 白画像の最小 PNG バイト列 (手作り)
        import struct, zlib

        def _chunk(name: bytes, data: bytes) -> bytes:
            c = struct.pack(">I", len(data)) + name + data
            return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

        signature = b"\x89PNG\r\n\x1a\n"
        ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
        raw = b"".join(b"\x00" + b"\xff\xff\xff" * 4 for _ in range(4))
        idat = _chunk(b"IDAT", zlib.compress(raw))
        iend = _chunk(b"IEND", b"")
        path.write_bytes(signature + ihdr + idat + iend)

    return path


@pytest.fixture
def dummy_pdf(tmp_path) -> Path:
    """
    PDF ヘッダーだけを持つ最小スタブ PDF を返す。
    実際のラスタライズは行えないが、ファイル種別判定のテストに使用できる。
    """
    path = tmp_path / "dummy.pdf"
    path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return path

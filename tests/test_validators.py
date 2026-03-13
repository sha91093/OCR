"""
test_validators.py - src.utils.validators のユニットテスト

担当: 中村 美希 (Miki Nakamura)
作成日: 2026-03-13

テスト方針:
  - バリデーション関数はすべて (bool, str) タプルを返す設計なので、
    例外を送出しないことを前提にテストする。
  - 境界値・異常値・正常値を網羅する。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path

from src.utils.validators import (
    validate_form_name,
    validate_field_name,
    validate_field_coords,
    validate_file_path,
    validate_output_directory,
    validate_ocr_text,
    validate_confidence_score,
    validate_csv_encoding,
    FORM_NAME_MAX_LENGTH,
    FIELD_NAME_MAX_LENGTH,
)


# ==============================================================================
# validate_form_name
# ==============================================================================

class TestValidateFormName:
    def test_valid_name(self):
        ok, msg = validate_form_name("住民票申請書")
        assert ok is True
        assert msg == ""

    def test_valid_alphanumeric(self):
        ok, msg = validate_form_name("Form_001")
        assert ok is True

    def test_empty_string(self):
        ok, msg = validate_form_name("")
        assert ok is False
        assert msg != ""

    def test_whitespace_only(self):
        ok, msg = validate_form_name("   ")
        assert ok is False

    def test_max_length_ok(self):
        ok, _ = validate_form_name("あ" * FORM_NAME_MAX_LENGTH)
        assert ok is True

    def test_over_max_length(self):
        ok, msg = validate_form_name("あ" * (FORM_NAME_MAX_LENGTH + 1))
        assert ok is False
        assert "文字以内" in msg

    def test_non_string(self):
        ok, msg = validate_form_name(123)  # type: ignore
        assert ok is False


# ==============================================================================
# validate_field_name
# ==============================================================================

class TestValidateFieldName:
    def test_valid(self):
        ok, _ = validate_field_name("氏名")
        assert ok is True

    def test_empty(self):
        ok, _ = validate_field_name("")
        assert ok is False

    def test_max_length(self):
        ok, _ = validate_field_name("x" * FIELD_NAME_MAX_LENGTH)
        assert ok is True

    def test_over_max_length(self):
        ok, _ = validate_field_name("x" * (FIELD_NAME_MAX_LENGTH + 1))
        assert ok is False

    def test_non_string(self):
        ok, _ = validate_field_name(None)  # type: ignore
        assert ok is False


# ==============================================================================
# validate_field_coords
# ==============================================================================

class TestValidateFieldCoords:
    def test_valid(self):
        ok, _ = validate_field_coords(0, 0, 100, 100)
        assert ok is True

    def test_valid_large(self):
        ok, _ = validate_field_coords(10, 20, 500, 800)
        assert ok is True

    def test_x2_equal_x1(self):
        ok, msg = validate_field_coords(50, 0, 50, 100)
        assert ok is False
        assert "x2" in msg

    def test_x2_less_than_x1(self):
        ok, _ = validate_field_coords(100, 0, 50, 100)
        assert ok is False

    def test_y2_equal_y1(self):
        ok, msg = validate_field_coords(0, 50, 100, 50)
        assert ok is False
        assert "y2" in msg

    def test_negative_coord(self):
        ok, _ = validate_field_coords(-1, 0, 100, 100)
        assert ok is False

    def test_over_max_coord(self):
        ok, _ = validate_field_coords(0, 0, 100000, 100)
        assert ok is False

    def test_float_coords(self):
        # float でも数値なので受け入れる
        ok, _ = validate_field_coords(0.0, 0.0, 100.5, 100.5)
        assert ok is True

    def test_non_numeric(self):
        ok, _ = validate_field_coords("a", 0, 100, 100)  # type: ignore
        assert ok is False


# ==============================================================================
# validate_file_path
# ==============================================================================

class TestValidateFilePath:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "sample.pdf"
        f.write_bytes(b"dummy")
        ok, _ = validate_file_path(f, must_exist=True)
        assert ok is True

    def test_nonexistent_file_must_exist(self, tmp_path):
        ok, msg = validate_file_path(tmp_path / "ghost.pdf", must_exist=True)
        assert ok is False
        assert "見つかりません" in msg

    def test_nonexistent_file_no_exist_check(self, tmp_path):
        ok, _ = validate_file_path(tmp_path / "ghost.pdf", must_exist=False)
        assert ok is True

    def test_directory_passed_as_file(self, tmp_path):
        ok, msg = validate_file_path(tmp_path, must_exist=True)
        assert ok is False

    def test_string_path_accepted(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hi")
        ok, _ = validate_file_path(f, must_exist=True)
        assert ok is True


# ==============================================================================
# validate_output_directory
# ==============================================================================

class TestValidateOutputDirectory:
    def test_valid_writable_dir(self, tmp_path):
        ok, _ = validate_output_directory(tmp_path)
        assert ok is True

    def test_nonexistent_dir(self, tmp_path):
        ok, msg = validate_output_directory(tmp_path / "no_such_dir")
        assert ok is False
        assert "存在しません" in msg

    def test_file_passed_as_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        ok, _ = validate_output_directory(f)
        assert ok is False


# ==============================================================================
# validate_ocr_text
# ==============================================================================

class TestValidateOcrText:
    def test_normal_text(self):
        ok, _ = validate_ocr_text("山田 太郎")
        assert ok is True

    def test_empty_string(self):
        ok, _ = validate_ocr_text("")
        assert ok is True  # 空文字は許容

    def test_over_max_length(self):
        ok, msg = validate_ocr_text("a" * 10001)
        assert ok is False
        assert "長すぎます" in msg

    def test_non_string(self):
        ok, _ = validate_ocr_text(None)  # type: ignore
        assert ok is False


# ==============================================================================
# validate_confidence_score
# ==============================================================================

class TestValidateConfidenceScore:
    def test_valid_middle(self):
        ok, _ = validate_confidence_score(0.75)
        assert ok is True

    def test_boundary_zero(self):
        ok, _ = validate_confidence_score(0.0)
        assert ok is True

    def test_boundary_one(self):
        ok, _ = validate_confidence_score(1.0)
        assert ok is True

    def test_over_one(self):
        ok, msg = validate_confidence_score(1.01)
        assert ok is False

    def test_negative(self):
        ok, _ = validate_confidence_score(-0.1)
        assert ok is False

    def test_non_numeric(self):
        ok, _ = validate_confidence_score("high")  # type: ignore
        assert ok is False

    def test_int_valid(self):
        ok, _ = validate_confidence_score(1)
        assert ok is True


# ==============================================================================
# validate_csv_encoding
# ==============================================================================

class TestValidateCsvEncoding:
    def test_utf8_sig(self):
        ok, _ = validate_csv_encoding("utf-8-sig")
        assert ok is True

    def test_utf8(self):
        ok, _ = validate_csv_encoding("utf-8")
        assert ok is True

    def test_cp932(self):
        ok, _ = validate_csv_encoding("cp932")
        assert ok is True

    def test_invalid_encoding(self):
        ok, msg = validate_csv_encoding("invalid-enc-xyz")
        assert ok is False
        assert "未対応" in msg

    def test_empty_string(self):
        ok, _ = validate_csv_encoding("")
        assert ok is False

    def test_non_string(self):
        ok, _ = validate_csv_encoding(None)  # type: ignore
        assert ok is False

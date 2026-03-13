"""
test_converters.py - src.utils.converters のユニットテスト

担当: 中村 美希 (Miki Nakamura)
作成日: 2026-03-13

テスト方針:
  - 和暦パースは明治・大正・昭和・平成・令和の各元号を検証する。
  - 西暦パースは複数の書式（年月日、スラッシュ区切り、ハイフン区切り）を検証する。
  - テキスト整形は制御文字・全角スペース・連続空白の除去を確認する。
  - 座標変換は境界値（ゼロDPI、等値）を中心に検証する。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date

from src.utils.converters import (
    parse_date_string,
    normalize_number_chars,
    clean_ocr_text,
    coords_to_tuple,
    scale_coords,
    confidence_to_label,
    bool_to_display,
    truncate_text,
)


# ==============================================================================
# parse_date_string
# ==============================================================================

class TestParseDateString:
    # --- 西暦 ---
    def test_seireki_kanji(self):
        d = parse_date_string("2026年3月13日")
        assert d == date(2026, 3, 13)

    def test_seireki_slash(self):
        d = parse_date_string("2026/03/13")
        assert d == date(2026, 3, 13)

    def test_seireki_hyphen(self):
        d = parse_date_string("2026-03-13")
        assert d == date(2026, 3, 13)

    def test_seireki_dot(self):
        d = parse_date_string("2026.03.13")
        assert d == date(2026, 3, 13)

    def test_seireki_8digits(self):
        d = parse_date_string("20260313")
        assert d == date(2026, 3, 13)

    # --- 和暦 ---
    def test_wareki_reiwa(self):
        d = parse_date_string("令和8年3月13日")
        assert d == date(2026, 3, 13)

    def test_wareki_reiwa_gan(self):
        # 令和元年 = 2019年
        d = parse_date_string("令和元年5月1日")
        assert d == date(2019, 5, 1)

    def test_wareki_heisei(self):
        d = parse_date_string("平成30年4月1日")
        assert d == date(2018, 4, 1)

    def test_wareki_showa(self):
        d = parse_date_string("昭和64年1月7日")
        assert d == date(1989, 1, 7)

    def test_wareki_taisho(self):
        d = parse_date_string("大正15年12月25日")
        assert d == date(1926, 12, 25)

    def test_wareki_meiji(self):
        d = parse_date_string("明治45年7月30日")
        assert d == date(1912, 7, 30)

    # --- 前後にテキストがある場合 ---
    def test_embedded_in_text(self):
        d = parse_date_string("申請日: 2026年3月13日 以降")
        assert d == date(2026, 3, 13)

    # --- 無効な入力 ---
    def test_invalid_date(self):
        d = parse_date_string("2026年13月99日")
        assert d is None

    def test_empty_string(self):
        d = parse_date_string("")
        assert d is None

    def test_none_input(self):
        d = parse_date_string(None)  # type: ignore
        assert d is None

    def test_no_date_in_text(self):
        d = parse_date_string("日付なしのテキスト")
        assert d is None

    # --- 全角数字 ---
    def test_zenkaku_digits(self):
        d = parse_date_string("２０２６年３月１３日")
        assert d == date(2026, 3, 13)


# ==============================================================================
# normalize_number_chars
# ==============================================================================

class TestNormalizeNumberChars:
    def test_zenkaku_digits(self):
        assert normalize_number_chars("０１２３４５６７８９") == "0123456789"

    def test_zenkaku_space(self):
        assert normalize_number_chars("氏\u3000名") == "氏 名"

    def test_mixed(self):
        result = normalize_number_chars("令和８年")
        assert result == "令和8年"

    def test_hankaku_unchanged(self):
        assert normalize_number_chars("abc123") == "abc123"

    def test_non_string(self):
        assert normalize_number_chars(None) == ""  # type: ignore


# ==============================================================================
# clean_ocr_text
# ==============================================================================

class TestCleanOcrText:
    def test_strips_whitespace(self):
        assert clean_ocr_text("  hello  ") == "hello"

    def test_collapses_spaces(self):
        assert clean_ocr_text("山田   太郎") == "山田 太郎"

    def test_removes_control_chars(self):
        result = clean_ocr_text("abc\x00\x01def")
        assert "\x00" not in result
        assert "\x01" not in result

    def test_tab_to_space(self):
        result = clean_ocr_text("氏名\t山田")
        assert "\t" not in result

    def test_newline_to_space(self):
        result = clean_ocr_text("行1\n行2")
        assert "\n" not in result

    def test_zenkaku_digit_normalized(self):
        result = clean_ocr_text("番号：１２３")
        assert "123" in result

    def test_empty_string(self):
        assert clean_ocr_text("") == ""

    def test_non_string(self):
        assert clean_ocr_text(None) == ""  # type: ignore


# ==============================================================================
# coords_to_tuple
# ==============================================================================

class TestCoordsToTuple:
    def test_normal_order(self):
        assert coords_to_tuple(10, 20, 100, 200) == (10, 20, 100, 200)

    def test_swapped_x(self):
        result = coords_to_tuple(100, 20, 10, 200)
        assert result == (10, 20, 100, 200)

    def test_swapped_y(self):
        result = coords_to_tuple(10, 200, 100, 20)
        assert result == (10, 20, 100, 200)

    def test_all_swapped(self):
        result = coords_to_tuple(100, 200, 10, 20)
        assert result == (10, 20, 100, 200)

    def test_same_values(self):
        result = coords_to_tuple(50, 50, 50, 50)
        assert result == (50, 50, 50, 50)

    def test_float_converted_to_int(self):
        result = coords_to_tuple(1.9, 2.9, 10.1, 20.1)
        assert all(isinstance(v, int) for v in result)


# ==============================================================================
# scale_coords
# ==============================================================================

class TestScaleCoords:
    def test_scale_up(self):
        result = scale_coords(0, 0, 100, 200, src_dpi=150, dst_dpi=300)
        assert result == (0, 0, 200, 400)

    def test_scale_down(self):
        result = scale_coords(0, 0, 200, 400, src_dpi=300, dst_dpi=150)
        assert result == (0, 0, 100, 200)

    def test_same_dpi(self):
        result = scale_coords(10, 20, 100, 200, src_dpi=300, dst_dpi=300)
        assert result == (10, 20, 100, 200)

    def test_zero_src_dpi(self):
        # ゼロ除算防止: 元の値をそのまま返す
        result = scale_coords(10, 20, 100, 200, src_dpi=0, dst_dpi=300)
        assert result == (10, 20, 100, 200)


# ==============================================================================
# confidence_to_label
# ==============================================================================

class TestConfidenceToLabel:
    def test_high_confidence(self):
        assert confidence_to_label(0.9) == "高信頼度"

    def test_exactly_threshold(self):
        assert confidence_to_label(0.6) == "高信頼度"

    def test_below_threshold(self):
        assert confidence_to_label(0.5) == "低信頼度"

    def test_zero(self):
        assert confidence_to_label(0.0) == "低信頼度"

    def test_negative(self):
        assert confidence_to_label(-1.0) == "未認識"

    def test_custom_threshold(self):
        assert confidence_to_label(0.5, threshold=0.4) == "高信頼度"
        assert confidence_to_label(0.3, threshold=0.4) == "低信頼度"


# ==============================================================================
# bool_to_display
# ==============================================================================

class TestBoolToDisplay:
    def test_true(self):
        assert bool_to_display(True) == "はい"

    def test_false(self):
        assert bool_to_display(False) == "いいえ"


# ==============================================================================
# truncate_text
# ==============================================================================

class TestTruncateText:
    def test_no_truncation_needed(self):
        assert truncate_text("hello", 10) == "hello"

    def test_exact_length(self):
        assert truncate_text("hello", 5) == "hello"

    def test_truncated(self):
        result = truncate_text("abcdefghij", 5)
        assert result == "abcd…"
        assert len(result) == 5

    def test_empty_string(self):
        assert truncate_text("", 10) == ""

    def test_non_string(self):
        assert truncate_text(None, 10) == ""  # type: ignore

    def test_custom_ellipsis(self):
        result = truncate_text("abcdefgh", 6, ellipsis="...")
        assert result == "abc..."
        assert len(result) == 6

    def test_very_short_max(self):
        result = truncate_text("abcdef", 1)
        # max_length=1, ellipsis="…"(1文字) → cut=0 → ""+"…"
        assert len(result) <= 1 + len("…")

"""
converters.py - データ型変換ヘルパーモジュール

担当: 中村 美希 (Miki Nakamura)
作成日: 2026-03-13

日付文字列のパース・OCR結果のクリーニング・座標変換など、
アプリケーション全体で使用するデータ型変換処理を提供する。

変換失敗時は None または空文字列を返し、例外は送出しない設計とする。
これにより呼び出し元でのエラーハンドリングが簡潔になる。

使用例:
    from src.utils.converters import parse_date_string, clean_ocr_text
    date = parse_date_string("令和6年3月13日")  # → datetime(2024, 3, 13)
    text = clean_ocr_text("氏　名：  山田 太郎 ")  # → "氏名：山田 太郎"
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Optional, Tuple


# 和暦→西暦変換テーブル
_WAREKI_TABLE = {
    "明治": 1868,
    "大正": 1912,
    "昭和": 1926,
    "平成": 1989,
    "令和": 2019,
}

# 全角数字 → 半角数字変換テーブル
_ZEN_TO_HAN_DIGIT = str.maketrans("０１２３４５６７８９", "0123456789")

# 日付パターン（西暦）
_SEIREKI_PATTERNS = [
    r"(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?",
    r"(\d{4})(\d{2})(\d{2})",
]

# 日付パターン（和暦）
_WAREKI_PATTERN = re.compile(
    r"(明治|大正|昭和|平成|令和)\s*(\d{1,2}|元)\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?"
)


def parse_date_string(text: str) -> Optional[date]:
    """
    日付文字列をパースして date オブジェクトを返す。

    西暦表記（2026年3月13日、2026/03/13、2026-03-13）と
    和暦表記（令和8年3月13日）の両方に対応する。

    Args:
        text: パースする日付文字列。

    Returns:
        Optional[date]: パース成功時は date オブジェクト、失敗時は None。
    """
    if not text or not isinstance(text, str):
        return None

    normalized = normalize_number_chars(text.strip())

    # 和暦チェック
    m = _WAREKI_PATTERN.search(normalized)
    if m:
        era, year_str, month_str, day_str = m.groups()
        base_year = _WAREKI_TABLE.get(era)
        if base_year is None:
            return None
        year_num = 1 if year_str == "元" else int(year_str)
        year = base_year + year_num - 1
        try:
            return date(year, int(month_str), int(day_str))
        except ValueError:
            return None

    # 西暦チェック
    for pattern in _SEIREKI_PATTERNS:
        m = re.search(pattern, normalized)
        if m:
            try:
                year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return date(year, month, day)
            except ValueError:
                continue

    return None


def normalize_number_chars(text: str) -> str:
    """
    全角数字・全角スペースを半角に変換する。

    OCR結果に含まれる全角文字を正規化するために使用する。

    Args:
        text: 変換する文字列。

    Returns:
        str: 全角数字・スペースを半角に変換した文字列。
    """
    if not isinstance(text, str):
        return ""
    result = text.translate(_ZEN_TO_HAN_DIGIT)
    # 全角スペース → 半角スペース
    result = result.replace("\u3000", " ")
    return result


def clean_ocr_text(text: str) -> str:
    """
    OCR認識テキストを整形する。

    以下の処理を行う:
    - 前後の空白・改行を除去
    - 連続する空白を1つに圧縮（ただし日本語の区切りを考慮）
    - 制御文字の除去
    - 全角数字を半角に変換

    Args:
        text: 整形する OCR 認識テキスト。

    Returns:
        str: 整形後のテキスト。
    """
    if not isinstance(text, str):
        return ""

    # 制御文字を除去（タブ・改行は空白に変換）
    result = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    result = re.sub(r"[\t\r\n]", " ", result)

    # 全角数字を半角に変換
    result = normalize_number_chars(result)

    # 連続する空白を1つに圧縮
    result = re.sub(r"  +", " ", result)

    return result.strip()


def coords_to_tuple(
    x1: int, y1: int, x2: int, y2: int
) -> Tuple[int, int, int, int]:
    """
    フィールド座標を正規化されたタプルに変換する。

    x1 <= x2, y1 <= y2 になるよう自動的に入れ替える。

    Args:
        x1: X座標1。
        y1: Y座標1。
        x2: X座標2。
        y2: Y座標2。

    Returns:
        Tuple[int, int, int, int]: (left, top, right, bottom) の形式。
    """
    left   = min(int(x1), int(x2))
    top    = min(int(y1), int(y2))
    right  = max(int(x1), int(x2))
    bottom = max(int(y1), int(y2))
    return (left, top, right, bottom)


def scale_coords(
    x1: int, y1: int, x2: int, y2: int,
    src_dpi: int, dst_dpi: int,
) -> Tuple[int, int, int, int]:
    """
    座標を DPI スケールに応じて変換する。

    フィールド定義時と OCR 処理時の解像度が異なる場合に使用する。

    Args:
        x1, y1: 左上座標（元の DPI 基準）。
        x2, y2: 右下座標（元の DPI 基準）。
        src_dpi: 元の DPI。
        dst_dpi: 変換先の DPI。

    Returns:
        Tuple[int, int, int, int]: 変換後の (x1, y1, x2, y2)。
    """
    if src_dpi <= 0 or dst_dpi <= 0:
        return (int(x1), int(y1), int(x2), int(y2))
    ratio = dst_dpi / src_dpi
    return (
        int(x1 * ratio),
        int(y1 * ratio),
        int(x2 * ratio),
        int(y2 * ratio),
    )


def confidence_to_label(score: float, threshold: float = 0.6) -> str:
    """
    OCR信頼度スコアを人間が読みやすいラベルに変換する。

    Args:
        score:     信頼度スコア (0.0 〜 1.0)。
        threshold: 低信頼度と判断するしきい値（デフォルト 0.6）。

    Returns:
        str: "高信頼度", "低信頼度", または "未認識" のいずれか。
    """
    if score < 0:
        return "未認識"
    if score < threshold:
        return "低信頼度"
    return "高信頼度"


def bool_to_display(value: bool) -> str:
    """
    bool 値を日本語表示文字列に変換する。

    Args:
        value: 変換する bool 値。

    Returns:
        str: True → "はい", False → "いいえ"。
    """
    return "はい" if value else "いいえ"


def truncate_text(text: str, max_length: int = 50, ellipsis: str = "…") -> str:
    """
    テキストを指定した最大文字数に切り詰める。

    UI の表示スペースが限られている場合に使用する。

    Args:
        text:       切り詰めるテキスト。
        max_length: 最大文字数（省略記号を含む）。
        ellipsis:   省略時に末尾に付加する文字列。

    Returns:
        str: 切り詰め後のテキスト。
    """
    if not isinstance(text, str):
        return ""
    if len(text) <= max_length:
        return text
    cut = max_length - len(ellipsis)
    return text[:max(cut, 0)] + ellipsis

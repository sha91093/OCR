"""
validators.py - 入力値バリデーション関数群

担当: 中村 美希 (Miki Nakamura)
作成日: 2026-03-13

UI層・コアロジック層からの入力値を検証する純粋関数を提供する。
バリデーション失敗時は例外を送出せず、検証結果と理由を返す設計とする。
これにより呼び出し元がエラーハンドリング方針を自由に決定できる。

使用例:
    from src.utils.validators import validate_form_name, validate_field_coords
    ok, reason = validate_form_name("住民票申請書")
    if not ok:
        show_error(reason)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Tuple

# 様式名の制約
FORM_NAME_MAX_LENGTH: int = 100
FORM_NAME_MIN_LENGTH: int = 1

# フィールド名の制約
FIELD_NAME_MAX_LENGTH: int = 100
FIELD_NAME_MIN_LENGTH: int = 1

# フィールド座標値の制約（ピクセル）
COORD_MIN: int = 0
COORD_MAX: int = 99999

# OCR認識テキストの最大長
OCR_TEXT_MAX_LENGTH: int = 10000


def validate_form_name(name: str) -> Tuple[bool, str]:
    """
    様式名を検証する。

    Args:
        name: 検証する様式名。

    Returns:
        Tuple[bool, str]: (検証結果, エラーメッセージ)。
                          成功時は (True, "")、失敗時は (False, エラー内容)。
    """
    if not isinstance(name, str):
        return False, "様式名は文字列で指定してください"
    stripped = name.strip()
    if len(stripped) < FORM_NAME_MIN_LENGTH:
        return False, "様式名を入力してください"
    if len(stripped) > FORM_NAME_MAX_LENGTH:
        return False, f"様式名は{FORM_NAME_MAX_LENGTH}文字以内で入力してください"
    return True, ""


def validate_field_name(name: str) -> Tuple[bool, str]:
    """
    フィールド名を検証する。

    Args:
        name: 検証するフィールド名。

    Returns:
        Tuple[bool, str]: (検証結果, エラーメッセージ)。
    """
    if not isinstance(name, str):
        return False, "フィールド名は文字列で指定してください"
    stripped = name.strip()
    if len(stripped) < FIELD_NAME_MIN_LENGTH:
        return False, "フィールド名を入力してください"
    if len(stripped) > FIELD_NAME_MAX_LENGTH:
        return False, f"フィールド名は{FIELD_NAME_MAX_LENGTH}文字以内で入力してください"
    return True, ""


def validate_field_coords(
    x1: int, y1: int, x2: int, y2: int
) -> Tuple[bool, str]:
    """
    フィールドの矩形座標を検証する。

    x1 < x2 かつ y1 < y2 を保証する。座標値は 0 以上の整数。

    Args:
        x1: 左上 X 座標。
        y1: 左上 Y 座標。
        x2: 右下 X 座標。
        y2: 右下 Y 座標。

    Returns:
        Tuple[bool, str]: (検証結果, エラーメッセージ)。
    """
    for name, val in [("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)]:
        if not isinstance(val, (int, float)):
            return False, f"{name} は数値で指定してください"
        if val < COORD_MIN:
            return False, f"{name} は 0 以上の値を指定してください"
        if val > COORD_MAX:
            return False, f"{name} は {COORD_MAX} 以下の値を指定してください"

    if x1 >= x2:
        return False, "x2 は x1 より大きい値を指定してください"
    if y1 >= y2:
        return False, "y2 は y1 より大きい値を指定してください"

    return True, ""


def validate_file_path(path: Path, must_exist: bool = True) -> Tuple[bool, str]:
    """
    ファイルパスを検証する。

    Args:
        path:       検証するファイルパス。
        must_exist: True の場合、ファイルが存在することも確認する。

    Returns:
        Tuple[bool, str]: (検証結果, エラーメッセージ)。
    """
    if not isinstance(path, Path):
        try:
            path = Path(path)
        except (TypeError, ValueError):
            return False, "有効なファイルパスを指定してください"

    if must_exist and not path.exists():
        return False, f"ファイルが見つかりません: {path}"
    if must_exist and not path.is_file():
        return False, f"指定されたパスはファイルではありません: {path}"
    return True, ""


def validate_output_directory(directory: Path) -> Tuple[bool, str]:
    """
    CSV出力先ディレクトリを検証する。

    Args:
        directory: 検証する出力先ディレクトリパス。

    Returns:
        Tuple[bool, str]: (検証結果, エラーメッセージ)。
    """
    if not isinstance(directory, Path):
        try:
            directory = Path(directory)
        except (TypeError, ValueError):
            return False, "有効なディレクトリパスを指定してください"

    if not directory.exists():
        return False, f"出力先ディレクトリが存在しません: {directory}"
    if not directory.is_dir():
        return False, f"指定されたパスはディレクトリではありません: {directory}"

    # 書き込み権限の確認
    import os
    if not os.access(directory, os.W_OK):
        return False, f"出力先ディレクトリへの書き込み権限がありません: {directory}"

    return True, ""


def validate_ocr_text(text: str) -> Tuple[bool, str]:
    """
    OCR認識テキストの基本バリデーションを行う。

    Args:
        text: 検証するOCR認識テキスト。

    Returns:
        Tuple[bool, str]: (検証結果, エラーメッセージ)。
    """
    if not isinstance(text, str):
        return False, "テキストは文字列で指定してください"
    if len(text) > OCR_TEXT_MAX_LENGTH:
        return False, f"テキストが長すぎます（最大 {OCR_TEXT_MAX_LENGTH} 文字）"
    return True, ""


def validate_confidence_score(score: float) -> Tuple[bool, str]:
    """
    OCR信頼度スコアを検証する（0.0 〜 1.0 の範囲）。

    Args:
        score: 検証する信頼度スコア。

    Returns:
        Tuple[bool, str]: (検証結果, エラーメッセージ)。
    """
    if not isinstance(score, (int, float)):
        return False, "信頼度スコアは数値で指定してください"
    if not (0.0 <= float(score) <= 1.0):
        return False, "信頼度スコアは 0.0 〜 1.0 の範囲で指定してください"
    return True, ""


def validate_csv_encoding(encoding: str) -> Tuple[bool, str]:
    """
    CSV出力エンコーディング名を検証する。

    Args:
        encoding: 検証するエンコーディング名（例: "utf-8-sig", "cp932"）。

    Returns:
        Tuple[bool, str]: (検証結果, エラーメッセージ)。
    """
    if not isinstance(encoding, str) or not encoding.strip():
        return False, "エンコーディングを指定してください"
    try:
        import codecs
        codecs.lookup(encoding)
    except LookupError:
        return False, f"未対応のエンコーディングです: {encoding}"
    return True, ""

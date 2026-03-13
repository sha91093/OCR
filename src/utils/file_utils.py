"""
file_utils.py - ファイル操作ユーティリティモジュール

担当: 中村 美希 (Miki Nakamura)
作成日: 2026-03-13

ファイルパス操作・拡張子チェック・一時ファイル管理など
ファイルシステム関連の汎用関数を提供する。

ビジネスロジックへの依存を持たず、単独でテスト可能な純粋関数で構成する。

使用例:
    from src.utils.file_utils import is_supported_file, get_unique_output_path
    if is_supported_file(path):
        output = get_unique_output_path(output_dir, "result", ".csv")
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List, Optional


# サポートする画像・文書ファイル拡張子（小文字）
SUPPORTED_IMAGE_EXTENSIONS: List[str] = [
    ".tiff", ".tif",
    ".png",
    ".jpeg", ".jpg",
    ".bmp",
]

SUPPORTED_DOC_EXTENSIONS: List[str] = [".pdf"]

ALL_SUPPORTED_EXTENSIONS: List[str] = (
    SUPPORTED_IMAGE_EXTENSIONS + SUPPORTED_DOC_EXTENSIONS
)


def is_supported_file(path: Path) -> bool:
    """
    ファイルがサポートされている形式かどうかを判定する。

    Args:
        path: 確認するファイルパス。

    Returns:
        bool: サポートされている形式であれば True。
    """
    return path.suffix.lower() in ALL_SUPPORTED_EXTENSIONS


def is_image_file(path: Path) -> bool:
    """
    ファイルが画像ファイルかどうかを判定する（PDFを除く）。

    Args:
        path: 確認するファイルパス。

    Returns:
        bool: 画像ファイルであれば True。
    """
    return path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


def is_pdf_file(path: Path) -> bool:
    """
    ファイルが PDF かどうかを判定する。

    Args:
        path: 確認するファイルパス。

    Returns:
        bool: PDF ファイルであれば True。
    """
    return path.suffix.lower() == ".pdf"


def get_unique_output_path(
    output_dir: Path,
    stem: str,
    suffix: str,
) -> Path:
    """
    出力先ディレクトリに同名ファイルが存在する場合に連番を付与した
    重複しないファイルパスを返す。

    例: result.csv が存在する場合 → result_1.csv, result_2.csv, ...

    Args:
        output_dir: 出力先ディレクトリ。
        stem:       ファイル名（拡張子なし）。
        suffix:     拡張子（例: ".csv"）。

    Returns:
        Path: 重複しないファイルパス。
    """
    candidate = output_dir / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate

    counter = 1
    while True:
        candidate = output_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def collect_supported_files(
    directory: Path,
    recursive: bool = False,
) -> List[Path]:
    """
    ディレクトリ内のサポートされているファイルを収集する。

    Args:
        directory: 検索対象ディレクトリ。
        recursive: True の場合はサブディレクトリも再帰的に検索する。

    Returns:
        List[Path]: サポートされているファイルのパスリスト（昇順ソート済み）。

    Raises:
        NotADirectoryError: 指定パスがディレクトリでない場合。
    """
    if not directory.is_dir():
        raise NotADirectoryError(f"ディレクトリが見つかりません: {directory}")

    pattern = "**/*" if recursive else "*"
    files = [
        p for p in directory.glob(pattern)
        if p.is_file() and is_supported_file(p)
    ]
    return sorted(files)


def ensure_directory(path: Path) -> Path:
    """
    ディレクトリが存在することを保証する。存在しない場合は作成する。

    Args:
        path: 作成・確認するディレクトリパス。

    Returns:
        Path: 確認・作成されたディレクトリパス（引数と同一）。

    Raises:
        OSError: ディレクトリの作成に失敗した場合。
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_file_stem(filename: str) -> str:
    """
    ファイル名として安全な文字列に変換する（拡張子を除く部分）。

    ファイルシステムで問題になりうる文字を アンダースコアに置換する。
    Windows / Linux / macOS で共通して安全な文字のみを許容する。

    Args:
        filename: 変換するファイル名（拡張子含む可）。

    Returns:
        str: 安全化されたファイル名ステム。
    """
    stem = Path(filename).stem
    # ファイルシステムで問題になりうる文字を置換
    unsafe_chars = r'/\:*?"<>|'
    result = stem
    for ch in unsafe_chars:
        result = result.replace(ch, "_")
    # 先頭・末尾のスペース・ドットを除去
    result = result.strip(". ")
    return result or "untitled"


@contextmanager
def temporary_directory() -> Generator[Path, None, None]:
    """
    処理完了後に自動削除される一時ディレクトリを作成するコンテキストマネージャ。

    OCR処理中の中間ファイル（PDF→画像変換後の一時画像など）の
    格納場所として使用する。

    Yields:
        Path: 一時ディレクトリのパス。

    使用例:
        with temporary_directory() as tmp_dir:
            # tmp_dir 内にファイルを作成して処理
            ...
        # ブロック終了後に tmp_dir は自動削除される
    """
    tmp_path = Path(tempfile.mkdtemp(prefix="ocr_shinseisho_"))
    try:
        yield tmp_path
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def get_file_size_str(path: Path) -> str:
    """
    ファイルサイズを人間が読みやすい文字列で返す。

    Args:
        path: サイズを取得するファイルパス。

    Returns:
        str: "1.2 MB" などの形式の文字列。ファイルが存在しない場合は "不明"。
    """
    try:
        size = path.stat().st_size
    except OSError:
        return "不明"

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f} TB"

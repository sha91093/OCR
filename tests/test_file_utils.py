"""
test_file_utils.py - src.utils.file_utils のユニットテスト

担当: 中村 美希 (Miki Nakamura)
作成日: 2026-03-13

テスト方針:
  - tmp_path フィクスチャで実ファイルシステムを使用し、実際のファイル操作を検証する。
  - temporary_directory() コンテキストマネージャは正常系・例外発生時の両方でクリーンアップを確認する。
  - get_unique_output_path() は連続した重複名でも正しく連番付与されることを確認する。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path

from src.utils.file_utils import (
    is_supported_file,
    is_image_file,
    is_pdf_file,
    get_unique_output_path,
    collect_supported_files,
    ensure_directory,
    safe_file_stem,
    temporary_directory,
    get_file_size_str,
    ALL_SUPPORTED_EXTENSIONS,
)


# ==============================================================================
# is_supported_file / is_image_file / is_pdf_file
# ==============================================================================

class TestFileTypeChecks:
    @pytest.mark.parametrize("ext", [
        ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff",
        ".PDF", ".PNG", ".JPG",
    ])
    def test_supported_extensions(self, ext):
        assert is_supported_file(Path(f"test{ext}")) is True

    @pytest.mark.parametrize("ext", [".txt", ".docx", ".xlsx", ".csv", ".mp4", ""])
    def test_unsupported_extensions(self, ext):
        assert is_supported_file(Path(f"test{ext}")) is False

    @pytest.mark.parametrize("ext", [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"])
    def test_image_file(self, ext):
        assert is_image_file(Path(f"img{ext}")) is True

    def test_pdf_not_image(self):
        assert is_image_file(Path("doc.pdf")) is False

    def test_is_pdf(self):
        assert is_pdf_file(Path("doc.pdf")) is True
        assert is_pdf_file(Path("doc.PDF")) is True

    def test_png_not_pdf(self):
        assert is_pdf_file(Path("img.png")) is False


# ==============================================================================
# get_unique_output_path
# ==============================================================================

class TestGetUniqueOutputPath:
    def test_no_conflict(self, tmp_path):
        p = get_unique_output_path(tmp_path, "result", ".csv")
        assert p == tmp_path / "result.csv"
        assert not p.exists()

    def test_one_conflict(self, tmp_path):
        (tmp_path / "result.csv").write_text("x")
        p = get_unique_output_path(tmp_path, "result", ".csv")
        assert p == tmp_path / "result_1.csv"

    def test_multiple_conflicts(self, tmp_path):
        (tmp_path / "result.csv").write_text("x")
        (tmp_path / "result_1.csv").write_text("x")
        (tmp_path / "result_2.csv").write_text("x")
        p = get_unique_output_path(tmp_path, "result", ".csv")
        assert p == tmp_path / "result_3.csv"

    def test_returns_path_object(self, tmp_path):
        p = get_unique_output_path(tmp_path, "out", ".csv")
        assert isinstance(p, Path)


# ==============================================================================
# collect_supported_files
# ==============================================================================

class TestCollectSupportedFiles:
    def test_collects_supported(self, tmp_path):
        (tmp_path / "a.pdf").write_bytes(b"")
        (tmp_path / "b.png").write_bytes(b"")
        (tmp_path / "c.txt").write_bytes(b"")
        files = collect_supported_files(tmp_path)
        names = {f.name for f in files}
        assert "a.pdf" in names
        assert "b.png" in names
        assert "c.txt" not in names

    def test_sorted_result(self, tmp_path):
        for name in ["c.pdf", "a.pdf", "b.png"]:
            (tmp_path / name).write_bytes(b"")
        files = collect_supported_files(tmp_path)
        names = [f.name for f in files]
        assert names == sorted(names)

    def test_recursive(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.pdf").write_bytes(b"")
        (tmp_path / "top.png").write_bytes(b"")

        non_recursive = collect_supported_files(tmp_path, recursive=False)
        recursive = collect_supported_files(tmp_path, recursive=True)

        assert len(non_recursive) == 1
        assert len(recursive) == 2

    def test_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(NotADirectoryError):
            collect_supported_files(f)

    def test_empty_directory(self, tmp_path):
        files = collect_supported_files(tmp_path)
        assert files == []


# ==============================================================================
# ensure_directory
# ==============================================================================

class TestEnsureDirectory:
    def test_creates_missing_dir(self, tmp_path):
        new_dir = tmp_path / "new" / "nested"
        result = ensure_directory(new_dir)
        assert new_dir.exists()
        assert result == new_dir

    def test_existing_dir_no_error(self, tmp_path):
        result = ensure_directory(tmp_path)
        assert result == tmp_path


# ==============================================================================
# safe_file_stem
# ==============================================================================

class TestSafeFileStem:
    def test_normal_name(self):
        assert safe_file_stem("住民票申請書.pdf") == "住民票申請書"

    def test_strips_extension(self):
        assert safe_file_stem("report.csv") == "report"

    def test_removes_unsafe_chars(self):
        result = safe_file_stem('file:with*bad?chars<>.pdf')
        for ch in r':*?<>':
            assert ch not in result

    def test_dotfile_stem(self):
        # ".pdf" は Unix の隠しファイル扱い: Path(".pdf").stem == ".pdf" → strip → "pdf"
        assert safe_file_stem(".pdf") == "pdf"

    def test_all_unsafe_chars_becomes_untitled(self):
        # 危険文字のみで構成された名前は "untitled" になる
        assert safe_file_stem("...") == "untitled"

    def test_no_extension(self):
        assert safe_file_stem("myfile") == "myfile"


# ==============================================================================
# temporary_directory
# ==============================================================================

class TestTemporaryDirectory:
    def test_creates_directory(self):
        with temporary_directory() as tmp:
            assert tmp.exists()
            assert tmp.is_dir()

    def test_cleaned_up_after_exit(self):
        with temporary_directory() as tmp:
            path = tmp
        assert not path.exists()

    def test_cleaned_up_on_exception(self):
        path = None
        try:
            with temporary_directory() as tmp:
                path = tmp
                raise RuntimeError("意図的エラー")
        except RuntimeError:
            pass
        assert path is not None
        assert not path.exists()

    def test_files_inside_cleaned(self):
        with temporary_directory() as tmp:
            (tmp / "work.png").write_bytes(b"\x89PNG")
            path = tmp
        assert not path.exists()


# ==============================================================================
# get_file_size_str
# ==============================================================================

class TestGetFileSizeStr:
    def test_bytes(self, tmp_path):
        f = tmp_path / "tiny.txt"
        f.write_bytes(b"hi")
        assert "B" in get_file_size_str(f)

    def test_kilobytes(self, tmp_path):
        f = tmp_path / "kb.bin"
        f.write_bytes(b"x" * 2048)
        result = get_file_size_str(f)
        assert "KB" in result or "MB" in result

    def test_nonexistent_file(self, tmp_path):
        result = get_file_size_str(tmp_path / "ghost.pdf")
        assert result == "不明"

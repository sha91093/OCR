"""
test_csv_exporter.py - CSVExporter のユニットテスト

担当: 中村 美希 (Miki Nakamura) - QAエンジニア
作成日: 2026-03-13

テスト方針:
  - 実際にファイルを書き出して内容を検証することで、エンコーディングや改行コードを確認する。
  - tmp_path フィクスチャで一時ファイルを使用し、テスト後は自動クリーンアップ。
  - 日本語文字列を含むテストデータを用いて、文字化けの有無を検証する。
  - CSV ファイルの内容検証には csv.reader を使用し、フォーマットに依存した文字列比較を避ける。
  - バッチ出力・プレビュー生成・エンコーディング切り替えを重点的にテストする。

カバレッジ対象:
  - CSVExporter.export_results()
  - CSVExporter.export_batch()
  - CSVExporter.generate_preview()
  - CSVExporter._collect_field_names()
  - CSVExporter._build_row()
  - エンコーディング: utf-8-sig (BOM付きUTF-8), cp932 (Shift-JIS)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import csv
import io
import pytest
from pathlib import Path
from typing import Any

from src.core.csv_exporter import CSVExporter


# ==============================================================================
# テストデータ定義
# ==============================================================================

def make_ocr_result(
    source_file: str,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    OCR 結果データ構造を生成するヘルパー関数。

    Args:
        source_file: 処理元ファイル名
        fields:      フィールド認識結果のリスト

    Returns:
        dict: OCR 結果データ
    """
    return {
        "source_file": source_file,
        "fields": fields,
    }


def make_field(field_name: str, recognized_text: str, confidence: float = 0.9) -> dict:
    """
    フィールド認識結果データを生成するヘルパー関数。
    """
    return {
        "field_name": field_name,
        "recognized_text": recognized_text,
        "confidence": confidence,
    }


# 標準的なテストデータセット
SAMPLE_RESULTS = [
    make_ocr_result(
        source_file="申請書001.pdf",
        fields=[
            make_field("applicant_name", "山田 太郎", 0.95),
            make_field("address", "東京都新宿区1-2-3", 0.88),
            make_field("phone", "03-1234-5678", 0.92),
        ],
    ),
    make_ocr_result(
        source_file="申請書002.pdf",
        fields=[
            make_field("applicant_name", "佐藤 花子", 0.91),
            make_field("address", "大阪府大阪市中央区4-5-6", 0.85),
            make_field("phone", "06-9876-5432", 0.89),
        ],
    ),
]


# ==============================================================================
# フィクスチャ定義
# ==============================================================================

@pytest.fixture
def exporter() -> CSVExporter:
    """デフォルト設定 (UTF-8 BOM付き) の CSVExporter"""
    return CSVExporter()


@pytest.fixture
def utf8_exporter() -> CSVExporter:
    """UTF-8 BOM付きエンコーディングの CSVExporter"""
    return CSVExporter(encoding="utf-8-sig")


@pytest.fixture
def sjis_exporter() -> CSVExporter:
    """Shift-JIS エンコーディングの CSVExporter"""
    return CSVExporter(encoding="cp932")


# ==============================================================================
# テスト: export_results()
# ==============================================================================

class TestExportResults:
    """export_results() のテスト群"""

    def test_export_results_creates_file(
        self, exporter: CSVExporter, tmp_path: Path
    ):
        """
        export_results 後にファイルが作成されること。
        """
        output = tmp_path / "output.csv"
        exporter.export_results(str(output), SAMPLE_RESULTS)
        assert output.exists(), "CSV ファイルが作成されること"

    def test_export_results_returns_path(
        self, exporter: CSVExporter, tmp_path: Path
    ):
        """
        export_results は出力先の Path オブジェクトを返すこと。
        """
        output = tmp_path / "output.csv"
        result_path = exporter.export_results(str(output), SAMPLE_RESULTS)
        assert isinstance(result_path, Path)
        assert result_path == output

    def test_export_results_correct_row_count(
        self, exporter: CSVExporter, tmp_path: Path
    ):
        """
        ヘッダー行 + データ行数が正しいこと。
        """
        output = tmp_path / "rows_test.csv"
        exporter.export_results(str(output), SAMPLE_RESULTS)

        with open(output, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # ヘッダー1行 + データ2行 = 3行
        assert len(rows) == 3, f"3行が出力されること (実際: {len(rows)}行)"

    def test_export_results_header_contains_source_file(
        self, exporter: CSVExporter, tmp_path: Path
    ):
        """
        ヘッダー行の先頭列が 'source_file' であること。
        """
        output = tmp_path / "header_test.csv"
        exporter.export_results(str(output), SAMPLE_RESULTS)

        with open(output, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)

        assert header[0] == "source_file"

    def test_export_results_header_contains_field_names(
        self, exporter: CSVExporter, tmp_path: Path
    ):
        """
        ヘッダー行にフィールド名が含まれること。
        """
        output = tmp_path / "fieldname_test.csv"
        exporter.export_results(str(output), SAMPLE_RESULTS)

        with open(output, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)

        assert "applicant_name" in header
        assert "address" in header
        assert "phone" in header

    def test_export_results_data_rows_contain_correct_values(
        self, exporter: CSVExporter, tmp_path: Path
    ):
        """
        データ行に正しい認識テキストが含まれること。
        """
        output = tmp_path / "values_test.csv"
        exporter.export_results(str(output), SAMPLE_RESULTS)

        with open(output, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)

        name_idx = header.index("applicant_name")

        assert rows[0][0] == "申請書001.pdf"
        assert rows[0][name_idx] == "山田 太郎"
        assert rows[1][0] == "申請書002.pdf"
        assert rows[1][name_idx] == "佐藤 花子"

    def test_export_results_no_header(
        self, exporter: CSVExporter, tmp_path: Path
    ):
        """
        include_header=False の場合はヘッダー行が出力されないこと。
        """
        output = tmp_path / "no_header.csv"
        exporter.export_results(str(output), SAMPLE_RESULTS, include_header=False)

        with open(output, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # データ行のみ (ヘッダーなし): 2行
        assert len(rows) == 2

    def test_export_results_empty_results(
        self, exporter: CSVExporter, tmp_path: Path
    ):
        """
        結果が空の場合でもヘッダー行だけ出力されること。
        """
        output = tmp_path / "empty.csv"
        exporter.export_results(str(output), [])

        with open(output, "r", encoding="utf-8-sig") as f:
            content = f.read()

        # ヘッダー行 (source_file のみ) が出力されること
        assert "source_file" in content

    def test_export_results_creates_parent_directory(
        self, exporter: CSVExporter, tmp_path: Path
    ):
        """
        出力先の親ディレクトリが存在しない場合、自動作成されること。
        """
        output = tmp_path / "subdir" / "deep" / "output.csv"
        exporter.export_results(str(output), SAMPLE_RESULTS)
        assert output.exists()


# ==============================================================================
# テスト: export_batch()
# ==============================================================================

class TestExportBatch:
    """export_batch() のテスト群"""

    @pytest.fixture
    def batch_results(self) -> list[dict[str, Any]]:
        """バッチ処理用のテストデータ"""
        return [
            {
                "result_id": 101,
                "source_file": "batch001.pdf",
                "processed_at": "2026-03-13T10:00:00",
                "status": "success",
                "fields": [
                    make_field("name", "田中 次郎", 0.93),
                    make_field("date", "2026年3月1日", 0.87),
                ],
            },
            {
                "result_id": 102,
                "source_file": "batch002.pdf",
                "processed_at": "2026-03-13T10:01:00",
                "status": "partial",
                "fields": [
                    make_field("name", "鈴木 三郎", 0.91),
                    make_field("date", "", 0.0),  # 認識失敗
                ],
            },
        ]

    def test_export_batch_creates_file(
        self,
        exporter: CSVExporter,
        tmp_path: Path,
        batch_results: list,
    ):
        """
        export_batch 後にファイルが作成されること。
        """
        output = tmp_path / "batch.csv"
        exporter.export_batch(str(output), batch_results)
        assert output.exists()

    def test_export_batch_with_metadata_columns(
        self,
        exporter: CSVExporter,
        tmp_path: Path,
        batch_results: list,
    ):
        """
        include_metadata=True の場合、result_id・processed_at・status 列が含まれること。
        """
        output = tmp_path / "batch_meta.csv"
        exporter.export_batch(str(output), batch_results, include_metadata=True)

        with open(output, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)

        assert "result_id" in header
        assert "processed_at" in header
        assert "status" in header

    def test_export_batch_without_metadata_columns(
        self,
        exporter: CSVExporter,
        tmp_path: Path,
        batch_results: list,
    ):
        """
        include_metadata=False の場合、メタデータ列が含まれないこと。
        """
        output = tmp_path / "batch_no_meta.csv"
        exporter.export_batch(str(output), batch_results, include_metadata=False)

        with open(output, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)

        assert "result_id" not in header
        assert "processed_at" not in header
        assert "status" not in header

    def test_export_batch_result_id_preserved(
        self,
        exporter: CSVExporter,
        tmp_path: Path,
        batch_results: list,
    ):
        """
        result_id が正しく出力されること。
        """
        output = tmp_path / "batch_id.csv"
        exporter.export_batch(str(output), batch_results, include_metadata=True)

        with open(output, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)

        id_idx = header.index("result_id")
        assert rows[0][id_idx] == "101"
        assert rows[1][id_idx] == "102"

    def test_export_batch_status_values(
        self,
        exporter: CSVExporter,
        tmp_path: Path,
        batch_results: list,
    ):
        """
        status 値 (success / partial) が正しく出力されること。
        """
        output = tmp_path / "batch_status.csv"
        exporter.export_batch(str(output), batch_results, include_metadata=True)

        with open(output, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)

        status_idx = header.index("status")
        assert rows[0][status_idx] == "success"
        assert rows[1][status_idx] == "partial"


# ==============================================================================
# テスト: エンコーディング (UTF-8 BOM付き)
# ==============================================================================

class TestEncodingUtf8:
    """UTF-8 BOM付きエンコーディングのテスト群"""

    def test_utf8_bom_present(
        self, utf8_exporter: CSVExporter, tmp_path: Path
    ):
        """
        UTF-8 BOM付き (utf-8-sig) でファイルが書き出されること。

        Excel での文字化け防止のため BOM が先頭に必要。
        BOM = b'\\xef\\xbb\\xbf' (UTF-8 BOM)
        """
        output = tmp_path / "utf8_bom.csv"
        utf8_exporter.export_results(str(output), SAMPLE_RESULTS)

        with open(output, "rb") as f:
            raw = f.read(3)

        assert raw == b"\xef\xbb\xbf", "ファイル先頭に UTF-8 BOM が存在すること"

    def test_utf8_japanese_readable(
        self, utf8_exporter: CSVExporter, tmp_path: Path
    ):
        """
        出力ファイルが UTF-8 で読み込んだ際に日本語が正しく表示されること。
        """
        output = tmp_path / "utf8_ja.csv"
        utf8_exporter.export_results(str(output), SAMPLE_RESULTS)

        with open(output, "r", encoding="utf-8-sig") as f:
            content = f.read()

        # 日本語文字列が含まれていること
        assert "山田 太郎" in content
        assert "東京都新宿区1-2-3" in content
        assert "申請書001.pdf" in content

    def test_utf8_default_encoding(self, tmp_path: Path):
        """
        CSVExporter のデフォルトエンコーディングが 'utf-8-sig' であること。

        設定を確認することで、新規インスタンスが常に Excel 互換の設定で動作することを保証。
        """
        exporter = CSVExporter()
        assert exporter.encoding == "utf-8-sig"


# ==============================================================================
# テスト: エンコーディング (Shift-JIS)
# ==============================================================================

class TestEncodingSjis:
    """Shift-JIS エンコーディングのテスト群"""

    def test_sjis_file_readable_as_cp932(
        self, sjis_exporter: CSVExporter, tmp_path: Path
    ):
        """
        Shift-JIS (cp932) で書き出したファイルが cp932 で読み込めること。

        旧来の業務システムとの連携ファイルとして要求されることがある。
        """
        output = tmp_path / "sjis.csv"
        sjis_exporter.export_results(str(output), SAMPLE_RESULTS)

        # cp932 で読み込めることを確認
        with open(output, "r", encoding="cp932") as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)

        assert len(rows) == 2, "2件のデータ行が読み込めること"
        assert "source_file" in header

    def test_sjis_japanese_content_preserved(
        self, sjis_exporter: CSVExporter, tmp_path: Path
    ):
        """
        Shift-JIS 出力でも日本語テキストが正しく保存されること。
        """
        output = tmp_path / "sjis_ja.csv"
        sjis_exporter.export_results(str(output), SAMPLE_RESULTS)

        with open(output, "r", encoding="cp932") as f:
            content = f.read()

        assert "山田 太郎" in content
        assert "佐藤 花子" in content

    def test_sjis_no_bom(
        self, sjis_exporter: CSVExporter, tmp_path: Path
    ):
        """
        Shift-JIS ファイルには UTF-8 BOM が含まれないこと。

        cp932 ファイルに UTF-8 BOM があると読み込みエラーになる可能性がある。
        """
        output = tmp_path / "sjis_no_bom.csv"
        sjis_exporter.export_results(str(output), SAMPLE_RESULTS)

        with open(output, "rb") as f:
            raw = f.read(3)

        # UTF-8 BOM ではないこと
        assert raw != b"\xef\xbb\xbf", "Shift-JIS ファイルに UTF-8 BOM がないこと"

    def test_sjis_encoding_attribute(self, sjis_exporter: CSVExporter):
        """
        CSVExporter の encoding 属性が 'cp932' に設定されていること。
        """
        assert sjis_exporter.encoding == "cp932"


# ==============================================================================
# テスト: generate_preview()
# ==============================================================================

class TestGeneratePreview:
    """generate_preview() のテスト群"""

    def test_generate_preview_returns_string(self, exporter: CSVExporter):
        """
        generate_preview は文字列を返すこと。
        """
        preview = exporter.generate_preview(SAMPLE_RESULTS)
        assert isinstance(preview, str)

    def test_generate_preview_contains_header(self, exporter: CSVExporter):
        """
        プレビュー文字列にヘッダー行が含まれること。
        """
        preview = exporter.generate_preview(SAMPLE_RESULTS)
        assert "source_file" in preview

    def test_generate_preview_contains_data(self, exporter: CSVExporter):
        """
        プレビュー文字列にデータが含まれること。
        """
        preview = exporter.generate_preview(SAMPLE_RESULTS)
        assert "申請書001.pdf" in preview
        assert "山田 太郎" in preview

    def test_generate_preview_max_rows_limit(self, exporter: CSVExporter):
        """
        max_rows で指定した件数以上のデータが含まれないこと。

        大量データのプレビュー時に UI がフリーズしないための機能。
        """
        # 5件のデータを用意
        large_results = [
            make_ocr_result(
                source_file=f"file{i:03d}.pdf",
                fields=[make_field("name", f"名前{i}")]
            )
            for i in range(5)
        ]

        # max_rows=2 で制限する
        preview = exporter.generate_preview(large_results, max_rows=2)

        # "file000.pdf" と "file001.pdf" は含まれるが "file004.pdf" は含まれないこと
        assert "file000.pdf" in preview
        assert "file001.pdf" in preview
        assert "file004.pdf" not in preview

    def test_generate_preview_truncation_notice(self, exporter: CSVExporter):
        """
        max_rows で切り捨てられた場合、省略メッセージが含まれること。

        ユーザーがプレビューで全件ではないことを認識できるように。
        """
        large_results = [
            make_ocr_result(f"file{i}.pdf", []) for i in range(5)
        ]
        preview = exporter.generate_preview(large_results, max_rows=2)
        # 省略通知が含まれること
        assert "残り" in preview or "省略" in preview

    def test_generate_preview_empty_results(self, exporter: CSVExporter):
        """
        空の結果リストでも正常にプレビューが生成されること。
        """
        preview = exporter.generate_preview([])
        assert isinstance(preview, str)
        # ヘッダー行 (source_file のみ) が含まれること
        assert "source_file" in preview

    def test_generate_preview_no_file_written(
        self, exporter: CSVExporter, tmp_path: Path
    ):
        """
        generate_preview はファイルを作成しないこと。

        プレビュー機能はメモリ上のみで動作すべき設計を確認する。
        """
        initial_files = set(tmp_path.iterdir())
        exporter.generate_preview(SAMPLE_RESULTS)
        final_files = set(tmp_path.iterdir())

        # tmp_path に新しいファイルが作成されていないこと
        assert initial_files == final_files, "generate_preview はファイルを生成しないこと"


# ==============================================================================
# テスト: 内部ヘルパーメソッド
# ==============================================================================

class TestInternalHelpers:
    """内部ヘルパーメソッドの直接テスト"""

    def test_collect_field_names_no_duplicates(self, exporter: CSVExporter):
        """
        同じフィールド名が複数の結果に含まれても、重複なしでリストが返ること。

        CSV のヘッダーに同じ列名が重複しないための仕様。
        """
        results = [
            make_ocr_result("a.pdf", [make_field("name", "A"), make_field("addr", "X")]),
            make_ocr_result("b.pdf", [make_field("name", "B"), make_field("addr", "Y")]),
        ]
        field_names = exporter._collect_field_names(results)

        assert len(field_names) == len(set(field_names)), "重複がないこと"
        assert "name" in field_names
        assert "addr" in field_names

    def test_collect_field_names_preserves_order(self, exporter: CSVExporter):
        """
        フィールド名の初出順が保持されること。

        CSV の列順序が毎回変わると使い勝手が悪いため、出現順を維持する。
        """
        results = [
            make_ocr_result("a.pdf", [
                make_field("name", "A"),
                make_field("date", "X"),
                make_field("address", "Y"),
            ]),
        ]
        field_names = exporter._collect_field_names(results)
        assert field_names == ["name", "date", "address"]

    def test_build_row_fills_missing_fields_with_empty(
        self, exporter: CSVExporter
    ):
        """
        フィールドが存在しない結果の場合、空文字で埋められること。

        フィールドが部分的にしか認識できなかった場合でも
        CSV の列数が揃うことが重要。
        """
        result = make_ocr_result(
            "test.pdf",
            [make_field("name", "太郎")],  # address フィールドなし
        )
        header_fields = ["name", "address", "phone"]  # 3列分のヘッダー
        row = exporter._build_row(result, header_fields)

        # source_file + 3フィールド = 4列
        assert len(row) == 4
        assert row[0] == "test.pdf"
        assert row[1] == "太郎"   # name
        assert row[2] == ""       # address (存在しないので空文字)
        assert row[3] == ""       # phone (存在しないので空文字)

    def test_line_terminator_setting(self, tmp_path: Path):
        """
        line_terminator 設定が CSV ファイルに反映されること。

        Windows 環境向けには CRLF (\\r\\n) を使用する。
        """
        exporter = CSVExporter(line_terminator="\r\n")
        output = tmp_path / "crlf.csv"
        exporter.export_results(
            str(output),
            [make_ocr_result("test.pdf", [make_field("n", "v")])],
        )

        with open(output, "rb") as f:
            content = f.read()

        assert b"\r\n" in content, "CRLF 改行コードが使用されること"

    def test_delimiter_setting(self, tmp_path: Path):
        """
        delimiter 設定が CSV ファイルに反映されること。
        """
        exporter = CSVExporter(delimiter="\t")  # タブ区切り
        output = tmp_path / "tsv.csv"
        exporter.export_results(
            str(output),
            [make_ocr_result("test.pdf", [
                make_field("col1", "val1"),
                make_field("col2", "val2"),
            ])],
        )

        with open(output, "r", encoding="utf-8-sig") as f:
            content = f.read()

        assert "\t" in content, "タブ文字が区切りとして使用されること"

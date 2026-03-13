"""
csv_exporter.py - CSV出力モジュール

担当: 佐藤 愛子 (Aiko Sato)
作成日: 2026-03-13

OCR結果をCSVファイルとして出力する機能を提供する。

設計方針:
  - 文字コードはデフォルトで UTF-8 BOM付き (utf-8-sig)。
    Excel で開いた際の文字化けを防ぐためこの設定を標準とする。
  - Shift-JIS (cp932) 出力もオプションとして提供する。
    旧来の業務システム連携に対応するため。
  - バッチ出力: 複数OCR結果を1つのCSVにまとめて出力する。
"""

import csv
import io
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CSVExporter:
    """
    OCR処理結果をCSV形式でエクスポートするクラス。

    単件出力とバッチ出力の両方に対応する。
    文字コードはインスタンス生成時に選択可能。

    Attributes:
        encoding (str):   出力文字コード (デフォルト: 'utf-8-sig')
        delimiter (str):  フィールド区切り文字 (デフォルト: ',')
        line_terminator (str): 行末文字 (デフォルト: '\\r\\n')
    """

    def __init__(
        self,
        encoding: str = "utf-8-sig",
        delimiter: str = ",",
        line_terminator: str = "\r\n",
    ) -> None:
        """
        CSVExporterを初期化する。

        Args:
            encoding:        出力文字コード。'utf-8-sig' または 'cp932' (Shift-JIS) など。
            delimiter:       フィールド区切り文字。
            line_terminator: 行末文字。Windows互換のCRLFがデフォルト。
        """
        self.encoding = encoding
        self.delimiter = delimiter
        self.line_terminator = line_terminator
        logger.debug(
            f"CSVExporter初期化: encoding={encoding}, "
            f"delimiter='{delimiter}', line_terminator={repr(line_terminator)}"
        )

    def export_results(
        self,
        output_path: str,
        results: list[dict[str, Any]],
        include_header: bool = True,
    ) -> Path:
        """
        OCR結果リストをCSVファイルに出力する。

        Args:
            output_path:    出力先ファイルパス (文字列)
            results:        OCR結果の辞書リスト。各要素のキー:
                            - source_file (str): 処理元ファイル名
                            - fields (list[dict]): 認識フィールドのリスト
                              各フィールド: {field_name, recognized_text, confidence}
            include_header: Trueの場合、1行目にヘッダー行を出力する。

        Returns:
            Path: 出力されたCSVファイルのパス

        Raises:
            OSError: ファイルへの書き込みに失敗した場合
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # ヘッダー列名を収集 (全結果のフィールド名を統合)
        header_fields = self._collect_field_names(results)

        with open(path, "w", encoding=self.encoding, newline="") as f:
            writer = csv.writer(
                f,
                delimiter=self.delimiter,
                lineterminator=self.line_terminator,
            )

            if include_header:
                # ヘッダー行: source_file + 各フィールド名
                header_row = ["source_file"] + header_fields
                writer.writerow(header_row)

            for result in results:
                row = self._build_row(result, header_fields)
                writer.writerow(row)

        logger.info(
            f"CSV出力完了: {path}, {len(results)}件, encoding={self.encoding}"
        )
        return path

    def export_batch(
        self,
        output_path: str,
        batch_results: list[dict[str, Any]],
        include_metadata: bool = True,
    ) -> Path:
        """
        バッチ処理のOCR結果をCSVファイルに一括出力する。

        Args:
            output_path:      出力先ファイルパス
            batch_results:    バッチ処理結果リスト。各要素:
                              - result_id (int): OCR結果ID
                              - source_file (str): 処理元ファイル名
                              - processed_at (str): 処理日時
                              - status (str): 処理状態
                              - fields (list[dict]): 認識フィールドリスト
            include_metadata: Trueの場合、result_id・processed_at・statusも列に含める。

        Returns:
            Path: 出力されたCSVファイルのパス
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        header_fields = self._collect_field_names(batch_results)

        with open(path, "w", encoding=self.encoding, newline="") as f:
            writer = csv.writer(
                f,
                delimiter=self.delimiter,
                lineterminator=self.line_terminator,
            )

            # ヘッダー行の構築
            if include_metadata:
                header = ["result_id", "source_file", "processed_at", "status"] + header_fields
            else:
                header = ["source_file"] + header_fields
            writer.writerow(header)

            for result in batch_results:
                if include_metadata:
                    meta = [
                        result.get("result_id", ""),
                        result.get("source_file", ""),
                        result.get("processed_at", ""),
                        result.get("status", ""),
                    ]
                else:
                    meta = [result.get("source_file", "")]

                field_values = self._build_row(result, header_fields)
                writer.writerow(meta + field_values)

        logger.info(
            f"バッチCSV出力完了: {path}, {len(batch_results)}件"
        )
        return path

    def generate_preview(
        self,
        results: list[dict[str, Any]],
        max_rows: int = 10,
    ) -> str:
        """
        CSVのプレビュー文字列を生成する（ファイルには書き出さない）。

        UIでのプレビュー表示に使用する。

        Args:
            results:  OCR結果リスト
            max_rows: プレビューに含める最大行数 (デフォルト: 10)

        Returns:
            str: CSV形式のプレビュー文字列 (UTF-8)
        """
        preview_results = results[:max_rows]
        header_fields = self._collect_field_names(preview_results)

        output = io.StringIO()
        writer = csv.writer(
            output,
            delimiter=self.delimiter,
            lineterminator=self.line_terminator,
        )

        # ヘッダー
        writer.writerow(["source_file"] + header_fields)

        for result in preview_results:
            row = self._build_row(result, header_fields)
            writer.writerow(row)

        if len(results) > max_rows:
            output.write(
                f"... (残り {len(results) - max_rows} 件は省略){self.line_terminator}"
            )

        return output.getvalue()

    # -------------------------------------------------------------------------
    # 内部ヘルパーメソッド
    # -------------------------------------------------------------------------

    def _collect_field_names(self, results: list[dict[str, Any]]) -> list[str]:
        """
        結果リストから全フィールド名を収集して重複なしのリストを返す。

        フィールド名の出現順を保持するため OrderedDict 的な処理を行う。

        Args:
            results: OCR結果リスト

        Returns:
            list[str]: フィールド名のリスト (出現順、重複なし)
        """
        seen: dict[str, None] = {}
        for result in results:
            for field in result.get("fields", []):
                fname = field.get("field_name", "")
                if fname and fname not in seen:
                    seen[fname] = None
        return list(seen.keys())

    def _build_row(
        self, result: dict[str, Any], header_fields: list[str]
    ) -> list[str]:
        """
        1件のOCR結果から CSV行データ (source_file + フィールド値) を構築する。

        Args:
            result:        OCR結果辞書 ('source_file', 'fields' を含む)
            header_fields: ヘッダーのフィールド名リスト

        Returns:
            list[str]: source_file + 各フィールドの認識テキストのリスト
        """
        # フィールド名 → 認識テキスト のマッピングを構築
        field_map: dict[str, str] = {}
        for field in result.get("fields", []):
            fname = field.get("field_name", "")
            text = field.get("recognized_text", "")
            field_map[fname] = text

        source_file = result.get("source_file", "")
        field_values = [field_map.get(fname, "") for fname in header_fields]
        return [source_file] + field_values

    # -------------------------------------------------------------------------
    # form_fields 対応オーバーロード (OCRProcessorからの呼び出し互換)
    # -------------------------------------------------------------------------

    def export_with_fields(
        self,
        results: list[dict[str, Any]],
        output_path: str,
        form_fields: list[dict[str, Any]],
    ) -> Path:
        """
        フィールド定義を使って列順を制御した CSV を出力する。

        form_fields の order_index 順でフィールド列を並べる。
        OCRProcessor から呼び出す場合はこちらを推奨。

        Args:
            results:     OCR結果リスト
            output_path: 出力先ファイルパス
            form_fields: フィールド定義リスト (order_index で列順を決定)

        Returns:
            Path: 出力した CSV ファイルのパス
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # フィールド定義を order_index, page_number 順にソート
        sorted_fields = sorted(
            form_fields,
            key=lambda f: (f.get("page_number", 1), f.get("order_index", 0)),
        )

        # ヘッダー行: source_file + フィールドラベル (なければfield_name)
        field_label_headers = [
            f.get("field_label", f.get("field_name", ""))
            for f in sorted_fields
        ]
        field_name_order = [f.get("field_name", "") for f in sorted_fields]

        with open(path, "w", encoding=self.encoding, newline="") as f:
            writer = csv.writer(
                f,
                delimiter=self.delimiter,
                lineterminator=self.line_terminator,
            )
            writer.writerow(["source_file"] + field_label_headers)

            for result in results:
                field_map: dict[str, str] = {
                    fld.get("field_name", ""): fld.get("recognized_text", "")
                    for fld in result.get("fields", [])
                }
                row = [result.get("source_file", "")] + [
                    field_map.get(n, "") for n in field_name_order
                ]
                writer.writerow(row)

        logger.info(f"CSV出力完了 (with fields): {path}, {len(results)}件")
        return path

    def generate_preview_rows(
        self,
        results: list[dict[str, Any]],
        form_fields: list[dict[str, Any]],
        max_rows: int = 10,
    ) -> list[list[str]]:
        """
        CSVプレビュー用の2次元リストを生成する。

        generate_preview() とは異なり、文字列ではなくリスト形式で返す。
        UIのテーブルウィジェットへの直接セットに便利。

        Args:
            results:     OCR結果リスト
            form_fields: フィールド定義リスト
            max_rows:    最大行数 (デフォルト: 10)

        Returns:
            list[list[str]]: [ヘッダー行, データ行1, ...] の2次元リスト
        """
        sorted_fields = sorted(
            form_fields,
            key=lambda f: (f.get("page_number", 1), f.get("order_index", 0)),
        )
        headers = ["source_file"] + [
            f.get("field_label", f.get("field_name", "")) for f in sorted_fields
        ]
        field_name_order = [f.get("field_name", "") for f in sorted_fields]

        data_rows: list[list[str]] = [headers]
        for result in results[:max_rows]:
            field_map = {
                fld.get("field_name", ""): fld.get("recognized_text", "")
                for fld in result.get("fields", [])
            }
            row = [result.get("source_file", "")] + [
                field_map.get(n, "") for n in field_name_order
            ]
            data_rows.append(row)

        return data_rows

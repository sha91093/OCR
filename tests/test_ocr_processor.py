"""
test_ocr_processor.py - OCRProcessor の結合テスト

担当: 中村 美希 (Miki Nakamura)
作成日: 2026-03-13

テスト方針:
  - conftest.py の `ocr_processor` (モック OCR エンジン) / `tiny_png` を使用する。
  - process_file() のフルフロー（ファイル読み込み→フィールド取得→OCR→DB保存）を検証する。
  - DPI スケーリング (_scale_fields_for_dpi) の結合動作を検証する。
  - バッチ処理 (process_batch) の正常系・部分失敗系を検証する。
  - OCR エンジンのモックを使うため ndlocr/Tesseract は不要。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ==============================================================================
# process_file — 正常系
# ==============================================================================

class TestProcessFileSuccess:
    def test_returns_success_true(self, ocr_processor, sample_form_with_fields, tiny_png):
        form_id = sample_form_with_fields["id"]
        result = ocr_processor.process_file(tiny_png, form_id)
        assert result["success"] is True

    def test_returns_result_id(self, ocr_processor, sample_form_with_fields, tiny_png):
        form_id = sample_form_with_fields["id"]
        result = ocr_processor.process_file(tiny_png, form_id)
        assert isinstance(result["result_id"], int)
        assert result["result_id"] > 0

    def test_returns_field_results(self, ocr_processor, sample_form_with_fields, tiny_png):
        form_id = sample_form_with_fields["id"]
        result = ocr_processor.process_file(tiny_png, form_id)
        assert len(result["results"]) >= 1
        for r in result["results"]:
            assert "field_name" in r
            assert "recognized_text" in r

    def test_recognized_text_stored_in_db(self, ocr_processor, db_manager,
                                          sample_form_with_fields, tiny_png):
        form_id = sample_form_with_fields["id"]
        result = ocr_processor.process_file(tiny_png, form_id)
        # result_id で ocr_result_fields を直接確認
        result_id = result["result_id"]
        with db_manager._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM ocr_result_fields WHERE result_id = ?", (result_id,)
            ).fetchall()
        assert len(rows) >= 1

    def test_callback_called_with_progress(self, ocr_processor, sample_form_with_fields, tiny_png):
        form_id = sample_form_with_fields["id"]
        calls = []
        ocr_processor.process_file(tiny_png, form_id,
                                   callback=lambda cur, tot, msg: calls.append((cur, tot)))
        assert len(calls) >= 1
        # 最終コールは total == total
        assert calls[-1][0] == calls[-1][1]

    def test_no_error_key_on_success(self, ocr_processor, sample_form_with_fields, tiny_png):
        form_id = sample_form_with_fields["id"]
        result = ocr_processor.process_file(tiny_png, form_id)
        assert result.get("error") is None


# ==============================================================================
# process_file — 異常系
# ==============================================================================

class TestProcessFileError:
    def test_nonexistent_file(self, ocr_processor, sample_form_with_fields):
        form_id = sample_form_with_fields["id"]
        result = ocr_processor.process_file("/tmp/no_such_file.png", form_id)
        assert result["success"] is False
        assert result["error"] is not None

    def test_invalid_form_id(self, ocr_processor, tiny_png):
        result = ocr_processor.process_file(tiny_png, form_id=99999)
        assert result["success"] is False
        assert "様式" in result["error"]

    def test_unsupported_extension(self, ocr_processor, sample_form_with_fields, tmp_path):
        form_id = sample_form_with_fields["id"]
        txt_file = tmp_path / "input.txt"
        txt_file.write_text("dummy")
        result = ocr_processor.process_file(txt_file, form_id)
        assert result["success"] is False

    def test_no_fields_defined(self, ocr_processor, form_manager, tiny_png):
        # フィールドなし様式
        empty_form_id = form_manager.create_form("空様式")
        result = ocr_processor.process_file(tiny_png, empty_form_id)
        # フィールドなしでも処理は成功する（結果は空）
        assert result["success"] is True
        assert result["results"] == []

    def test_callback_exception_does_not_crash(self, ocr_processor,
                                                sample_form_with_fields, tiny_png):
        form_id = sample_form_with_fields["id"]
        def bad_callback(cur, tot, msg):
            raise RuntimeError("callback error")

        result = ocr_processor.process_file(tiny_png, form_id, callback=bad_callback)
        assert result["success"] is True  # callback 失敗でも処理継続


# ==============================================================================
# DPI スケーリング結合テスト
# ==============================================================================

class TestDpiScalingIntegration:
    def test_same_dpi_no_change(self, ocr_processor):
        fields = [{"field_name": "a", "x1": 100, "y1": 200,
                   "x2": 400, "y2": 240, "template_dpi": 150}]
        ocr_processor.pdf_processor.dpi = 150
        scaled = ocr_processor._scale_fields_for_dpi(fields)
        assert scaled[0]["x1"] == 100
        assert scaled[0]["y1"] == 200

    def test_double_dpi_doubles_coords(self, ocr_processor):
        fields = [{"field_name": "a", "x1": 100, "y1": 200,
                   "x2": 400, "y2": 240, "template_dpi": 150}]
        ocr_processor.pdf_processor.dpi = 300
        scaled = ocr_processor._scale_fields_for_dpi(fields)
        assert scaled[0]["x1"] == 200
        assert scaled[0]["y1"] == 400
        assert scaled[0]["x2"] == 800
        assert scaled[0]["y2"] == 480

    def test_half_dpi_halves_coords(self, ocr_processor):
        fields = [{"field_name": "a", "x1": 200, "y1": 400,
                   "x2": 800, "y2": 480, "template_dpi": 300}]
        ocr_processor.pdf_processor.dpi = 150
        scaled = ocr_processor._scale_fields_for_dpi(fields)
        assert scaled[0]["x1"] == 100
        assert scaled[0]["y1"] == 200

    def test_missing_template_dpi_uses_processing_dpi(self, ocr_processor):
        # template_dpi がない場合は変換なしでそのまま返す
        fields = [{"field_name": "a", "x1": 100, "y1": 200, "x2": 400, "y2": 240}]
        ocr_processor.pdf_processor.dpi = 150
        scaled = ocr_processor._scale_fields_for_dpi(fields)
        assert scaled[0]["x1"] == 100

    def test_original_field_not_mutated(self, ocr_processor):
        fields = [{"field_name": "a", "x1": 100, "y1": 200,
                   "x2": 400, "y2": 240, "template_dpi": 150}]
        ocr_processor.pdf_processor.dpi = 300
        ocr_processor._scale_fields_for_dpi(fields)
        # 元のリストは変更されていないこと
        assert fields[0]["x1"] == 100

    def test_dpi_scale_applied_before_ocr(self, ocr_processor, db_manager,
                                           sample_form_id, sample_field_data, tiny_png):
        # template_dpi=150 のフィールドを DB に登録
        db_manager.save_form_field(sample_form_id, sample_field_data)
        # processing_dpi を 300 に変更
        ocr_processor.pdf_processor.dpi = 300
        # process_file 呼び出し時に recognize_regions が適切なスケール座標で呼ばれることを確認
        result = ocr_processor.process_file(tiny_png, sample_form_id)
        assert result["success"] is True
        call_args = ocr_processor.ocr_engine.recognize_regions.call_args
        scaled_fields = call_args[0][1]  # 第2引数 = fields
        assert scaled_fields[0]["x1"] == 200   # 100 × (300/150)


# ==============================================================================
# process_batch
# ==============================================================================

class TestProcessBatch:
    def test_batch_all_success(self, ocr_processor, sample_form_with_fields,
                               tmp_path, tiny_png):
        form_id = sample_form_with_fields["id"]
        # 3ファイルのコピー
        files = []
        for i in range(3):
            f = tmp_path / f"doc_{i}.png"
            f.write_bytes(tiny_png.read_bytes())
            files.append(f)

        results = ocr_processor.process_batch(files, form_id)
        assert results["total"]   == 3
        assert results["success"] == 3
        assert results["failed"]  == 0

    def test_batch_partial_failure(self, ocr_processor, sample_form_with_fields,
                                   tmp_path, tiny_png):
        form_id = sample_form_with_fields["id"]
        files = [
            tiny_png,
            tmp_path / "ghost.png",  # 存在しない
        ]
        results = ocr_processor.process_batch(files, form_id)
        assert results["total"]   == 2
        assert results["success"] == 1
        assert results["failed"]  == 1

    def test_batch_progress_callback(self, ocr_processor, sample_form_with_fields, tiny_png):
        form_id = sample_form_with_fields["id"]
        calls = []
        ocr_processor.process_batch(
            [tiny_png], form_id,
            callback=lambda done, total, msg: calls.append((done, total)),
        )
        assert len(calls) >= 1

    def test_batch_empty_list(self, ocr_processor, sample_form_with_fields):
        form_id = sample_form_with_fields["id"]
        results = ocr_processor.process_batch([], form_id)
        assert results["total"]   == 0
        assert results["success"] == 0


# ==============================================================================
# get_engine_info / get_form_list
# ==============================================================================

class TestHelpers:
    def test_get_engine_info_has_required_keys(self, ocr_processor):
        info = ocr_processor.get_engine_info()
        assert "engine_name" in info
        assert "is_available" in info

    def test_get_form_list_returns_list(self, ocr_processor, sample_form_with_fields):
        forms = ocr_processor.get_form_list()
        assert isinstance(forms, list)
        assert any(f["id"] == sample_form_with_fields["id"] for f in forms)

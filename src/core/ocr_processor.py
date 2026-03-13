"""
ocr_processor.py - OCR処理オーケストレーターモジュール

担当: 佐藤 愛子 (Aiko Sato)
作成日: 2026-03-13

FormManager / OCREngine / PDFProcessor / CSVExporter を統合し、
ファイル単体処理・バッチ処理・CSV出力のワークフローを一元管理する。

このクラスが「処理の司令塔」となり、
UI層はこのクラスだけを呼び出せばOCR処理のライフサイクルを完結できる。

処理フロー:
    1. PDF/画像ファイルを受け取る
    2. PDFProcessor で画像リストに変換
    3. OCREngine で各フィールドを認識
    4. DatabaseManager に結果を保存
    5. 必要に応じて CSVExporter で出力
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from .database import DatabaseManager
from .form_manager import FormManager
from .ocr_engine import OCREngine
from .pdf_processor import PDFProcessor
from .csv_exporter import CSVExporter

logger = logging.getLogger(__name__)

# 対応する画像ファイルの拡張子
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
# 対応する PDF の拡張子
_PDF_EXTENSIONS = {".pdf"}


class OCRProcessor:
    """
    OCR処理の全工程を調整するオーケストレータークラス。

    各コンポーネント (FormManager / OCREngine / PDFProcessor / CSVExporter) を
    初期化・保持し、ファイル処理・バッチ処理・CSV出力の統合APIを提供する。

    Attributes:
        db           (DatabaseManager): データベース管理
        form_manager (FormManager):     様式管理
        ocr_engine   (OCREngine):       OCR認識エンジン
        pdf_processor(PDFProcessor):    PDF/画像処理
        csv_exporter (CSVExporter):     CSV出力
    """

    def __init__(
        self,
        db_path: str = "ocr_tool.db",
        dpi: int = 150,
        csv_encoding: str = "utf-8-sig",
    ) -> None:
        """
        OCRProcessor を初期化する。

        Args:
            db_path:      SQLiteデータベースファイルのパス
            dpi:          PDF変換時の解像度 (低スペック対応デフォルト 150)
            csv_encoding: CSV出力のエンコーディング (デフォルト BOM付きUTF-8)
        """
        logger.info("OCRProcessorを初期化します")

        # データベース初期化
        self.db = DatabaseManager(db_path)
        self.db.initialize_db()

        # 各コンポーネント初期化
        self.form_manager = FormManager(self.db)
        self.ocr_engine = OCREngine()
        self.pdf_processor = PDFProcessor(dpi=dpi)
        self.csv_exporter = CSVExporter(encoding=csv_encoding)

        # OCRエンジンの可用性をログに記録
        if self.ocr_engine.is_available():
            logger.info(f"OCRエンジン '{self.ocr_engine.engine_name}' で動作します")
        else:
            logger.warning(
                "実際のOCRエンジンが利用できません。モックエンジンで動作します。"
                "ndloccrまたはtesseractをインストールしてください。"
            )

    # -------------------------------------------------------------------------
    # ファイル処理 (単体)
    # -------------------------------------------------------------------------

    def process_file(
        self,
        file_path: str | Path,
        form_id: int,
        callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict[str, Any]:
        """
        1件のファイル (PDF または画像) を OCR 処理する。

        処理ステップ:
            1. ファイル種別判定 (PDF / 画像)
            2. PDF は全ページを画像に変換
            3. 様式フィールド定義を取得
            4. 各ページの対象フィールドを OCR 認識
            5. 結果を DB に保存

        Args:
            file_path: 処理するファイルのパス
            form_id:   使用する様式のID
            callback:  進捗通知コールバック。
                       引数: (現在ページ番号, 総ページ数, ステータスメッセージ)

        Returns:
            dict: {
                'success':   bool,            処理成功フラグ
                'result_id': int | None,      DB保存された OCR結果ID
                'results':   list[dict],      各フィールドの認識結果
                'error':     str | None,      エラーメッセージ (失敗時のみ)
            }
        """
        file_path = Path(file_path)
        logger.info(f"ファイル処理開始: {file_path}, form_id={form_id}")

        # ファイル存在確認
        if not file_path.exists():
            msg = f"ファイルが見つかりません: {file_path}"
            logger.error(msg)
            return {"success": False, "result_id": None, "results": [], "error": msg}

        # 様式・フィールド定義取得
        form = self.form_manager.get_form_with_fields(form_id)
        if form is None:
            msg = f"様式が見つかりません: form_id={form_id}"
            logger.error(msg)
            return {"success": False, "result_id": None, "results": [], "error": msg}

        fields: list[dict[str, Any]] = form.get("fields", [])
        if not fields:
            logger.warning(f"様式 '{form['name']}' にフィールド定義がありません")

        try:
            # ファイル種別によって画像リストを生成
            ext = file_path.suffix.lower()
            if ext in _PDF_EXTENSIONS:
                images = self.pdf_processor.pdf_to_images(file_path)
            elif ext in _IMAGE_EXTENSIONS:
                images = [self.pdf_processor.load_image(file_path)]
            else:
                msg = f"対応していないファイル形式です: {ext}"
                logger.error(msg)
                return {"success": False, "result_id": None, "results": [], "error": msg}

            total_pages = len(images)
            logger.info(f"合計{total_pages}ページを処理します")

            all_field_results: list[dict[str, Any]] = []

            # ページごとに OCR 処理
            for page_idx, image in enumerate(images):
                page_num = page_idx + 1
                status_msg = f"ページ {page_num}/{total_pages} を処理中..."
                logger.debug(status_msg)

                # 進捗コールバック呼び出し
                if callback:
                    try:
                        callback(page_num, total_pages, status_msg)
                    except Exception as cb_exc:
                        logger.warning(f"コールバック呼び出しでエラー: {cb_exc}")

                # このページに属するフィールドのみ抽出
                page_fields = [
                    f for f in fields if f.get("page_number", 1) == page_num
                ]

                if not page_fields:
                    logger.debug(f"ページ {page_num} に対象フィールドなし。スキップ")
                    continue

                # 画像前処理
                processed_image = self.pdf_processor.preprocess_image(image)

                # OCR 一括認識
                page_results = self.ocr_engine.recognize_regions(
                    processed_image, page_fields
                )

                # フィールドIDを認識結果に付加
                field_id_map = {f["field_name"]: f["id"] for f in page_fields}
                for res in page_results:
                    res["field_id"] = field_id_map.get(res.get("field_name", ""))
                    # DBに保存するキー名に合わせる
                    res["recognized_text"] = res.pop("text", "")

                all_field_results.extend(page_results)

            # 完了コールバック
            if callback:
                try:
                    callback(total_pages, total_pages, "OCR処理完了。DBに保存中...")
                except Exception:
                    pass

            # DB に保存
            result_id = self.db.save_ocr_result(
                form_id=form_id,
                source_file=str(file_path),
                fields=all_field_results,
                status="success",
            )

            logger.info(f"ファイル処理完了: result_id={result_id}")
            return {
                "success":   True,
                "result_id": result_id,
                "results":   all_field_results,
                "error":     None,
            }

        except Exception as exc:
            logger.exception(f"ファイル処理中に予期しないエラーが発生しました: {exc}")

            # エラー時も DB に記録 (ステータス: error)
            try:
                result_id = self.db.save_ocr_result(
                    form_id=form_id,
                    source_file=str(file_path),
                    fields=[],
                    status="error",
                )
            except Exception:
                result_id = None

            return {
                "success":   False,
                "result_id": result_id,
                "results":   [],
                "error":     str(exc),
            }

    # -------------------------------------------------------------------------
    # バッチ処理 (複数ファイル)
    # -------------------------------------------------------------------------

    def process_batch(
        self,
        file_paths: list[str | Path],
        form_id: int,
        callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict[str, Any]:
        """
        複数のファイルを一括 OCR 処理する。

        各ファイルを順番に process_file() で処理し、
        結果と統計情報をまとめて返す。

        Args:
            file_paths: 処理するファイルパスのリスト
            form_id:    使用する様式のID
            callback:   進捗通知コールバック。
                        引数: (処理済みファイル数, 総ファイル数, ステータスメッセージ)

        Returns:
            dict: {
                'total':       int,         処理対象ファイル数
                'success':     int,         成功件数
                'failed':      int,         失敗件数
                'result_ids':  list[int],   成功した OCR結果ID のリスト
                'details':     list[dict],  各ファイルの処理結果
            }
        """
        total = len(file_paths)
        logger.info(f"バッチ処理開始: {total}件, form_id={form_id}")

        success_count = 0
        failed_count = 0
        result_ids: list[int] = []
        details: list[dict[str, Any]] = []

        for idx, file_path in enumerate(file_paths):
            file_num = idx + 1
            file_name = Path(file_path).name
            status_msg = f"[{file_num}/{total}] {file_name} を処理中..."

            logger.info(status_msg)

            # ファイルレベルの進捗コールバック
            if callback:
                try:
                    callback(file_num, total, status_msg)
                except Exception as cb_exc:
                    logger.warning(f"バッチコールバックエラー: {cb_exc}")

            # 1ファイル処理 (内部の進捗コールバックは渡さない: 二重通知を避ける)
            result = self.process_file(file_path, form_id, callback=None)
            result["file_path"] = str(file_path)
            details.append(result)

            if result["success"]:
                success_count += 1
                if result.get("result_id") is not None:
                    result_ids.append(result["result_id"])
            else:
                failed_count += 1
                logger.warning(f"処理失敗: {file_name} - {result.get('error', '不明なエラー')}")

        logger.info(
            f"バッチ処理完了: 成功={success_count}, 失敗={failed_count}, 合計={total}"
        )

        # 完了通知
        if callback:
            try:
                callback(
                    total, total,
                    f"バッチ処理完了: 成功 {success_count}件 / 失敗 {failed_count}件"
                )
            except Exception:
                pass

        return {
            "total":      total,
            "success":    success_count,
            "failed":     failed_count,
            "result_ids": result_ids,
            "details":    details,
        }

    # -------------------------------------------------------------------------
    # CSV出力
    # -------------------------------------------------------------------------

    def export_to_csv(
        self,
        result_ids: list[int],
        output_path: str | Path,
        form_id: int,
    ) -> Path:
        """
        指定した OCR 結果 ID リストの認識データを CSV に出力する。

        Args:
            result_ids:  出力対象の OCR結果ID リスト
            output_path: 出力先 CSV ファイルパス
            form_id:     フィールド定義を取得するための様式ID

        Returns:
            Path: 出力した CSV ファイルのパス

        Raises:
            ValueError: result_ids が空の場合
            KeyError:   様式が存在しない場合
        """
        if not result_ids:
            raise ValueError("出力するOCR結果IDが指定されていません")

        output_path = Path(output_path)

        # 様式フィールド定義取得 (列順制御のため)
        form = self.form_manager.get_form_with_fields(form_id)
        if form is None:
            raise KeyError(f"様式が見つかりません: form_id={form_id}")

        form_fields = form.get("fields", [])

        # DB から結果データ取得
        results = self.db.get_ocr_results_by_ids(result_ids)
        if not results:
            raise ValueError("指定された OCR結果が見つかりません")

        logger.info(f"CSV出力開始: {len(results)}件 → {output_path}")

        # フィールド定義がある場合は列順制御あり、ない場合はデフォルト
        if form_fields:
            saved_path = self.csv_exporter.export_with_fields(
                results=results,
                output_path=str(output_path),
                form_fields=form_fields,
            )
        else:
            saved_path = self.csv_exporter.export_batch(
                output_path=str(output_path),
                batch_results=results,
            )

        logger.info(f"CSV出力完了: {saved_path}")
        return saved_path

    # -------------------------------------------------------------------------
    # ユーティリティ
    # -------------------------------------------------------------------------

    def get_engine_info(self) -> dict[str, Any]:
        """
        現在使用中の OCR エンジン情報を返す。

        Returns:
            dict: {
                'engine_name': str,   エンジン名
                'is_available': bool, 実認識可能か
            }
        """
        return {
            "engine_name":  self.ocr_engine.engine_name,
            "is_available": self.ocr_engine.is_available(),
        }

    def get_form_list(self) -> list[dict[str, Any]]:
        """
        登録済み様式の一覧を返す。

        Returns:
            list[dict]: 様式データのリスト
        """
        return self.form_manager.list_forms()

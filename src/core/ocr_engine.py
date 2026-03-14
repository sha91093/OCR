"""
ocr_engine.py - OCRエンジン管理モジュール

担当: 佐藤 愛子 (Aiko Sato)
作成日: 2026-03-13

OCRエンジンの初期化・テキスト認識を担う。
ndlocr-lite が利用可能な場合はそれを使用し、
利用できない場合は pytesseract → 簡易モック の順でフォールバックする。

【ndlocr-lite のインストール方法】
    pip install ndlocr-lite @ git+https://github.com/ndl-lab/ndlocr-lite.git
    インストール後のモジュール名は "ocr" (import ocr)。

【ndlocr-lite と ndlocr の違い】
    ndlocr-lite : GitHub からインストール。モデルが小さく低スペックPC向け。
    ndlocr      : フル版。高精度だがモデルが大きく RAM・ディスク要求が高い。
    → 本ツールは必ず ndlocr-lite を使用すること。

フォールバック戦略:
    1. ndlocr-lite (import ocr) : 国立国会図書館OCR軽量版。日本語精度が最も高い。
    2. pytesseract               : Tesseract OSSラッパー。要 tesseract バイナリインストール。
    3. MockEngine                : テスト用ダミー実装。実認識は行わないが動作確認に使える。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# エンジン可用性フラグ (import 時に一度だけ判定)
# ---------------------------------------------------------------------------

_NDLOCR_AVAILABLE = False
_TESSERACT_AVAILABLE = False

try:
    # ndlocr-lite のパッケージ存在確認
    # GitHub からインストール: pip install ndlocr-lite @ git+https://github.com/ndl-lab/ndlocr-lite.git
    # インストール後のモジュール名は "ocr" (deim, parseq 等も同梱される)
    import ocr as _ndlocr_check  # type: ignore[import]
    _NDLOCR_AVAILABLE = True
    logger.info("ndlocr-lite パッケージが利用可能です")
except ImportError:
    logger.info("ndlocr-lite パッケージが見つかりません。次のエンジンを試みます")

try:
    import pytesseract  # type: ignore[import]
    from PIL import Image as _PilImage
    # tesseract バイナリが実際に呼び出せるか確認
    pytesseract.get_tesseract_version()
    _TESSERACT_AVAILABLE = True
    logger.info("pytesseract (Tesseract OCR) が利用可能です")
except Exception:
    logger.info("pytesseractが利用できません。モックエンジンにフォールバックします")


# ---------------------------------------------------------------------------
# 内部エンジン実装
# ---------------------------------------------------------------------------

class _NdlocrEngine:
    """
    ndlocr-lite を使った OCR エンジン実装。

    ndlocr-lite は日本語文書専用に調整された軽量版 OCR エンジンであり、
    縦書き・旧字体を含む申請書類に高い認識精度を発揮する。
    低スペックPC向けにモデルサイズが抑えられている点が特徴。

    インストール:
        pip install ndlocr-lite @ git+https://github.com/ndl-lab/ndlocr-lite.git
    """

    def __init__(self) -> None:
        """ndlocr-lite エンジンを初期化する。"""
        import argparse
        import importlib.util
        import os

        spec = importlib.util.find_spec("ocr")
        if spec is None:
            raise ImportError("ndlocr-lite が見つかりません")
        # ndlocr-lite の src/ ディレクトリ (モデル・設定ファイルの基準パス)
        src_dir = os.path.dirname(spec.origin)

        args = argparse.Namespace(
            det_weights=os.path.join(src_dir, "model", "deim-s-1024x1024.onnx"),
            det_classes=os.path.join(src_dir, "config", "ndl.yaml"),
            det_score_threshold=0.2,
            det_conf_threshold=0.25,
            det_iou_threshold=0.2,
            rec_weights=os.path.join(
                src_dir, "model", "parseq-ndl-16x768-100-tiny-165epoch-tegaki2.onnx"
            ),
            rec_weights30=os.path.join(
                src_dir, "model", "parseq-ndl-16x256-30-tiny-192epoch-tegaki3.onnx"
            ),
            rec_weights50=os.path.join(
                src_dir, "model", "parseq-ndl-16x384-50-tiny-146epoch-tegaki2.onnx"
            ),
            rec_classes=os.path.join(src_dir, "config", "NDLmoji.yaml"),
            device="cpu",
            viz=False,
        )

        from ocr import get_detector, get_recognizer  # type: ignore[import]
        # ndloccr のモデルロード。LGWAN環境では事前オフライン配置が必要。
        # 手順: docs/offline_setup.md の「手順 3」を参照。
        self._detector = get_detector(args)
        self._recognizer100 = get_recognizer(args=args)
        self._recognizer30 = get_recognizer(args=args, weights_path=args.rec_weights30)
        self._recognizer50 = get_recognizer(args=args, weights_path=args.rec_weights50)
        logger.info("ndlocr-lite エンジンを初期化しました")

    def recognize(self, image: Any, region: Optional[tuple[int, int, int, int]] = None) -> dict[str, Any]:
        """
        指定領域のテキストを ndlocr-lite で認識する。

        Args:
            image:  PIL.Image オブジェクト
            region: (x1, y1, x2, y2) のクロップ領域。None の場合は全体を対象。

        Returns:
            dict: {'text': str, 'confidence': float}
        """
        import tempfile
        import xml.etree.ElementTree as ET

        import numpy as np
        from ocr import (  # type: ignore[import]
            RecogLine,
            convert_to_xml_string3,
            process_cascade,
            process_detector,
        )
        from reading_order.xy_cut.eval import eval_xml  # type: ignore[import]

        target: Any = image
        if region is not None:
            x1, y1, x2, y2 = region
            target = image.crop((x1, y1, x2, y2))

        img = np.array(target.convert("RGB"))
        img_h, img_w = img.shape[:2]

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                detections, classeslist = process_detector(
                    self._detector, "input.jpg", img, tmpdir, issaveimg=False
                )

            # 検出結果を ndlocr-lite 内部 XML 形式に変換
            resultobj: list[Any] = [dict(), dict()]
            resultobj[0][0] = []
            for i in range(17):
                resultobj[1][i] = []
            for det in detections:
                xmin, ymin, xmax, ymax = det["box"]
                conf = det["confidence"]
                char_count = det["pred_char_count"]
                if det["class_index"] == 0:
                    resultobj[0][0].append([xmin, ymin, xmax, ymax])
                resultobj[1][det["class_index"]].append(
                    [xmin, ymin, xmax, ymax, conf, char_count]
                )

            xmlstr = convert_to_xml_string3(img_w, img_h, "input.jpg", classeslist, resultobj)
            xmlstr = "<OCRDATASET>" + xmlstr + "</OCRDATASET>"
            root = ET.fromstring(xmlstr)
            eval_xml(root, logger=None)

            alllineobj: list[RecogLine] = []
            for idx, lineobj in enumerate(root.findall(".//LINE")):
                xmin = int(lineobj.get("X", 0))
                ymin = int(lineobj.get("Y", 0))
                line_w = int(lineobj.get("WIDTH", 0))
                line_h = int(lineobj.get("HEIGHT", 0))
                try:
                    pred_char_cnt = float(lineobj.get("PRED_CHAR_CNT", 100.0))
                except (TypeError, ValueError):
                    pred_char_cnt = 100.0
                lineimg = img[ymin:ymin + line_h, xmin:xmin + line_w, :]
                alllineobj.append(RecogLine(lineimg, idx, pred_char_cnt))

            # 行検出が 0 件の場合、検出枠全体を 1 行として扱う
            if len(alllineobj) == 0 and len(detections) > 0:
                for idx, det in enumerate(detections):
                    xmin, ymin, xmax, ymax = det["box"]
                    line_w = int(xmax - xmin)
                    line_h = int(ymax - ymin)
                    if line_w > 0 and line_h > 0:
                        lineimg = img[int(ymin):int(ymax), int(xmin):int(xmax), :]
                        alllineobj.append(RecogLine(lineimg, idx, 100.0))

            if not alllineobj:
                return {"text": "", "confidence": 0.0}

            result_lines = process_cascade(
                alllineobj,
                self._recognizer30,
                self._recognizer50,
                self._recognizer100,
                is_cascade=True,
            )
            text = "\n".join(result_lines)

        except Exception as exc:
            logger.error(f"ndlocr-lite の認識処理でエラーが発生しました: {exc}")
            text = ""

        return {"text": text.strip(), "confidence": 0.9 if text.strip() else 0.0}


class _TesseractEngine:
    """
    pytesseract (Tesseract OCR) を使った OCR エンジン実装。

    ndloccr が利用できない場合のフォールバック。
    日本語認識には 'jpn' 言語データが必要。
    """

    def __init__(self) -> None:
        """Tesseract エンジンを初期化する。"""
        import pytesseract  # type: ignore[import]
        self._pytesseract = pytesseract
        logger.info("Tesseractエンジンを初期化しました")

    def recognize(self, image: Any, region: Optional[tuple[int, int, int, int]] = None) -> dict[str, Any]:
        """
        指定領域のテキストを Tesseract で認識する。

        Args:
            image:  PIL.Image オブジェクト
            region: (x1, y1, x2, y2) のクロップ領域。None の場合は全体を対象。

        Returns:
            dict: {'text': str, 'confidence': float}
        """
        # 領域クロップ
        target: Any = image
        if region is not None:
            x1, y1, x2, y2 = region
            target = image.crop((x1, y1, x2, y2))

        # 日本語認識設定
        # --psm 6: 統一されたテキストブロックとして認識
        # -l jpn: 日本語言語モデルを使用
        config = "--psm 6 -l jpn"

        try:
            # output_type=dict で詳細データ取得
            data = self._pytesseract.image_to_data(
                target,
                config=config,
                output_type=self._pytesseract.Output.DICT,
            )
            # 信頼度が 0 以上のテキストのみ結合
            words = []
            confidences = []
            for i, conf in enumerate(data["conf"]):
                if int(conf) > 0:
                    words.append(data["text"][i])
                    confidences.append(float(conf) / 100.0)

            text = " ".join(w for w in words if w.strip())
            confidence = sum(confidences) / len(confidences) if confidences else 0.0

        except Exception as exc:
            logger.error(f"Tesseractの認識処理でエラーが発生しました: {exc}")
            text, confidence = "", 0.0

        return {"text": text.strip(), "confidence": round(confidence, 3)}


class _MockEngine:
    """
    テスト用のモック OCR エンジン。

    実際の画像認識は行わず、一定のダミーテキストを返す。
    CI/CD 環境や OCR ライブラリが未インストールの開発環境で
    アプリケーション全体の動作確認をするために使用する。
    """

    def __init__(self) -> None:
        """モックエンジンを初期化する。"""
        logger.warning(
            "OCRエンジンが見つからないため、モックエンジンで動作します。"
            "実際の文字認識は行われません。"
        )

    def recognize(self, image: Any, region: Optional[tuple[int, int, int, int]] = None) -> dict[str, Any]:
        """
        ダミーのテキスト認識結果を返す。

        Args:
            image:  PIL.Image オブジェクト (使用しない)
            region: クロップ領域 (使用しない)

        Returns:
            dict: {'text': '[OCRモック]', 'confidence': 0.0}
        """
        return {"text": "[OCRモック: テキストが認識されませんでした]", "confidence": 0.0}


# ---------------------------------------------------------------------------
# 公開クラス: OCREngine
# ---------------------------------------------------------------------------

class OCREngine:
    """
    OCRエンジンのファサードクラス。

    利用可能なエンジンを自動検出して初期化し、
    統一されたインターフェースで文字認識機能を提供する。

    利用優先順位:
        1. ndlocr-lite  (最高精度・日本語特化・低スペックPC向け軽量版)
        2. pytesseract  (汎用・要 Tesseract インストール)
        3. MockEngine   (テスト用フォールバック)

    Example:
        >>> engine = OCREngine()
        >>> if engine.is_available():
        ...     result = engine.recognize_text(image, region=(10, 20, 200, 60))
        ...     print(result['text'])
    """

    def __init__(self) -> None:
        """利用可能な OCR エンジンを選択して初期化する。"""
        self._engine_name: str
        self._engine: Any

        if _NDLOCR_AVAILABLE:
            try:
                self._engine = _NdlocrEngine()
                self._engine_name = "ndloccr"
                logger.info("OCRエンジン: ndlocr-lite を使用します")
                return
            except Exception as exc:
                logger.warning(f"ndlocr-lite の初期化に失敗しました: {exc}")

        if _TESSERACT_AVAILABLE:
            try:
                self._engine = _TesseractEngine()
                self._engine_name = "tesseract"
                logger.info("OCRエンジン: Tesseract にフォールバックします")
                return
            except Exception as exc:
                logger.warning(f"Tesseractの初期化に失敗しました: {exc}")

        # どのエンジンも使えない場合はモックで代替
        self._engine = _MockEngine()
        self._engine_name = "mock"

    def is_available(self) -> bool:
        """
        実際に文字認識が行えるエンジンが初期化されているかを返す。

        Returns:
            bool: モックエンジン以外が使用中の場合 True
        """
        return self._engine_name != "mock"

    @property
    def engine_name(self) -> str:
        """現在使用中のエンジン名を返す。"""
        return self._engine_name

    def recognize_text(
        self,
        image: Any,
        region: Optional[tuple[int, int, int, int]] = None,
    ) -> dict[str, Any]:
        """
        画像の指定領域からテキストを認識する。

        Args:
            image:  PIL.Image オブジェクト
            region: (x1, y1, x2, y2) のクロップ領域 (px単位)。
                    None の場合は画像全体を対象とする。

        Returns:
            dict: {
                'text':       認識されたテキスト文字列,
                'confidence': 認識信頼度 (0.0〜1.0)
            }
        """
        if image is None:
            logger.warning("recognize_text: image が None です")
            return {"text": "", "confidence": 0.0}

        logger.debug(f"テキスト認識開始: region={region}, engine={self._engine_name}")
        result = self._engine.recognize(image, region)
        logger.debug(f"テキスト認識完了: text='{result['text'][:30]}...', conf={result['confidence']:.3f}")
        return result

    def recognize_regions(
        self,
        image: Any,
        regions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        複数の領域を一括認識する。

        Args:
            image:   PIL.Image オブジェクト
            regions: 認識対象領域のリスト。各要素は辞書:
                     - field_name (str): フィールド識別名
                     - x1, y1, x2, y2 (float): 領域座標 (px)
                     - page_number (int, 省略可): ページ番号 (ログ用)

        Returns:
            list[dict]: 認識結果のリスト。各要素:
                        - field_name (str): フィールド識別名 (入力そのまま)
                        - text (str): 認識テキスト
                        - confidence (float): 信頼度 0.0〜1.0
        """
        results: list[dict[str, Any]] = []

        for region_def in regions:
            field_name: str = region_def.get("field_name", "unknown")
            x1 = int(region_def.get("x1", 0))
            y1 = int(region_def.get("y1", 0))
            x2 = int(region_def.get("x2", 0))
            y2 = int(region_def.get("y2", 0))

            # 座標の妥当性チェック
            if x2 <= x1 or y2 <= y1:
                logger.warning(
                    f"フィールド '{field_name}' の領域座標が不正です: "
                    f"({x1}, {y1}, {x2}, {y2}) → スキップします"
                )
                results.append({
                    "field_name": field_name,
                    "text": "",
                    "confidence": 0.0,
                })
                continue

            recognition = self.recognize_text(image, region=(x1, y1, x2, y2))
            results.append({
                "field_name": field_name,
                "text": recognition["text"],
                "confidence": recognition["confidence"],
            })

        logger.info(f"一括認識完了: {len(results)}件のフィールドを処理しました")
        return results

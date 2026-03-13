"""
ocr_engine.py - OCRエンジン管理モジュール

担当: 佐藤 愛子 (Aiko Sato)
作成日: 2026-03-13

OCRエンジンの初期化・テキスト認識を担う。
ndlocr-lite (ndloccr) が利用可能な場合はそれを使用し、
利用できない場合は pytesseract → 簡易モック の順でフォールバックする。

フォールバック戦略:
    1. ndloccr  : 国立国会図書館OCR。日本語精度が最も高い。
    2. pytesseract: Tesseract OSSラッパー。要 tesseract バイナリインストール。
    3. MockEngine : テスト用ダミー実装。実認識は行わないが動作確認に使える。
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
    # ndloccr パッケージの存在確認
    # 実際の API は ndloccr のバージョンによって異なる場合があるため
    # インポートの成否だけで判定し、詳細は _NdlocrEngine 内で処理する
    import ndloccr  # type: ignore[import]
    _NDLOCR_AVAILABLE = True
    logger.info("ndloccrパッケージが利用可能です")
except ImportError:
    logger.info("ndloccrパッケージが見つかりません。次のエンジンを試みます")

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
    ndloccr を使った OCR エンジン実装。

    ndloccr は日本語文書専用に調整されており、
    縦書き・旧字体を含む申請書類に高い認識精度を発揮する。
    """

    def __init__(self) -> None:
        """ndloccr エンジンを初期化する。"""
        import ndloccr  # type: ignore[import]
        # ndloccr のモデルロード。初回はモデルファイルのダウンロードが発生する場合がある
        self._engine = ndloccr
        logger.info("ndloccrエンジンを初期化しました")

    def recognize(self, image: Any, region: Optional[tuple[int, int, int, int]] = None) -> dict[str, Any]:
        """
        指定領域のテキストを ndloccr で認識する。

        Args:
            image:  PIL.Image オブジェクト
            region: (x1, y1, x2, y2) のクロップ領域。None の場合は全体を対象。

        Returns:
            dict: {'text': str, 'confidence': float}
        """
        from PIL import Image

        # 必要に応じて領域をクロップ
        target: Any = image
        if region is not None:
            x1, y1, x2, y2 = region
            target = image.crop((x1, y1, x2, y2))

        # ndloccr の API を呼び出す
        # ndloccr は numpy 配列または PIL.Image を受け付けることが多いが
        # バージョン差異を吸収するため numpy 変換してから渡す
        import numpy as np
        img_array = np.array(target.convert("RGB"))

        try:
            # ndloccr.ocr() の戻り値は文字列 or (文字列, 信頼度) のどちらかの場合がある
            result = self._engine.ocr(img_array)
            if isinstance(result, tuple):
                text, confidence = result[0], float(result[1])
            else:
                text = str(result)
                confidence = 0.9  # ndloccr が信頼度を返さない場合のデフォルト値
        except Exception as exc:
            logger.error(f"ndloccrの認識処理でエラーが発生しました: {exc}")
            text, confidence = "", 0.0

        return {"text": text.strip(), "confidence": confidence}


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
        1. ndloccr  (最高精度・日本語特化)
        2. pytesseract (汎用・要 Tesseract インストール)
        3. MockEngine  (テスト用フォールバック)

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
                logger.info("OCRエンジン: ndloccr を使用します")
                return
            except Exception as exc:
                logger.warning(f"ndloccrの初期化に失敗しました: {exc}")

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

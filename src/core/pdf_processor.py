"""
pdf_processor.py - PDF処理モジュール

担当: 佐藤 愛子 (Aiko Sato)
作成日: 2026-03-13

pdf2image を使って PDF ファイルを PIL.Image オブジェクトのリストに変換し、
OCRエンジンへ渡す前の画像前処理も担う。

依存ライブラリ:
    - pdf2image  : PDF → PIL.Image 変換 (poppler-utils が別途必要)
    - Pillow     : 画像操作
    - opencv-python-headless (cv2): 高度な前処理 (オプション)

注意:
    pdf2image を使うには OS に poppler-utils がインストールされている必要がある。
    Ubuntu/Debian: sudo apt-get install poppler-utils
    Windows      : poppler を PATH に追加する
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# オプション依存の可用性チェック
# ---------------------------------------------------------------------------

_PDF2IMAGE_AVAILABLE = False
_CV2_AVAILABLE = False

try:
    from pdf2image import convert_from_path  # type: ignore[import]
    _PDF2IMAGE_AVAILABLE = True
    logger.info("pdf2imageが利用可能です")
except ImportError:
    logger.warning("pdf2imageが見つかりません。PDFの読み込みが制限されます")

try:
    import cv2  # type: ignore[import]
    import numpy as np
    _CV2_AVAILABLE = True
    logger.info("OpenCV (cv2) が利用可能です")
except ImportError:
    logger.info("OpenCVが見つかりません。Pillowのみで前処理を行います")


class PDFProcessor:
    """
    PDF ファイルを画像化し、OCR に適した形に前処理するクラス。

    低スペック PC での動作を考慮し、DPI はデフォルト 150 に設定している。
    高精度が必要な場合は dpi=300 に変更することを推奨するが、
    メモリ使用量が約 4 倍になるため注意が必要。

    Attributes:
        dpi (int): PDF ラスタライズ時の解像度 (dots per inch)
    """

    def __init__(self, dpi: int = 150) -> None:
        """
        PDFProcessor を初期化する。

        Args:
            dpi: PDF → 画像変換時の解像度。
                 低スペック環境では 150、高精度優先なら 300 を推奨。
        """
        self.dpi = dpi
        logger.info(f"PDFProcessorを初期化しました: dpi={self.dpi}")

        if not _PDF2IMAGE_AVAILABLE:
            logger.warning(
                "pdf2imageが利用できないため、PDF処理は制限されます。"
                "pip install pdf2image でインストールしてください。"
            )

    @staticmethod
    def is_pdf_supported() -> bool:
        """pdf2image が利用可能かどうかを返す。"""
        return _PDF2IMAGE_AVAILABLE

    def pdf_to_images(self, pdf_path: str | Path) -> list[Any]:
        """
        PDF ファイルの全ページを PIL.Image のリストに変換する。

        Args:
            pdf_path: PDF ファイルのパス

        Returns:
            list[PIL.Image]: 各ページの画像リスト (1ページ目が index 0)

        Raises:
            FileNotFoundError: PDF ファイルが存在しない場合
            RuntimeError: pdf2image が利用できない場合
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDFファイルが見つかりません: {pdf_path}")

        if not _PDF2IMAGE_AVAILABLE:
            raise RuntimeError(
                "pdf2imageがインストールされていません。"
                "pip install pdf2image を実行してください。"
            )

        logger.info(f"PDF変換開始: {pdf_path}, dpi={self.dpi}")

        try:
            images = convert_from_path(
                str(pdf_path),
                dpi=self.dpi,
                fmt="RGB",          # RGB形式で統一 (グレースケールPDFも対応)
                thread_count=1,     # 低スペック対応: シングルスレッド
            )
            logger.info(f"PDF変換完了: {len(images)}ページ")
            return images

        except Exception as exc:
            logger.error(f"PDF変換中にエラーが発生しました: {exc}")
            raise

    def get_page_count(self, pdf_path: str | Path) -> int:
        """
        PDF のページ数を取得する。

        フル変換を避けるため、pdfinfo (poppler) を使って軽量に取得する。
        pdfinfo が利用できない環境では全ページ変換にフォールバック。

        Args:
            pdf_path: PDF ファイルのパス

        Returns:
            int: ページ数
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDFファイルが見つかりません: {pdf_path}")

        # pdf2image の pdfinfo_from_path を使ってメタデータのみ取得
        if _PDF2IMAGE_AVAILABLE:
            try:
                from pdf2image import pdfinfo_from_path  # type: ignore[import]
                info = pdfinfo_from_path(str(pdf_path))
                page_count = info.get("Pages", 0)
                logger.debug(f"PDFページ数: {page_count}")
                return int(page_count)
            except Exception as exc:
                logger.warning(f"pdfinfo取得に失敗しました。全変換にフォールバック: {exc}")
                images = self.pdf_to_images(pdf_path)
                return len(images)

        return 0

    def load_image(self, image_path: str | Path) -> Any:
        """
        画像ファイルを PIL.Image として読み込む。

        PDF 以外の画像ファイル (JPEG, PNG, TIFF 等) を
        直接 OCR にかけたい場合に使用する。

        Args:
            image_path: 画像ファイルのパス

        Returns:
            PIL.Image: 読み込んだ画像オブジェクト

        Raises:
            FileNotFoundError: ファイルが存在しない場合
            OSError: 画像ファイルの読み込みに失敗した場合
        """
        from PIL import Image

        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"画像ファイルが見つかりません: {image_path}")

        try:
            image = Image.open(str(image_path)).convert("RGB")
            logger.info(f"画像読み込み完了: {image_path}, サイズ={image.size}")
            return image
        except OSError as exc:
            logger.error(f"画像ファイルの読み込みに失敗しました: {exc}")
            raise

    def preprocess_image(self, image: Any) -> Any:
        """
        OCR 精度向上のための画像前処理を行う。

        処理内容:
            1. グレースケール変換
            2. コントラスト調整 (CLAHE または Pillow の ImageEnhance)
            3. ノイズ除去 (OpenCV が利用可能な場合)
            4. 二値化 (OpenCV Otsu 法 または Pillow threshold)

        OpenCV が利用できない環境では Pillow のみで簡易前処理を行う。

        Args:
            image: PIL.Image オブジェクト (RGB または グレースケール)

        Returns:
            PIL.Image: 前処理済みの画像オブジェクト (グレースケール)
        """
        from PIL import Image, ImageEnhance, ImageFilter

        logger.debug("画像前処理を開始します")

        if _CV2_AVAILABLE:
            return self._preprocess_with_cv2(image)
        else:
            return self._preprocess_with_pillow(image)

    def _preprocess_with_cv2(self, image: Any) -> Any:
        """
        OpenCV を使った高品質な前処理。

        処理ステップ:
            1. グレースケール変換
            2. CLAHE (コントラスト制限付き適応ヒストグラム均一化)
            3. ガウシアンブラー (軽いノイズ除去)
            4. Otsu 二値化

        Args:
            image: PIL.Image オブジェクト

        Returns:
            PIL.Image: 二値化済み画像
        """
        from PIL import Image

        # PIL.Image → numpy 配列 に変換
        img_array = np.array(image.convert("RGB"))

        # グレースケール変換
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # CLAHE: 局所的なコントラスト強調。申請書の薄い印字にも有効
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # 軽いガウシアンブラーでノイズを低減
        blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)

        # Otsu 法で最適なしきい値を自動決定して二値化
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # numpy 配列 → PIL.Image に変換して返す
        result = Image.fromarray(binary, mode="L")
        logger.debug("OpenCVによる前処理が完了しました")
        return result

    def _preprocess_with_pillow(self, image: Any) -> Any:
        """
        Pillow のみを使った簡易前処理。

        OpenCV が利用できない環境 (軽量インストール) 向け。
        CLAHE や Otsu の代わりに Pillow の基本機能で対応する。

        処理ステップ:
            1. グレースケール変換
            2. シャープネス強調
            3. コントラスト強調

        Args:
            image: PIL.Image オブジェクト

        Returns:
            PIL.Image: 前処理済み画像
        """
        from PIL import Image, ImageEnhance, ImageFilter

        # グレースケール変換
        gray = image.convert("L")

        # シャープネス強調 (エッジ鮮明化でOCR認識率向上)
        sharp = ImageEnhance.Sharpness(gray).enhance(2.0)

        # コントラスト強調
        contrasted = ImageEnhance.Contrast(sharp).enhance(1.5)

        logger.debug("Pillowによる簡易前処理が完了しました")
        return contrasted

    def crop_region(
        self,
        image: Any,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        padding: int = 2,
    ) -> Any:
        """
        画像から指定領域を切り出す。

        フィールド定義の座標に基づいてトリミングする際に使用。
        少量のパディングを付けることで、境界付近の文字が欠けるのを防ぐ。

        Args:
            image:   PIL.Image オブジェクト
            x1, y1:  左上座標 (px)
            x2, y2:  右下座標 (px)
            padding: 境界に追加するパディング量 (px)。デフォルト 2px。

        Returns:
            PIL.Image: クロップされた画像
        """
        width, height = image.size

        # パディングを考慮した座標 (画像範囲外にはみ出さないようクランプ)
        left   = max(0, int(x1) - padding)
        top    = max(0, int(y1) - padding)
        right  = min(width,  int(x2) + padding)
        bottom = min(height, int(y2) + padding)

        if right <= left or bottom <= top:
            logger.warning(
                f"クロップ領域が無効です: ({left}, {top}, {right}, {bottom})"
            )
            return image  # 無効な領域の場合は元画像をそのまま返す

        cropped = image.crop((left, top, right, bottom))
        logger.debug(f"領域クロップ完了: ({left}, {top}, {right}, {bottom}), サイズ={cropped.size}")
        return cropped

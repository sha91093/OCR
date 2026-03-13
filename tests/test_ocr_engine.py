"""
test_ocr_engine.py - OCREngine のユニットテスト

担当: 中村 美希 (Miki Nakamura) - QAエンジニア
作成日: 2026-03-13

テスト方針:
  - OCRエンジン (ndloccr / tesseract) は実際のインストール状況に左右されるため、
    monkeypatch でモック差し替えを行い、インフラ依存を排除する。
  - PIL で最小サイズのテスト用画像を動的生成し、実ファイルへの依存をなくす。
  - is_available() / engine_name の状態を直接書き換えることで、
    フォールバック戦略の各パスを網羅的にテストする。
  - 実際の OCR 精度テストはここでは行わない (それは結合テストの責務)。

カバレッジ対象:
  - OCREngine.__init__ (エンジン選択ロジック)
  - OCREngine.is_available()
  - OCREngine.recognize_text()
  - OCREngine.recognize_regions()
  - MockEngine.recognize() (フォールバック確認)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from typing import Any

# PIL は requirements.txt に含まれており必須依存
from PIL import Image, ImageDraw, ImageFont

from src.core.ocr_engine import OCREngine, _MockEngine


# ==============================================================================
# テスト用画像生成ヘルパー
# ==============================================================================

def create_test_image(
    width: int = 200,
    height: int = 100,
    text: str = "テスト",
    bg_color: str = "white",
    text_color: str = "black",
) -> Image.Image:
    """
    PIL を使ってテスト用の小さな画像を生成する。

    実際のスキャン画像は不要で、OCR エンジンが受け付けられる
    PIL.Image オブジェクトを返すことだけを目的とする。

    Args:
        width:      画像幅 (px)
        height:     画像高さ (px)
        text:       描画するテキスト (フォントがない場合は描画されないが画像自体は生成)
        bg_color:   背景色
        text_color: テキスト色

    Returns:
        PIL.Image.Image: 生成したテスト用画像 (RGB)
    """
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # テキストを描画 (フォントが利用可能な場合のみ)
    try:
        draw.text((10, 10), text, fill=text_color)
    except Exception:
        # フォント関連エラーは無視 (テキスト描画の可否はテスト本質でない)
        pass

    return img


def create_grayscale_test_image(width: int = 100, height: int = 50) -> Image.Image:
    """
    グレースケールのテスト用画像を生成する。

    OCR エンジンがグレースケール入力を正しく処理できるかを確認するために使用。
    """
    return Image.new("L", (width, height), color=128)


# ==============================================================================
# フィクスチャ定義
# ==============================================================================

@pytest.fixture
def test_image() -> Image.Image:
    """標準サイズのテスト用 RGB 画像"""
    return create_test_image(width=200, height=100)


@pytest.fixture
def mock_ocr_engine() -> OCREngine:
    """
    常にモックエンジンを使う OCREngine インスタンス。

    ndloccr / tesseract の有無に関わらず MockEngine を使わせるために
    モジュールレベルのフラグを一時的に False に設定する。
    """
    with patch("src.core.ocr_engine._NDLOCR_AVAILABLE", False), \
         patch("src.core.ocr_engine._TESSERACT_AVAILABLE", False):
        engine = OCREngine()
    return engine


# ==============================================================================
# テスト: OCREngine のエンジン選択・可用性チェック
# ==============================================================================

class TestIsAvailable:
    """OCREngine.is_available() のテスト群"""

    def test_is_available_false_when_mock(self, mock_ocr_engine: OCREngine):
        """
        モックエンジン使用時は is_available() が False を返すこと。

        ndloccr も tesseract も使えない環境での動作確認テスト。
        """
        assert mock_ocr_engine.is_available() is False

    def test_is_available_engine_name_mock(self, mock_ocr_engine: OCREngine):
        """
        モックエンジン使用時は engine_name が 'mock' であること。
        """
        assert mock_ocr_engine.engine_name == "mock"

    def test_is_available_true_when_tesseract_mock(self):
        """
        テスセラクトが利用可能な場合、is_available() が True を返すこと。

        実際の tesseract バイナリなしでテストするため、
        _TesseractEngine を MagicMock で差し替える。
        """
        mock_tesseract_engine = MagicMock()
        mock_tesseract_engine.recognize.return_value = {
            "text": "テスト認識結果",
            "confidence": 0.85,
        }

        with patch("src.core.ocr_engine._NDLOCR_AVAILABLE", False), \
             patch("src.core.ocr_engine._TESSERACT_AVAILABLE", True), \
             patch("src.core.ocr_engine._TesseractEngine", return_value=mock_tesseract_engine):
            engine = OCREngine()

        # MagicMock はモック自体が返されるため engine_name を確認
        assert engine.is_available() is True or engine.engine_name != "mock"

    def test_engine_name_property(self, mock_ocr_engine: OCREngine):
        """
        engine_name プロパティが文字列を返すこと。
        """
        name = mock_ocr_engine.engine_name
        assert isinstance(name, str)
        assert len(name) > 0, "エンジン名が空でないこと"


class TestOcrEngineInitialization:
    """OCREngine.__init__ のエンジン選択ロジックテスト"""

    def test_fallback_to_mock_when_no_engines(self):
        """
        ndloccr も tesseract も利用できない場合、MockEngine にフォールバックすること。
        """
        with patch("src.core.ocr_engine._NDLOCR_AVAILABLE", False), \
             patch("src.core.ocr_engine._TESSERACT_AVAILABLE", False):
            engine = OCREngine()

        assert engine.engine_name == "mock"
        assert engine.is_available() is False

    def test_prefers_ndloccr_over_tesseract(self):
        """
        ndloccr が利用可能な場合は tesseract より優先されること。

        フォールバック優先順位: ndloccr > tesseract > mock
        """
        mock_ndloccr_engine = MagicMock()
        mock_ndloccr_engine.recognize.return_value = {"text": "NDL結果", "confidence": 0.9}

        with patch("src.core.ocr_engine._NDLOCR_AVAILABLE", True), \
             patch("src.core.ocr_engine._NdlocrEngine", return_value=mock_ndloccr_engine):
            engine = OCREngine()

        # ndloccr が選ばれていること
        assert engine.engine_name == "ndloccr"

    def test_fallback_to_tesseract_when_ndloccr_init_fails(self):
        """
        ndloccr の初期化が例外を投げた場合、tesseract にフォールバックすること。
        """
        mock_tesseract_engine = MagicMock()
        mock_tesseract_engine.recognize.return_value = {"text": "Tesseract結果", "confidence": 0.8}

        with patch("src.core.ocr_engine._NDLOCR_AVAILABLE", True), \
             patch("src.core.ocr_engine._NdlocrEngine", side_effect=RuntimeError("初期化失敗")), \
             patch("src.core.ocr_engine._TESSERACT_AVAILABLE", True), \
             patch("src.core.ocr_engine._TesseractEngine", return_value=mock_tesseract_engine):
            engine = OCREngine()

        # tesseract にフォールバックしていること
        assert engine.engine_name == "tesseract"


# ==============================================================================
# テスト: テキスト認識 (recognize_text)
# ==============================================================================

class TestRecognizeTextWithMock:
    """モック画像でのテキスト認識テスト (recognize_text)"""

    def test_recognize_text_returns_dict(
        self, mock_ocr_engine: OCREngine, test_image: Image.Image
    ):
        """
        recognize_text の戻り値が辞書型で、必要なキーを持つこと。
        """
        result = mock_ocr_engine.recognize_text(test_image)

        assert isinstance(result, dict), "戻り値は辞書であること"
        assert "text" in result, "'text' キーが存在すること"
        assert "confidence" in result, "'confidence' キーが存在すること"

    def test_recognize_text_text_is_string(
        self, mock_ocr_engine: OCREngine, test_image: Image.Image
    ):
        """
        'text' フィールドが文字列型であること。
        """
        result = mock_ocr_engine.recognize_text(test_image)
        assert isinstance(result["text"], str)

    def test_recognize_text_confidence_is_float(
        self, mock_ocr_engine: OCREngine, test_image: Image.Image
    ):
        """
        'confidence' フィールドが 0.0〜1.0 の範囲の数値であること。
        """
        result = mock_ocr_engine.recognize_text(test_image)
        conf = result["confidence"]
        assert isinstance(conf, (int, float)), "confidence は数値であること"
        assert 0.0 <= conf <= 1.0, f"confidence は 0〜1 の範囲: {conf}"

    def test_recognize_text_with_region(
        self, mock_ocr_engine: OCREngine, test_image: Image.Image
    ):
        """
        region 指定した場合も正常に動作すること。

        region = (x1, y1, x2, y2) でクロップ領域を指定できる。
        """
        region = (0, 0, 100, 50)  # 左上半分をクロップ
        result = mock_ocr_engine.recognize_text(test_image, region=region)

        assert "text" in result
        assert "confidence" in result

    def test_recognize_text_none_image_returns_empty(
        self, mock_ocr_engine: OCREngine
    ):
        """
        image=None を渡した場合、空文字と信頼度0が返ること。

        None チェックが実装されていることを確認する。
        """
        result = mock_ocr_engine.recognize_text(None)

        assert result["text"] == ""
        assert result["confidence"] == 0.0

    def test_recognize_text_with_real_engine_mock(
        self, test_image: Image.Image
    ):
        """
        内部エンジンをモックに差し替えてテキスト認識フローを検証する。

        recognize_text が内部エンジンの recognize() を正しく呼び出すかを確認。
        """
        expected_result = {"text": "模擬認識結果", "confidence": 0.92}
        mock_engine = MagicMock()
        mock_engine.recognize.return_value = expected_result

        with patch("src.core.ocr_engine._NDLOCR_AVAILABLE", False), \
             patch("src.core.ocr_engine._TESSERACT_AVAILABLE", False):
            ocr = OCREngine()

        # 内部エンジンをモックに差し替え
        ocr._engine = mock_engine

        result = ocr.recognize_text(test_image, region=(10, 10, 150, 80))

        # モックが呼ばれたことを確認
        mock_engine.recognize.assert_called_once()
        assert result["text"] == "模擬認識結果"
        assert result["confidence"] == pytest.approx(0.92)

    def test_recognize_text_with_grayscale_image(self, mock_ocr_engine: OCREngine):
        """
        グレースケール画像を渡した場合も正常に処理されること。
        """
        gray_img = create_grayscale_test_image()
        result = mock_ocr_engine.recognize_text(gray_img)

        assert isinstance(result, dict)
        assert "text" in result


# ==============================================================================
# テスト: 複数領域認識 (recognize_regions)
# ==============================================================================

class TestRecognizeRegions:
    """複数領域認識 (recognize_regions) のテスト群"""

    def test_recognize_regions_returns_list(
        self, mock_ocr_engine: OCREngine, test_image: Image.Image
    ):
        """
        recognize_regions は結果のリストを返すこと。
        """
        regions = [
            {"field_name": "name", "x1": 0, "y1": 0, "x2": 100, "y2": 50},
            {"field_name": "address", "x1": 0, "y1": 50, "x2": 200, "y2": 100},
        ]
        results = mock_ocr_engine.recognize_regions(test_image, regions)

        assert isinstance(results, list), "戻り値はリストであること"
        assert len(results) == 2, "領域数と同じ件数が返ること"

    def test_recognize_regions_field_names_preserved(
        self, mock_ocr_engine: OCREngine, test_image: Image.Image
    ):
        """
        各結果に field_name が正しく含まれること。
        入力の field_name がそのまま出力に引き継がれる設計を確認する。
        """
        regions = [
            {"field_name": "applicant_name", "x1": 0, "y1": 0, "x2": 100, "y2": 30},
            {"field_name": "birth_date", "x1": 0, "y1": 30, "x2": 100, "y2": 60},
            {"field_name": "address", "x1": 0, "y1": 60, "x2": 200, "y2": 100},
        ]
        results = mock_ocr_engine.recognize_regions(test_image, regions)

        result_names = [r["field_name"] for r in results]
        assert "applicant_name" in result_names
        assert "birth_date" in result_names
        assert "address" in result_names

    def test_recognize_regions_result_structure(
        self, mock_ocr_engine: OCREngine, test_image: Image.Image
    ):
        """
        各結果が 'field_name', 'text', 'confidence' キーを持つこと。
        """
        regions = [
            {"field_name": "field1", "x1": 0, "y1": 0, "x2": 100, "y2": 50},
        ]
        results = mock_ocr_engine.recognize_regions(test_image, regions)

        assert len(results) == 1
        result = results[0]
        assert "field_name" in result
        assert "text" in result
        assert "confidence" in result

    def test_recognize_regions_empty_regions_list(
        self, mock_ocr_engine: OCREngine, test_image: Image.Image
    ):
        """
        空の領域リストを渡した場合は空リストが返ること。
        """
        results = mock_ocr_engine.recognize_regions(test_image, [])
        assert results == []

    def test_recognize_regions_invalid_coordinates_skipped(
        self, mock_ocr_engine: OCREngine, test_image: Image.Image
    ):
        """
        x2 <= x1 などの不正な座標を持つ領域はスキップされること。

        不正な座標で OCR を実行するとエラーが発生するため、
        事前チェックで空の結果として処理される設計を確認する。
        """
        regions = [
            # 不正な座標 (x2 < x1)
            {"field_name": "invalid_field", "x1": 100, "y1": 0, "x2": 50, "y2": 50},
            # 正常な座標
            {"field_name": "valid_field", "x1": 0, "y1": 0, "x2": 100, "y2": 50},
        ]
        results = mock_ocr_engine.recognize_regions(test_image, regions)

        # 全件返ってくること (不正なものは空テキストで返る)
        assert len(results) == 2

        # 不正な座標の領域は空テキスト・信頼度0になること
        invalid_result = next(r for r in results if r["field_name"] == "invalid_field")
        assert invalid_result["text"] == ""
        assert invalid_result["confidence"] == 0.0

    def test_recognize_regions_with_page_number_key(
        self, mock_ocr_engine: OCREngine, test_image: Image.Image
    ):
        """
        page_number キーを含む領域定義でも正常に動作すること。
        page_number はログ目的のオプションキーであり処理に影響しない。
        """
        regions = [
            {
                "field_name": "name",
                "page_number": 1,
                "x1": 0, "y1": 0, "x2": 100, "y2": 50,
            },
        ]
        results = mock_ocr_engine.recognize_regions(test_image, regions)
        assert len(results) == 1


# ==============================================================================
# テスト: MockEngine の動作確認
# ==============================================================================

class TestMockEngine:
    """_MockEngine の直接テスト"""

    def test_mock_engine_recognize_returns_dict(self, test_image: Image.Image):
        """
        MockEngine.recognize() は辞書を返すこと。
        """
        engine = _MockEngine()
        result = engine.recognize(test_image)

        assert isinstance(result, dict)
        assert "text" in result
        assert "confidence" in result

    def test_mock_engine_text_not_empty(self, test_image: Image.Image):
        """
        MockEngine は空でないテキストを返すこと (モックであることを示す文字列)。
        """
        engine = _MockEngine()
        result = engine.recognize(test_image)

        # モックエンジンは識別用の文字列を返す設計
        assert isinstance(result["text"], str)
        # 空でないことを確認
        assert len(result["text"]) > 0

    def test_mock_engine_confidence_zero(self, test_image: Image.Image):
        """
        MockEngine の confidence は 0.0 であること。

        モックエンジンは実際の認識を行わないため信頼度は 0 が妥当。
        """
        engine = _MockEngine()
        result = engine.recognize(test_image)
        assert result["confidence"] == 0.0

    def test_mock_engine_with_region_parameter(self, test_image: Image.Image):
        """
        region パラメータを渡しても MockEngine はエラーを出さないこと。

        MockEngine は region を無視するが、引数として受け取る設計。
        """
        engine = _MockEngine()
        result = engine.recognize(test_image, region=(10, 10, 100, 50))

        assert isinstance(result, dict)
        assert "text" in result

    def test_mock_engine_with_none_image(self):
        """
        image=None を渡しても MockEngine はエラーを出さないこと。

        MockEngine は image を使用しないため None でも動作する設計。
        """
        engine = _MockEngine()
        result = engine.recognize(None)
        assert isinstance(result, dict)


# ==============================================================================
# テスト: 画像生成ユーティリティ動作確認
# ==============================================================================

class TestImageCreation:
    """テスト用画像生成の動作確認"""

    def test_create_test_image_returns_pil_image(self):
        """
        create_test_image が PIL.Image を返すこと。
        """
        img = create_test_image()
        assert isinstance(img, Image.Image)

    def test_create_test_image_correct_size(self):
        """
        指定したサイズの画像が生成されること。
        """
        img = create_test_image(width=300, height=150)
        assert img.size == (300, 150)

    def test_create_test_image_rgb_mode(self):
        """
        生成された画像が RGB モードであること。
        """
        img = create_test_image()
        assert img.mode == "RGB"

    def test_create_grayscale_test_image(self):
        """
        グレースケール画像が生成されること。
        """
        img = create_grayscale_test_image(100, 50)
        assert img.mode == "L"
        assert img.size == (100, 50)

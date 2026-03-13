"""
test_database.py - DatabaseManager のユニットテスト

担当: 中村 美希 (Miki Nakamura) - QAエンジニア
作成日: 2026-03-13

テスト方針:
  - テスト毎に一時ディレクトリを使い、テスト間の状態汚染を防ぐ。
  - tmp_path フィクスチャ (pytest 組み込み) でOS標準の一時ディレクトリを利用する。
  - 外部依存は一切なし (SQLite は標準ライブラリのため)。
  - カスケード削除・外部キー制約など DB 設計の重要な動作を重点的に検証する。

カバレッジ目標: DatabaseManager の主要メソッドを 90% 以上カバーする
"""

import sys
import os

# プロジェクトルートをパスに追加 (テスト実行時の import 解決)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path
from src.core.database import DatabaseManager


# ==============================================================================
# フィクスチャ定義
# ==============================================================================

@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    """
    テスト用の一時 SQLite DB を作成して DatabaseManager を返す。

    tmp_path は pytest の組み込みフィクスチャで、
    テスト終了後に自動クリーンアップされる。
    毎テスト関数ごとに新しいインスタンスが生成されるため、
    テスト間の状態汚染がない。

    Args:
        tmp_path: pytest が提供するテスト用一時ディレクトリ

    Yields:
        DatabaseManager: 初期化済みのテスト用 DB マネージャー
    """
    db_path = tmp_path / "test_ocr.db"
    manager = DatabaseManager(db_path=str(db_path))
    manager.initialize_db()
    return manager


@pytest.fixture
def sample_form(db: DatabaseManager) -> int:
    """
    テスト用の様式を1件作成して ID を返す。

    複数テストで共通して使用するサンプルデータのフィクスチャ。
    """
    form_id = db.create_form(
        name="住民票申請書",
        description="住民票の写し交付申請書のOCRテンプレート"
    )
    return form_id


@pytest.fixture
def sample_field_data() -> dict:
    """
    テスト用のフィールド定義データを返す。

    座標は A4 縦を想定した典型的な値を設定している。
    """
    return {
        "field_name": "applicant_name",
        "field_label": "申請者氏名",
        "page_number": 1,
        "x1": 100.0,
        "y1": 200.0,
        "x2": 400.0,
        "y2": 240.0,
        "field_type": "text",
        "order_index": 0,
    }


# ==============================================================================
# テスト: 様式 (forms) テーブルの CRUD
# ==============================================================================

class TestCreateForm:
    """様式作成 (create_form) のテスト群"""

    def test_create_form_returns_positive_id(self, db: DatabaseManager):
        """
        create_form は正の整数 ID を返すこと。
        SQLite AUTOINCREMENT により 1 から始まる。
        """
        form_id = db.create_form(name="テスト様式")
        assert isinstance(form_id, int), "戻り値は整数でなければならない"
        assert form_id > 0, "ID は正の整数でなければならない"

    def test_create_form_stores_name(self, db: DatabaseManager):
        """
        create_form で保存した様式名が get_form で取得できること。
        """
        form_id = db.create_form(name="住民票申請書", description="テスト説明")
        retrieved = db.get_form(form_id)

        assert retrieved is not None, "作成した様式が取得できること"
        assert retrieved["name"] == "住民票申請書"
        assert retrieved["description"] == "テスト説明"

    def test_create_form_sets_timestamps(self, db: DatabaseManager):
        """
        create_form は created_at / updated_at を ISO8601 形式で設定すること。
        """
        form_id = db.create_form(name="タイムスタンプテスト")
        form = db.get_form(form_id)

        assert form is not None
        assert form["created_at"] != "", "created_at が設定されること"
        assert form["updated_at"] != "", "updated_at が設定されること"
        # ISO8601 の簡易チェック: 'YYYY-MM-DD' の形式か
        assert "T" in form["created_at"] or "-" in form["created_at"], \
            "タイムスタンプは ISO8601 形式であること"

    def test_create_multiple_forms_unique_ids(self, db: DatabaseManager):
        """
        複数の様式を作成した場合、それぞれ異なる ID を持つこと。
        """
        id1 = db.create_form(name="様式A")
        id2 = db.create_form(name="様式B")
        id3 = db.create_form(name="様式C")

        assert id1 != id2, "様式A と様式B の ID は異なること"
        assert id2 != id3, "様式B と様式C の ID は異なること"
        assert id1 != id3, "様式A と様式C の ID は異なること"

    def test_create_form_empty_description(self, db: DatabaseManager):
        """
        description を省略した場合も正常に作成できること。
        デフォルト値として空文字が設定されること。
        """
        form_id = db.create_form(name="説明なし様式")
        form = db.get_form(form_id)

        assert form is not None
        # description のデフォルトは空文字 or NULL (どちらでも問題なし)
        assert form.get("description", "") in ("", None)


class TestListForms:
    """様式一覧取得 (list_forms) のテスト群"""

    def test_list_forms_empty_initially(self, db: DatabaseManager):
        """
        初期状態では様式が0件であること。
        """
        forms = db.list_forms()
        assert forms == [], "初期状態では様式が存在しないこと"

    def test_list_forms_returns_all(self, db: DatabaseManager):
        """
        作成した全様式が一覧に含まれること。
        """
        db.create_form(name="様式1")
        db.create_form(name="様式2")
        db.create_form(name="様式3")

        forms = db.list_forms()
        assert len(forms) == 3, "3件の様式がすべて返されること"

    def test_list_forms_returns_dict_list(self, db: DatabaseManager):
        """
        list_forms の戻り値が辞書のリストであること。
        各辞書に必要なキーが含まれていること。
        """
        db.create_form(name="キー確認様式")
        forms = db.list_forms()

        assert len(forms) == 1
        form = forms[0]
        required_keys = ["id", "name", "description", "created_at", "updated_at"]
        for key in required_keys:
            assert key in form, f"'{key}' キーが存在すること"

    def test_list_forms_ordered_by_updated_at_desc(self, db: DatabaseManager):
        """
        list_forms は updated_at の降順 (新しいものが先頭) で返すこと。
        """
        import time
        id1 = db.create_form(name="古い様式")
        time.sleep(0.01)  # タイムスタンプが異なるよう微小な遅延を入れる
        id2 = db.create_form(name="新しい様式")

        forms = db.list_forms()
        # updated_at 降順なので新しい様式が先頭
        assert forms[0]["name"] == "新しい様式", "新しい様式が先頭に来ること"
        assert forms[1]["name"] == "古い様式"


class TestDeleteForm:
    """様式削除 (delete_form) のテスト群"""

    def test_delete_form_returns_true(self, db: DatabaseManager, sample_form: int):
        """
        存在する様式の削除は True を返すこと。
        """
        result = db.delete_form(sample_form)
        assert result is True

    def test_delete_form_removes_from_db(self, db: DatabaseManager, sample_form: int):
        """
        削除後は get_form で None が返ること。
        """
        db.delete_form(sample_form)
        retrieved = db.get_form(sample_form)
        assert retrieved is None, "削除後は様式が取得できないこと"

    def test_delete_nonexistent_form_returns_false(self, db: DatabaseManager):
        """
        存在しない ID を削除しようとすると False を返すこと。
        """
        result = db.delete_form(99999)
        assert result is False

    def test_delete_form_cascades_to_fields(
        self, db: DatabaseManager, sample_form: int
    ):
        """
        様式削除時に、紐づくフィールド定義も自動削除されること (CASCADE)。

        外部キー制約 ON DELETE CASCADE が正しく機能しているかを確認する。
        これが機能しないと孤立したフィールドレコードが残り、
        DB の整合性が崩れる。
        """
        # フィールドを追加する
        field_data = {
            "field_name": "test_field",
            "field_label": "テストフィールド",
            "page_number": 1,
            "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 50.0,
            "field_type": "text",
            "order_index": 0,
        }
        db.save_form_field(sample_form, field_data)
        fields_before = db.get_form_fields(sample_form)
        assert len(fields_before) == 1, "フィールドが1件作成されていること"

        # 様式を削除する
        db.delete_form(sample_form)

        # フィールドも削除されていること
        fields_after = db.get_form_fields(sample_form)
        assert len(fields_after) == 0, "カスケード削除でフィールドも消えること"

    def test_delete_form_cascades_to_ocr_results(
        self, db: DatabaseManager, sample_form: int
    ):
        """
        様式削除時に、紐づくOCR結果も自動削除されること (CASCADE)。
        """
        # OCR 結果を保存する
        result_id = db.save_ocr_result(
            form_id=sample_form,
            source_file="test.pdf",
            fields=[
                {"field_id": None, "field_name": "name", "recognized_text": "テスト太郎", "confidence": 0.9}
            ],
        )

        # 様式を削除する
        db.delete_form(sample_form)

        # OCR 結果も削除されていること
        result = db.get_ocr_result_by_id(result_id)
        assert result is None, "カスケード削除でOCR結果も消えること"


# ==============================================================================
# テスト: フィールド定義 (form_fields) テーブルの CRUD
# ==============================================================================

class TestSaveFormField:
    """フィールド保存 (save_form_field) のテスト群"""

    def test_save_new_field_returns_positive_id(
        self, db: DatabaseManager, sample_form: int, sample_field_data: dict
    ):
        """
        新規フィールドの保存は正の整数 ID を返すこと。
        """
        field_id = db.save_form_field(sample_form, sample_field_data)
        assert isinstance(field_id, int)
        assert field_id > 0

    def test_save_field_stores_all_attributes(
        self, db: DatabaseManager, sample_form: int, sample_field_data: dict
    ):
        """
        保存したフィールドのすべての属性が取得時に一致すること。
        """
        field_id = db.save_form_field(sample_form, sample_field_data)
        fields = db.get_form_fields(sample_form)

        assert len(fields) == 1
        field = fields[0]

        assert field["field_name"] == "applicant_name"
        assert field["field_label"] == "申請者氏名"
        assert field["page_number"] == 1
        assert field["x1"] == pytest.approx(100.0)
        assert field["y1"] == pytest.approx(200.0)
        assert field["x2"] == pytest.approx(400.0)
        assert field["y2"] == pytest.approx(240.0)
        assert field["field_type"] == "text"
        assert field["order_index"] == 0

    def test_save_field_update_existing(
        self, db: DatabaseManager, sample_form: int, sample_field_data: dict
    ):
        """
        field_data に 'id' を含めて呼び出すと既存フィールドが更新されること。
        """
        # 新規作成
        field_id = db.save_form_field(sample_form, sample_field_data)

        # 更新 (座標を変更)
        updated_data = dict(sample_field_data)
        updated_data["id"] = field_id
        updated_data["x1"] = 150.0
        updated_data["x2"] = 450.0
        updated_data["field_label"] = "申請者名（更新後）"

        returned_id = db.save_form_field(sample_form, updated_data)
        assert returned_id == field_id, "更新時は同じ ID が返ること"

        # 更新内容の確認
        fields = db.get_form_fields(sample_form)
        assert len(fields) == 1, "更新後もフィールド数は変わらない"
        assert fields[0]["x1"] == pytest.approx(150.0)
        assert fields[0]["field_label"] == "申請者名（更新後）"

    def test_save_multiple_fields(
        self, db: DatabaseManager, sample_form: int
    ):
        """
        複数フィールドを保存した場合、すべて取得できること。
        """
        for i in range(5):
            db.save_form_field(sample_form, {
                "field_name": f"field_{i}",
                "field_label": f"フィールド{i}",
                "page_number": 1,
                "x1": float(i * 100),
                "y1": 100.0,
                "x2": float(i * 100 + 80),
                "y2": 130.0,
                "field_type": "text",
                "order_index": i,
            })

        fields = db.get_form_fields(sample_form)
        assert len(fields) == 5, "5件のフィールドがすべて取得できること"


class TestGetFormFields:
    """フィールド取得 (get_form_fields) のテスト群"""

    def test_get_form_fields_empty(self, db: DatabaseManager, sample_form: int):
        """
        フィールドが未登録の様式では空リストが返ること。
        """
        fields = db.get_form_fields(sample_form)
        assert fields == []

    def test_get_form_fields_ordered_by_page_and_index(
        self, db: DatabaseManager, sample_form: int
    ):
        """
        get_form_fields は page_number 昇順、order_index 昇順で返すこと。

        CSV 出力の列順序が正しくなるために重要な仕様。
        """
        # 意図的に逆順で登録する
        for page, order in [(2, 1), (1, 2), (1, 0), (2, 0)]:
            db.save_form_field(sample_form, {
                "field_name": f"p{page}_o{order}",
                "field_label": f"p{page}_o{order}",
                "page_number": page,
                "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 10.0,
                "field_type": "text",
                "order_index": order,
            })

        fields = db.get_form_fields(sample_form)
        assert len(fields) == 4

        # ソート確認
        assert fields[0]["field_name"] == "p1_o0"
        assert fields[1]["field_name"] == "p1_o2"
        assert fields[2]["field_name"] == "p2_o0"
        assert fields[3]["field_name"] == "p2_o1"

    def test_get_form_fields_isolation(self, db: DatabaseManager):
        """
        異なる様式のフィールドが混入しないこと。

        form_id による分離が正しく機能しているかを確認する。
        """
        form_a = db.create_form(name="様式A")
        form_b = db.create_form(name="様式B")

        db.save_form_field(form_a, {
            "field_name": "field_a", "field_label": "A",
            "page_number": 1, "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 10.0,
            "field_type": "text", "order_index": 0,
        })
        db.save_form_field(form_b, {
            "field_name": "field_b", "field_label": "B",
            "page_number": 1, "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 10.0,
            "field_type": "text", "order_index": 0,
        })

        fields_a = db.get_form_fields(form_a)
        fields_b = db.get_form_fields(form_b)

        assert len(fields_a) == 1
        assert fields_a[0]["field_name"] == "field_a"
        assert len(fields_b) == 1
        assert fields_b[0]["field_name"] == "field_b"


# ==============================================================================
# テスト: OCR 結果保存 (ocr_results / ocr_result_fields)
# ==============================================================================

class TestSaveOcrResult:
    """OCR 結果保存 (save_ocr_result) のテスト群"""

    def test_save_ocr_result_returns_positive_id(
        self, db: DatabaseManager, sample_form: int
    ):
        """
        save_ocr_result は正の整数 ID を返すこと。
        """
        result_id = db.save_ocr_result(
            form_id=sample_form,
            source_file="/tmp/test.pdf",
            fields=[],
        )
        assert isinstance(result_id, int)
        assert result_id > 0

    def test_save_ocr_result_stores_fields(
        self, db: DatabaseManager, sample_form: int
    ):
        """
        フィールドの認識テキストが正しく保存されること。
        """
        fields = [
            {
                "field_id": None,
                "field_name": "applicant_name",
                "recognized_text": "山田 太郎",
                "confidence": 0.95,
            },
            {
                "field_id": None,
                "field_name": "address",
                "recognized_text": "東京都新宿区1-1-1",
                "confidence": 0.88,
            },
        ]

        result_id = db.save_ocr_result(
            form_id=sample_form,
            source_file="申請書.pdf",
            fields=fields,
        )

        # 保存内容の検証
        result = db.get_ocr_result_by_id(result_id)
        assert result is not None
        assert result["source_file"] == "申請書.pdf"
        assert result["status"] == "success"
        assert len(result["fields"]) == 2

        # フィールドの認識テキストを確認
        field_map = {f["field_name"]: f for f in result["fields"]}
        assert field_map["applicant_name"]["recognized_text"] == "山田 太郎"
        assert field_map["address"]["recognized_text"] == "東京都新宿区1-1-1"
        assert field_map["applicant_name"]["confidence"] == pytest.approx(0.95)

    def test_save_ocr_result_with_error_status(
        self, db: DatabaseManager, sample_form: int
    ):
        """
        status='error' でも正常に保存できること。
        処理失敗の記録も重要なデータとして残す設計。
        """
        result_id = db.save_ocr_result(
            form_id=sample_form,
            source_file="broken.pdf",
            fields=[],
            status="error",
        )
        result = db.get_ocr_result_by_id(result_id)
        assert result is not None
        assert result["status"] == "error"

    def test_save_ocr_result_sets_processed_at(
        self, db: DatabaseManager, sample_form: int
    ):
        """
        processed_at が自動設定されること。
        """
        result_id = db.save_ocr_result(
            form_id=sample_form,
            source_file="test.pdf",
            fields=[],
        )
        result = db.get_ocr_result_by_id(result_id)
        assert result is not None
        assert result["processed_at"] != "", "処理日時が設定されること"

    def test_get_ocr_results_returns_list(
        self, db: DatabaseManager, sample_form: int
    ):
        """
        get_ocr_results で複数結果が取得できること。
        """
        db.save_ocr_result(
            form_id=sample_form,
            source_file="file1.pdf",
            fields=[{"field_id": None, "field_name": "a", "recognized_text": "A", "confidence": 0.9}],
        )
        db.save_ocr_result(
            form_id=sample_form,
            source_file="file2.pdf",
            fields=[{"field_id": None, "field_name": "b", "recognized_text": "B", "confidence": 0.8}],
        )

        results = db.get_ocr_results(sample_form)
        assert len(results) == 2, "2件のOCR結果が取得できること"

    def test_get_ocr_results_by_ids(
        self, db: DatabaseManager, sample_form: int
    ):
        """
        get_ocr_results_by_ids で指定した ID のみ取得できること。
        """
        id1 = db.save_ocr_result(
            form_id=sample_form, source_file="a.pdf", fields=[],
        )
        id2 = db.save_ocr_result(
            form_id=sample_form, source_file="b.pdf", fields=[],
        )
        id3 = db.save_ocr_result(
            form_id=sample_form, source_file="c.pdf", fields=[],
        )

        # id1 と id3 のみ取得
        results = db.get_ocr_results_by_ids([id1, id3])
        assert len(results) == 2
        source_files = {r["source_file"] for r in results}
        assert source_files == {"a.pdf", "c.pdf"}

    def test_get_ocr_results_by_ids_empty_list(
        self, db: DatabaseManager
    ):
        """
        空リストを渡した場合は空リストが返ること。
        """
        results = db.get_ocr_results_by_ids([])
        assert results == []


# ==============================================================================
# テスト: データベース初期化
# ==============================================================================

class TestInitializeDb:
    """データベース初期化 (initialize_db) のテスト群"""

    def test_initialize_db_idempotent(self, tmp_path: Path):
        """
        initialize_db を複数回呼んでもエラーにならないこと (べき等性)。

        IF NOT EXISTS を使っているため重複実行は安全でなければならない。
        """
        db_path = str(tmp_path / "idempotent_test.db")
        manager = DatabaseManager(db_path=db_path)

        # 2回呼んでもエラーが出ないこと
        manager.initialize_db()
        manager.initialize_db()  # 2回目はスキップされるはず

        # 正常に操作できること
        form_id = manager.create_form(name="べき等テスト")
        assert form_id > 0

    def test_initialize_creates_db_file(self, tmp_path: Path):
        """
        initialize_db 後にデータベースファイルが作成されること。
        """
        db_path = tmp_path / "created_db.db"
        assert not db_path.exists(), "事前にファイルが存在しないこと"

        manager = DatabaseManager(db_path=str(db_path))
        manager.initialize_db()

        assert db_path.exists(), "initialize_db 後にファイルが作成されること"

    def test_initialize_creates_parent_directory(self, tmp_path: Path):
        """
        親ディレクトリが存在しない場合、自動作成されること。
        """
        # 存在しないサブディレクトリ配下にDBパスを指定
        db_path = tmp_path / "subdir" / "nested" / "test.db"
        assert not db_path.parent.exists()

        manager = DatabaseManager(db_path=str(db_path))
        manager.initialize_db()

        assert db_path.exists(), "ネストされたディレクトリも自動作成されること"

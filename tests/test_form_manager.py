"""
test_form_manager.py - FormManager のユニットテスト

担当: 中村 美希 (Miki Nakamura) - QAエンジニア
作成日: 2026-03-13

テスト方針:
  - FormManager は DatabaseManager のラッパーであるため、
    実際の SQLite DB (tmp_path で生成した一時 DB) を使って結合的にテストする。
    これにより DB 連携も含めて一貫した動作を確認できる。
  - バリデーション (ValueError) のテストを重点的に行う。
    FormManager の主な責務はバリデーションとビジネスルールの適用であるため。
  - 削除・カスケード動作は test_database.py でカバーしているため、
    ここでは FormManager 固有のロジックに集中する。

カバレッジ対象:
  - FormManager.create_form() (バリデーション含む)
  - FormManager.list_forms()
  - FormManager.get_form_with_fields()
  - FormManager.add_field() (バリデーション含む)
  - FormManager.delete_form()
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path

from src.core.database import DatabaseManager
from src.core.form_manager import FormManager


# ==============================================================================
# フィクスチャ定義
# ==============================================================================

@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    """
    テスト用の一時 SQLite DB を初期化して返す。
    """
    db_path = str(tmp_path / "form_manager_test.db")
    manager = DatabaseManager(db_path=db_path)
    manager.initialize_db()
    return manager


@pytest.fixture
def fm(db: DatabaseManager) -> FormManager:
    """
    テスト用の FormManager インスタンスを返す。

    実際の DatabaseManager を渡すことで、
    DB 操作を含めた結合的なテストが可能になる。
    """
    return FormManager(db_manager=db)


@pytest.fixture
def valid_field_data() -> dict:
    """
    バリデーションを通過する正常なフィールドデータ。
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
# テスト: 様式作成 (create_form)
# ==============================================================================

class TestCreateForm:
    """FormManager.create_form() のテスト群"""

    def test_create_form_success(self, fm: FormManager):
        """
        正常な様式名で作成成功し、正の ID が返ること。
        """
        form_id = fm.create_form(name="住民票申請書")
        assert isinstance(form_id, int)
        assert form_id > 0

    def test_create_form_with_description(self, fm: FormManager):
        """
        説明付きで様式を作成できること。
        """
        form_id = fm.create_form(
            name="転出届",
            description="転出届提出用のOCRテンプレートです"
        )
        # 作成後に get_form で取得して確認
        form = fm.get_form(form_id)
        assert form is not None
        assert form["description"] == "転出届提出用のOCRテンプレートです"

    def test_create_form_empty_name_raises_value_error(self, fm: FormManager):
        """
        空文字の様式名は ValueError を発生させること。

        DB に空名の様式が作成されることを防ぐバリデーション。
        """
        with pytest.raises(ValueError, match="空にできません"):
            fm.create_form(name="")

    def test_create_form_whitespace_only_name_raises_value_error(
        self, fm: FormManager
    ):
        """
        空白文字のみの様式名は ValueError を発生させること。

        空白を名前として登録することで UI が見にくくなるのを防ぐ。
        """
        with pytest.raises(ValueError):
            fm.create_form(name="   ")

    def test_create_form_strips_whitespace_from_name(self, fm: FormManager):
        """
        様式名の前後の空白はトリムされて保存されること。

        ユーザーが誤って入力した空白による重複登録を防ぐ。
        """
        form_id = fm.create_form(name="  住民票申請書  ")
        form = fm.get_form(form_id)
        assert form is not None
        assert form["name"] == "住民票申請書", "前後の空白が除去されること"

    def test_create_form_japanese_name(self, fm: FormManager):
        """
        日本語の様式名が正しく保存されること。
        """
        japanese_name = "国民健康保険加入届出書（転入用）"
        form_id = fm.create_form(name=japanese_name)
        form = fm.get_form(form_id)
        assert form["name"] == japanese_name


# ==============================================================================
# テスト: 様式一覧 (list_forms)
# ==============================================================================

class TestListForms:
    """FormManager.list_forms() のテスト群"""

    def test_list_forms_empty(self, fm: FormManager):
        """
        様式が未登録の場合、空リストが返ること。
        """
        forms = fm.list_forms()
        assert forms == []

    def test_list_forms_returns_all_created(self, fm: FormManager):
        """
        作成した全様式が一覧に含まれること。
        """
        fm.create_form(name="様式A")
        fm.create_form(name="様式B")
        fm.create_form(name="様式C")

        forms = fm.list_forms()
        names = [f["name"] for f in forms]

        assert "様式A" in names
        assert "様式B" in names
        assert "様式C" in names
        assert len(forms) == 3

    def test_list_forms_returns_list_of_dicts(self, fm: FormManager):
        """
        list_forms の戻り値が辞書のリストであること。
        """
        fm.create_form(name="辞書確認テスト")
        forms = fm.list_forms()

        assert isinstance(forms, list)
        assert isinstance(forms[0], dict)

    def test_list_forms_contains_required_keys(self, fm: FormManager):
        """
        各様式データに必要なキーが含まれること。
        """
        fm.create_form(name="キーテスト")
        forms = fm.list_forms()

        form = forms[0]
        for key in ["id", "name", "description", "created_at", "updated_at"]:
            assert key in form, f"'{key}' が存在すること"


# ==============================================================================
# テスト: フィールド追加 (add_field)
# ==============================================================================

class TestAddField:
    """FormManager.add_field() のテスト群"""

    def test_add_field_success(
        self, fm: FormManager, valid_field_data: dict
    ):
        """
        正常なフィールドデータで追加成功し、正の ID が返ること。
        """
        form_id = fm.create_form(name="フィールドテスト様式")
        field_id = fm.add_field(form_id, valid_field_data)

        assert isinstance(field_id, int)
        assert field_id > 0

    def test_add_field_stored_in_db(
        self, fm: FormManager, valid_field_data: dict
    ):
        """
        追加したフィールドが get_fields で取得できること。
        """
        form_id = fm.create_form(name="フィールド保存テスト")
        fm.add_field(form_id, valid_field_data)

        fields = fm.get_fields(form_id)
        assert len(fields) == 1
        assert fields[0]["field_name"] == "applicant_name"

    def test_add_field_missing_field_name_raises(self, fm: FormManager):
        """
        field_name が空の場合、ValueError を発生させること。
        """
        form_id = fm.create_form(name="バリデーションテスト")

        invalid_data = {
            "field_name": "",  # 空文字 → エラー
            "field_label": "氏名",
            "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 50.0,
        }

        with pytest.raises(ValueError, match="field_name"):
            fm.add_field(form_id, invalid_data)

    def test_add_field_missing_field_label_raises(self, fm: FormManager):
        """
        field_label が空の場合、ValueError を発生させること。
        """
        form_id = fm.create_form(name="ラベルバリデーションテスト")

        invalid_data = {
            "field_name": "name",
            "field_label": "",  # 空文字 → エラー
            "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 50.0,
        }

        with pytest.raises(ValueError, match="field_label"):
            fm.add_field(form_id, invalid_data)

    def test_add_field_invalid_coordinates_raises(self, fm: FormManager):
        """
        x2 <= x1 の不正座標は ValueError を発生させること。

        不正な座標でフィールドを登録するとOCR処理でエラーが発生するため、
        登録時にブロックする。
        """
        form_id = fm.create_form(name="座標バリデーションテスト")

        invalid_data = {
            "field_name": "test",
            "field_label": "テスト",
            "x1": 200.0,
            "y1": 100.0,
            "x2": 100.0,  # x2 < x1 → 不正
            "y2": 200.0,
        }

        with pytest.raises(ValueError, match="座標"):
            fm.add_field(form_id, invalid_data)

    def test_add_field_invalid_y_coordinates_raises(self, fm: FormManager):
        """
        y2 <= y1 の不正座標も ValueError を発生させること。
        """
        form_id = fm.create_form(name="Y座標バリデーションテスト")

        invalid_data = {
            "field_name": "test",
            "field_label": "テスト",
            "x1": 0.0,
            "y1": 200.0,
            "x2": 100.0,
            "y2": 100.0,  # y2 < y1 → 不正
        }

        with pytest.raises(ValueError, match="座標"):
            fm.add_field(form_id, invalid_data)

    def test_add_multiple_fields(self, fm: FormManager):
        """
        複数フィールドを追加できること。
        """
        form_id = fm.create_form(name="複数フィールドテスト")

        for i in range(3):
            fm.add_field(form_id, {
                "field_name": f"field_{i}",
                "field_label": f"フィールド{i}",
                "x1": float(i * 100),
                "y1": 0.0,
                "x2": float(i * 100 + 80),
                "y2": 40.0,
                "order_index": i,
            })

        fields = fm.get_fields(form_id)
        assert len(fields) == 3


# ==============================================================================
# テスト: 様式+フィールド取得 (get_form_with_fields)
# ==============================================================================

class TestGetFormWithFields:
    """FormManager.get_form_with_fields() のテスト群"""

    def test_get_form_with_fields_returns_form_data(
        self, fm: FormManager, valid_field_data: dict
    ):
        """
        様式の基本情報が含まれること。
        """
        form_id = fm.create_form(name="住民票申請書", description="説明テキスト")
        result = fm.get_form_with_fields(form_id)

        assert result is not None
        assert result["id"] == form_id
        assert result["name"] == "住民票申請書"
        assert result["description"] == "説明テキスト"

    def test_get_form_with_fields_includes_fields_key(
        self, fm: FormManager, valid_field_data: dict
    ):
        """
        戻り値に 'fields' キーが含まれること。
        """
        form_id = fm.create_form(name="フィールドキーテスト")
        result = fm.get_form_with_fields(form_id)

        assert "fields" in result, "'fields' キーが存在すること"
        assert isinstance(result["fields"], list)

    def test_get_form_with_fields_no_fields(self, fm: FormManager):
        """
        フィールド未登録の様式でも 'fields' が空リストで返ること。
        """
        form_id = fm.create_form(name="フィールドなし様式")
        result = fm.get_form_with_fields(form_id)

        assert result["fields"] == []

    def test_get_form_with_fields_includes_all_fields(
        self, fm: FormManager
    ):
        """
        登録済みの全フィールドが 'fields' に含まれること。
        """
        form_id = fm.create_form(name="全フィールドテスト")

        field_names = ["name", "address", "phone", "email"]
        for name in field_names:
            fm.add_field(form_id, {
                "field_name": name,
                "field_label": name,
                "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 40.0,
            })

        result = fm.get_form_with_fields(form_id)
        retrieved_names = [f["field_name"] for f in result["fields"]]

        for name in field_names:
            assert name in retrieved_names

    def test_get_form_with_fields_nonexistent_returns_none(
        self, fm: FormManager
    ):
        """
        存在しない ID を指定した場合、None が返ること。
        """
        result = fm.get_form_with_fields(99999)
        assert result is None

    def test_get_form_with_fields_isolation(self, fm: FormManager):
        """
        他の様式のフィールドが混入しないこと。
        """
        form_a = fm.create_form(name="様式A")
        form_b = fm.create_form(name="様式B")

        fm.add_field(form_a, {
            "field_name": "field_a",
            "field_label": "A",
            "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 40.0,
        })
        fm.add_field(form_b, {
            "field_name": "field_b",
            "field_label": "B",
            "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 40.0,
        })

        result_a = fm.get_form_with_fields(form_a)
        assert len(result_a["fields"]) == 1
        assert result_a["fields"][0]["field_name"] == "field_a"

        result_b = fm.get_form_with_fields(form_b)
        assert len(result_b["fields"]) == 1
        assert result_b["fields"][0]["field_name"] == "field_b"


# ==============================================================================
# テスト: 様式削除 (delete_form)
# ==============================================================================

class TestDeleteForm:
    """FormManager.delete_form() のテスト群"""

    def test_delete_form_success(self, fm: FormManager):
        """
        存在する様式の削除が成功し、True が返ること。
        """
        form_id = fm.create_form(name="削除テスト")
        result = fm.delete_form(form_id)
        assert result is True

    def test_delete_form_not_found_in_list(self, fm: FormManager):
        """
        削除後は list_forms に表示されないこと。
        """
        form_id = fm.create_form(name="削除確認テスト")
        fm.delete_form(form_id)

        forms = fm.list_forms()
        ids = [f["id"] for f in forms]
        assert form_id not in ids

    def test_delete_form_returns_false_if_not_exists(
        self, fm: FormManager
    ):
        """
        存在しない ID の削除は False を返すこと。
        """
        result = fm.delete_form(99999)
        assert result is False

    def test_delete_form_fields_also_deleted(self, fm: FormManager):
        """
        様式削除後、フィールドも削除されること。

        FormManager 経由でも CASCADE 削除が機能することを確認。
        """
        form_id = fm.create_form(name="カスケードテスト")
        fm.add_field(form_id, {
            "field_name": "test",
            "field_label": "テスト",
            "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 40.0,
        })

        fm.delete_form(form_id)

        # get_fields は空リストを返すこと (form_id が存在しないため)
        fields = fm.get_fields(form_id)
        assert fields == []

    def test_delete_field_individually(self, fm: FormManager):
        """
        個別フィールドの削除が正常に動作すること。
        """
        form_id = fm.create_form(name="個別削除テスト")
        field_id = fm.add_field(form_id, {
            "field_name": "to_delete",
            "field_label": "削除対象",
            "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 40.0,
        })

        result = fm.delete_field(field_id)
        assert result is True

        fields = fm.get_fields(form_id)
        assert len(fields) == 0


# ==============================================================================
# テスト: 様式更新 (update_form)
# ==============================================================================

class TestUpdateForm:
    """FormManager.update_form() のテスト群 (linter が追加したメソッドも含む)"""

    def test_update_form_success(self, fm: FormManager):
        """
        様式名と説明の更新が成功すること。
        """
        form_id = fm.create_form(name="更新前様式名")
        result = fm.update_form(form_id, name="更新後様式名", description="新しい説明")

        assert result is True
        form = fm.get_form(form_id)
        assert form["name"] == "更新後様式名"
        assert form["description"] == "新しい説明"

    def test_update_form_empty_name_raises(self, fm: FormManager):
        """
        空文字の名前で更新しようとすると ValueError が発生すること。
        """
        form_id = fm.create_form(name="更新バリデーションテスト")

        with pytest.raises(ValueError):
            fm.update_form(form_id, name="")

    def test_update_form_nonexistent_returns_false(self, fm: FormManager):
        """
        存在しない ID の更新は False を返すこと。
        """
        result = fm.update_form(99999, name="存在しない様式")
        assert result is False

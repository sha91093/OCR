"""
form_manager.py - 様式管理モジュール

担当: 佐藤 愛子 (Aiko Sato)
作成日: 2026-03-13

DatabaseManagerを薄くラップして様式(フォーム)とフィールドの
CRUDオペレーションをビジネスロジック層で扱いやすいAPIとして提供する。

設計方針:
  - DatabaseManagerへの直接依存をこのクラスに集約し、
    UI層がDBを直接触らない構造にする。
  - バリデーションはこの層で実施することでDBへの不正データ投入を防ぐ。
"""

import logging
from typing import Any, Optional

from src.core.database import DatabaseManager

logger = logging.getLogger(__name__)


class FormManager:
    """
    様式（フォーム）とフィールド定義を管理するクラス。

    DatabaseManagerの上位レイヤーとして機能し、
    バリデーションを含む様式操作のAPIを提供する。

    Attributes:
        _db (DatabaseManager): 内部で使用するDBマネージャー
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        """
        FormManagerを初期化する。

        Args:
            db_manager: 初期化済みのDatabaseManagerインスタンス
        """
        self._db = db_manager
        logger.debug("FormManagerを初期化しました")

    # -------------------------------------------------------------------------
    # 様式 (forms) 操作
    # -------------------------------------------------------------------------

    def create_form(self, name: str, description: str = "") -> int:
        """
        新しい様式を作成する。

        Args:
            name:        様式名 (空文字不可)
            description: 様式の説明 (省略可)

        Returns:
            int: 作成された様式のID

        Raises:
            ValueError: nameが空文字の場合
        """
        if not name or not name.strip():
            raise ValueError("様式名は空にできません")

        form_id = self._db.create_form(name.strip(), description)
        logger.info(f"様式を作成しました: id={form_id}, name={name}")
        return form_id

    def list_forms(self) -> list[dict[str, Any]]:
        """
        全様式の一覧を取得する。

        Returns:
            list[dict]: 様式データのリスト (更新日時降順)
        """
        forms = self._db.list_forms()
        logger.debug(f"様式一覧取得: {len(forms)}件")
        return forms

    def get_form(self, form_id: int) -> Optional[dict[str, Any]]:
        """
        指定IDの様式を取得する。

        Args:
            form_id: 様式のID

        Returns:
            dict または None: 様式データ。存在しない場合はNone。
        """
        return self._db.get_form(form_id)

    def get_form_with_fields(self, form_id: int) -> Optional[dict[str, Any]]:
        """
        様式とその全フィールドをまとめて取得する。

        Args:
            form_id: 様式のID

        Returns:
            dict または None: 様式データ（'fields'キーにフィールドリストを含む）
        """
        form = self._db.get_form(form_id)
        if form is None:
            return None
        form["fields"] = self._db.get_form_fields(form_id)
        return form

    def delete_form(self, form_id: int) -> bool:
        """
        様式を削除する。

        関連するフィールド定義・OCR結果もカスケード削除される。

        Args:
            form_id: 削除対象の様式ID

        Returns:
            bool: 削除成功した場合True
        """
        result = self._db.delete_form(form_id)
        if result:
            logger.info(f"様式を削除しました: id={form_id}")
        else:
            logger.warning(f"削除対象の様式が見つかりません: id={form_id}")
        return result

    # -------------------------------------------------------------------------
    # フィールド定義 (form_fields) 操作
    # -------------------------------------------------------------------------

    def add_field(self, form_id: int, field_data: dict[str, Any]) -> int:
        """
        様式にフィールドを追加する。

        Args:
            form_id:    対象様式のID
            field_data: フィールド定義データ。必須キー:
                        - field_name (str): フィールド識別名
                        - field_label (str): 表示ラベル
                        - x1, y1, x2, y2 (float): 領域座標

        Returns:
            int: 追加されたフィールドのID

        Raises:
            ValueError: 必須キーが不足している場合、または座標が不正な場合
        """
        # 必須フィールドのバリデーション
        required_keys = ["field_name", "field_label"]
        for key in required_keys:
            if not field_data.get(key):
                raise ValueError(f"フィールドの '{key}' は必須です")

        # 座標の妥当性チェック
        x1 = field_data.get("x1", 0.0)
        y1 = field_data.get("y1", 0.0)
        x2 = field_data.get("x2", 0.0)
        y2 = field_data.get("y2", 0.0)

        if x2 <= x1 or y2 <= y1:
            raise ValueError(
                f"フィールド座標が不正です: "
                f"x1={x1}, y1={y1}, x2={x2}, y2={y2} "
                f"(x2 > x1 かつ y2 > y1 が必要です)"
            )

        field_id = self._db.save_form_field(form_id, field_data)
        logger.debug(
            f"フィールドを追加しました: form_id={form_id}, "
            f"field_id={field_id}, name={field_data.get('field_name')}"
        )
        return field_id

    def get_fields(self, form_id: int) -> list[dict[str, Any]]:
        """
        様式のフィールド一覧を取得する。

        Args:
            form_id: 様式のID

        Returns:
            list[dict]: フィールドデータのリスト (page_number, order_index 昇順)
        """
        return self._db.get_form_fields(form_id)

    def update_field(self, form_id: int, field_data: dict[str, Any]) -> int:
        """
        フィールド定義を更新する。

        Args:
            form_id:    対象様式のID
            field_data: 更新するフィールドデータ ('id'キーが必須)

        Returns:
            int: 更新されたフィールドのID

        Raises:
            ValueError: field_dataに'id'が含まれていない場合
        """
        if "id" not in field_data:
            raise ValueError("フィールドの更新には 'id' キーが必要です")
        return self._db.save_form_field(form_id, field_data)

    def delete_field(self, field_id: int) -> bool:
        """
        フィールドを削除する。

        Args:
            field_id: 削除対象のフィールドID

        Returns:
            bool: 削除成功した場合True
        """
        return self._db.delete_form_field(field_id)

    # -------------------------------------------------------------------------
    # 追加メソッド (インターフェース拡張)
    # -------------------------------------------------------------------------

    def update_form(self, form_id: int, name: str, description: str = "") -> bool:
        """
        様式の基本情報を更新する。

        Args:
            form_id:     更新対象の様式ID
            name:        新しい様式名 (空文字不可)
            description: 新しい説明文

        Returns:
            bool: 更新成功した場合True

        Raises:
            ValueError: nameが空文字の場合
        """
        if not name or not name.strip():
            raise ValueError("様式名は空にできません")

        result = self._db.update_form(form_id, name.strip(), description)
        if result:
            logger.info(f"様式を更新しました: id={form_id}, name={name}")
        else:
            logger.warning(f"更新対象の様式が見つかりません: id={form_id}")
        return result

    def remove_field(self, field_id: int) -> bool:
        """
        フィールドを削除する (delete_field の別名)。

        OCRProcessorなど外部から統一的な名前でアクセスするためのエイリアス。

        Args:
            field_id: 削除対象のフィールドID

        Returns:
            bool: 削除成功した場合True
        """
        return self.delete_field(field_id)

    def reorder_fields(self, form_id: int, field_ids: list[int]) -> bool:
        """
        フィールドの表示順を変更する。

        field_ids リストの順番が新しい order_index になる。
        CSV出力の列順やUIでの表示順を変更する際に使用する。

        Args:
            form_id:   対象の様式ID
            field_ids: 新しい順序に並べたフィールドIDのリスト

        Returns:
            bool: 更新成功した場合True

        Raises:
            ValueError: field_idsが空の場合
        """
        if not field_ids:
            raise ValueError("フィールドIDリストが空です")

        with self._db._get_connection() as conn:
            for new_index, fid in enumerate(field_ids):
                conn.execute(
                    "UPDATE form_fields SET order_index = ? WHERE id = ? AND form_id = ?",
                    (new_index, fid, form_id),
                )
            conn.commit()

        logger.info(f"フィールド順を更新しました: form_id={form_id}, {len(field_ids)}件")
        return True

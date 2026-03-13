"""
database.py - SQLiteデータベース管理モジュール

担当: 佐藤 愛子 (Aiko Sato)
作成日: 2026-03-13

SQLiteを使って様式定義・OCR結果を永続化する。
低スペックPC環境でも動作するよう、外部DBサーバー不要のSQLiteを採用。
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    SQLiteデータベースの操作を管理するクラス。

    テーブル構成:
        - forms            : 様式（フォーム）の基本情報
        - form_fields      : 様式に紐づく読み取りフィールド定義
        - ocr_results      : OCR処理の実行結果サマリー
        - ocr_result_fields: OCR結果の各フィールド値

    Attributes:
        db_path (Path): SQLiteデータベースファイルのパス
    """

    def __init__(self, db_path: str = "ocr_tool.db") -> None:
        """
        データベースマネージャーを初期化する。

        Args:
            db_path: SQLiteデータベースファイルのパス。
                     デフォルトはカレントディレクトリの ocr_tool.db。
        """
        self.db_path = Path(db_path)
        # 親ディレクトリが存在しない場合は作成する
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"データベースパス: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """
        データベース接続を取得する。

        外部キー制約を有効化し、辞書形式でRowを返すよう設定する。

        Returns:
            sqlite3.Connection: 設定済みのDB接続オブジェクト
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # カラム名でアクセスできるようにする
        conn.execute("PRAGMA foreign_keys = ON")  # 外部キー制約を有効化
        conn.execute("PRAGMA journal_mode = WAL")  # 書き込み性能向上
        return conn

    def initialize_db(self) -> None:
        """
        必要なテーブルをすべて作成する。

        既にテーブルが存在する場合はスキップ (IF NOT EXISTS)。
        アプリ起動時に必ず呼び出すこと。
        """
        logger.info("データベースの初期化を開始します")

        create_forms_sql = """
        CREATE TABLE IF NOT EXISTS forms (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,           -- 様式名 (例: 住民票申請書)
            description TEXT    DEFAULT '',         -- 様式の説明・備考
            created_at  TEXT    NOT NULL,           -- 作成日時 (ISO8601形式)
            updated_at  TEXT    NOT NULL            -- 更新日時 (ISO8601形式)
        )
        """

        create_form_fields_sql = """
        CREATE TABLE IF NOT EXISTS form_fields (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            form_id     INTEGER NOT NULL,           -- 所属する様式のID
            field_name  TEXT    NOT NULL,           -- フィールド識別名 (英数字推奨)
            field_label TEXT    NOT NULL,           -- 表示ラベル (日本語可)
            page_number INTEGER NOT NULL DEFAULT 1, -- 対象ページ番号 (1始まり)
            x1          REAL    NOT NULL DEFAULT 0, -- 領域左上X座標 (px)
            y1          REAL    NOT NULL DEFAULT 0, -- 領域左上Y座標 (px)
            x2          REAL    NOT NULL DEFAULT 0, -- 領域右下X座標 (px)
            y2          REAL    NOT NULL DEFAULT 0, -- 領域右下Y座標 (px)
            field_type  TEXT    NOT NULL DEFAULT 'text', -- フィールド種別 (text/number/date)
            order_index INTEGER NOT NULL DEFAULT 0, -- CSV出力時の列順序
            FOREIGN KEY (form_id) REFERENCES forms(id) ON DELETE CASCADE
        )
        """

        create_ocr_results_sql = """
        CREATE TABLE IF NOT EXISTS ocr_results (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            form_id      INTEGER NOT NULL,          -- 使用した様式のID
            source_file  TEXT    NOT NULL,          -- 処理元ファイルのパス
            processed_at TEXT    NOT NULL,          -- 処理日時 (ISO8601形式)
            status       TEXT    NOT NULL DEFAULT 'success', -- 処理状態 (success/error/partial)
            FOREIGN KEY (form_id) REFERENCES forms(id) ON DELETE CASCADE
        )
        """

        create_ocr_result_fields_sql = """
        CREATE TABLE IF NOT EXISTS ocr_result_fields (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id       INTEGER NOT NULL,       -- 所属するOCR結果のID
            field_id        INTEGER,                -- 対応するフィールド定義のID (削除済みの場合はNULL)
            field_name      TEXT    NOT NULL,       -- フィールド識別名 (スナップショット)
            recognized_text TEXT    DEFAULT '',     -- OCRで認識されたテキスト
            confidence      REAL    DEFAULT 0.0,   -- 認識の信頼度 (0.0〜1.0)
            FOREIGN KEY (result_id) REFERENCES ocr_results(id) ON DELETE CASCADE
        )
        """

        # インデックス: 様式IDによる検索を高速化
        create_indexes_sql = [
            "CREATE INDEX IF NOT EXISTS idx_form_fields_form_id ON form_fields(form_id)",
            "CREATE INDEX IF NOT EXISTS idx_ocr_results_form_id ON ocr_results(form_id)",
            "CREATE INDEX IF NOT EXISTS idx_ocr_result_fields_result_id ON ocr_result_fields(result_id)",
        ]

        with self._get_connection() as conn:
            conn.execute(create_forms_sql)
            conn.execute(create_form_fields_sql)
            conn.execute(create_ocr_results_sql)
            conn.execute(create_ocr_result_fields_sql)
            for idx_sql in create_indexes_sql:
                conn.execute(idx_sql)
            conn.commit()

        logger.info("データベースの初期化が完了しました")

    # -------------------------------------------------------------------------
    # 様式 (forms) の操作
    # -------------------------------------------------------------------------

    def create_form(self, name: str, description: str = "") -> int:
        """
        新しい様式を作成する。

        Args:
            name:        様式名 (必須)
            description: 様式の説明・備考 (省略可)

        Returns:
            int: 作成された様式のID
        """
        now = datetime.now().isoformat()
        sql = """
        INSERT INTO forms (name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """
        with self._get_connection() as conn:
            cursor = conn.execute(sql, (name, description, now, now))
            conn.commit()
            form_id = cursor.lastrowid

        logger.info(f"様式を作成しました: id={form_id}, name={name}")
        return form_id

    def get_form(self, form_id: int) -> Optional[dict[str, Any]]:
        """
        指定IDの様式を取得する。

        Args:
            form_id: 様式のID

        Returns:
            dict または None: 様式データの辞書。存在しない場合はNone。
        """
        sql = "SELECT * FROM forms WHERE id = ?"
        with self._get_connection() as conn:
            row = conn.execute(sql, (form_id,)).fetchone()

        if row is None:
            return None
        return dict(row)

    def list_forms(self) -> list[dict[str, Any]]:
        """
        全様式の一覧を取得する。

        Returns:
            list[dict]: 様式データの辞書リスト。更新日時の降順で返す。
        """
        sql = "SELECT * FROM forms ORDER BY updated_at DESC"
        with self._get_connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(row) for row in rows]

    def update_form(self, form_id: int, name: str, description: str = "") -> bool:
        """
        様式の基本情報を更新する。

        Args:
            form_id:     更新対象の様式ID
            name:        新しい様式名
            description: 新しい説明文

        Returns:
            bool: 更新成功した場合True、対象が存在しない場合False
        """
        now = datetime.now().isoformat()
        sql = """
        UPDATE forms SET name = ?, description = ?, updated_at = ?
        WHERE id = ?
        """
        with self._get_connection() as conn:
            cursor = conn.execute(sql, (name, description, now, form_id))
            conn.commit()
            updated = cursor.rowcount > 0

        if updated:
            logger.info(f"様式を更新しました: id={form_id}, name={name}")
        else:
            logger.warning(f"更新対象の様式が見つかりません: id={form_id}")
        return updated

    def delete_form(self, form_id: int) -> bool:
        """
        様式を削除する。

        外部キー制約 ON DELETE CASCADE により、紐づく
        form_fields・ocr_results・ocr_result_fields も自動削除される。

        Args:
            form_id: 削除対象の様式ID

        Returns:
            bool: 削除成功した場合True、対象が存在しない場合False
        """
        sql = "DELETE FROM forms WHERE id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(sql, (form_id,))
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info(f"様式を削除しました (カスケード削除含む): id={form_id}")
        else:
            logger.warning(f"削除対象の様式が見つかりません: id={form_id}")
        return deleted

    # -------------------------------------------------------------------------
    # フィールド定義 (form_fields) の操作
    # -------------------------------------------------------------------------

    def save_form_field(self, form_id: int, field_data: dict[str, Any]) -> int:
        """
        様式フィールドを保存する (新規作成 or 更新)。

        field_data に 'id' キーが含まれていれば UPDATE、なければ INSERT。

        Args:
            form_id:    所属する様式のID
            field_data: フィールド定義データの辞書。キー:
                        - field_name (str): 識別名
                        - field_label (str): 表示ラベル
                        - page_number (int): ページ番号
                        - x1, y1, x2, y2 (float): 領域座標
                        - field_type (str): フィールド種別
                        - order_index (int): 列順序
                        - id (int, 省略可): 更新時に指定

        Returns:
            int: フィールドのID (新規作成時は新しいID、更新時は既存ID)
        """
        field_id = field_data.get("id")

        if field_id:
            # 既存フィールドの更新
            sql = """
            UPDATE form_fields
            SET field_name=?, field_label=?, page_number=?,
                x1=?, y1=?, x2=?, y2=?, field_type=?, order_index=?
            WHERE id=? AND form_id=?
            """
            with self._get_connection() as conn:
                conn.execute(sql, (
                    field_data.get("field_name", ""),
                    field_data.get("field_label", ""),
                    field_data.get("page_number", 1),
                    field_data.get("x1", 0.0),
                    field_data.get("y1", 0.0),
                    field_data.get("x2", 0.0),
                    field_data.get("y2", 0.0),
                    field_data.get("field_type", "text"),
                    field_data.get("order_index", 0),
                    field_id,
                    form_id,
                ))
                conn.commit()
            logger.debug(f"フィールドを更新しました: id={field_id}")
            return field_id
        else:
            # 新規フィールドの挿入
            sql = """
            INSERT INTO form_fields
                (form_id, field_name, field_label, page_number, x1, y1, x2, y2, field_type, order_index)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            with self._get_connection() as conn:
                cursor = conn.execute(sql, (
                    form_id,
                    field_data.get("field_name", ""),
                    field_data.get("field_label", ""),
                    field_data.get("page_number", 1),
                    field_data.get("x1", 0.0),
                    field_data.get("y1", 0.0),
                    field_data.get("x2", 0.0),
                    field_data.get("y2", 0.0),
                    field_data.get("field_type", "text"),
                    field_data.get("order_index", 0),
                ))
                conn.commit()
                new_id = cursor.lastrowid

            logger.debug(f"フィールドを作成しました: id={new_id}, form_id={form_id}")
            return new_id

    def get_form_fields(self, form_id: int) -> list[dict[str, Any]]:
        """
        様式に属するフィールド定義一覧を取得する。

        Args:
            form_id: 様式のID

        Returns:
            list[dict]: フィールドデータの辞書リスト。order_index 昇順。
        """
        sql = """
        SELECT * FROM form_fields
        WHERE form_id = ?
        ORDER BY page_number ASC, order_index ASC
        """
        with self._get_connection() as conn:
            rows = conn.execute(sql, (form_id,)).fetchall()
        return [dict(row) for row in rows]

    def delete_form_field(self, field_id: int) -> bool:
        """
        フィールド定義を削除する。

        Args:
            field_id: 削除対象のフィールドID

        Returns:
            bool: 削除成功した場合True
        """
        sql = "DELETE FROM form_fields WHERE id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(sql, (field_id,))
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            logger.debug(f"フィールドを削除しました: id={field_id}")
        return deleted

    # -------------------------------------------------------------------------
    # OCR結果 (ocr_results / ocr_result_fields) の操作
    # -------------------------------------------------------------------------

    def save_ocr_result(
        self,
        form_id: int,
        source_file: str,
        fields: list[dict[str, Any]],
        status: str = "success",
    ) -> int:
        """
        OCR処理結果をデータベースに保存する。

        ocr_results に1件のサマリーを作成し、
        各フィールドの認識テキストを ocr_result_fields に保存する。

        Args:
            form_id:     使用した様式のID
            source_file: 処理元ファイルのパス
            fields:      各フィールドの認識結果リスト。要素は辞書:
                         - field_id (int|None): フィールド定義ID
                         - field_name (str): フィールド識別名
                         - recognized_text (str): 認識テキスト
                         - confidence (float): 信頼度 0.0〜1.0
            status:      処理状態 ("success" / "error" / "partial")

        Returns:
            int: 作成された ocr_results のID
        """
        now = datetime.now().isoformat()

        with self._get_connection() as conn:
            # サマリーレコードを挿入
            cursor = conn.execute(
                """
                INSERT INTO ocr_results (form_id, source_file, processed_at, status)
                VALUES (?, ?, ?, ?)
                """,
                (form_id, source_file, now, status),
            )
            result_id = cursor.lastrowid

            # 各フィールドの認識結果を挿入
            for field in fields:
                conn.execute(
                    """
                    INSERT INTO ocr_result_fields
                        (result_id, field_id, field_name, recognized_text, confidence)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        result_id,
                        field.get("field_id"),
                        field.get("field_name", ""),
                        field.get("recognized_text", ""),
                        field.get("confidence", 0.0),
                    ),
                )
            conn.commit()

        logger.info(f"OCR結果を保存しました: result_id={result_id}, file={source_file}")
        return result_id

    def get_ocr_results(self, form_id: int) -> list[dict[str, Any]]:
        """
        様式に紐づくOCR処理結果の一覧を取得する。

        各結果にはフィールドデータも含める (JOIN)。

        Args:
            form_id: 様式のID

        Returns:
            list[dict]: OCR結果データ。各要素:
                        - id, form_id, source_file, processed_at, status
                        - fields: list[dict] (認識フィールド一覧)
        """
        results_sql = """
        SELECT * FROM ocr_results
        WHERE form_id = ?
        ORDER BY processed_at DESC
        """
        fields_sql = """
        SELECT * FROM ocr_result_fields WHERE result_id = ?
        """

        with self._get_connection() as conn:
            result_rows = conn.execute(results_sql, (form_id,)).fetchall()
            results = []
            for row in result_rows:
                result = dict(row)
                field_rows = conn.execute(fields_sql, (result["id"],)).fetchall()
                result["fields"] = [dict(f) for f in field_rows]
                results.append(result)

        return results

    def get_ocr_result_by_id(self, result_id: int) -> Optional[dict[str, Any]]:
        """
        IDでOCR処理結果を1件取得する。

        Args:
            result_id: OCR結果のID

        Returns:
            dict または None: OCR結果データ (fieldsリスト含む)
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM ocr_results WHERE id = ?", (result_id,)
            ).fetchone()

            if row is None:
                return None

            result = dict(row)
            field_rows = conn.execute(
                "SELECT * FROM ocr_result_fields WHERE result_id = ?", (result_id,)
            ).fetchall()
            result["fields"] = [dict(f) for f in field_rows]

        return result

    def get_ocr_results_by_ids(self, result_ids: list[int]) -> list[dict[str, Any]]:
        """
        複数のIDでOCR処理結果を一括取得する。

        Args:
            result_ids: OCR結果IDのリスト

        Returns:
            list[dict]: OCR結果データのリスト
        """
        if not result_ids:
            return []

        placeholders = ",".join("?" * len(result_ids))
        sql = f"SELECT * FROM ocr_results WHERE id IN ({placeholders}) ORDER BY processed_at DESC"

        with self._get_connection() as conn:
            result_rows = conn.execute(sql, result_ids).fetchall()
            results = []
            for row in result_rows:
                result = dict(row)
                field_rows = conn.execute(
                    "SELECT * FROM ocr_result_fields WHERE result_id = ?", (result["id"],)
                ).fetchall()
                result["fields"] = [dict(f) for f in field_rows]
                results.append(result)

        return results

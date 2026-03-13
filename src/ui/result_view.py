"""
result_view.py - OCR結果確認画面

担当: 木村 浩 (Hiroshi Kimura) - フロントエンド開発者
作成日: 2026-03-13

OCR処理の結果を一覧表示し、詳細確認・手動修正・CSVエクスポートを行う画面。

レイアウト:
    ┌──────────────────────────────────────────────────────┐
    │  様式選択: [Combobox ▼]  [更新]                       │
    ├────────────────────┬─────────────────────────────────┤
    │ OCR結果一覧         │ 詳細表示                         │
    │ (Treeview)         │                                 │
    │  ファイル名 | 日時  │ ファイル名: sample.pdf          │
    │  ○ file1  | 03-13 │ 処理日時: 2026-03-13 12:00      │
    │  ○ file2  | 03-13 │ ステータス: success             │
    │                   │                                 │
    │                   │ フィールド認識結果:               │
    │                   │   氏名: [山田太郎    ] [編集]    │
    │                   │   住所: [東京都......] [編集]    │
    │                   │                                 │
    │ [全選択] [CSVへ]   │          [変更を保存]            │
    └────────────────────┴─────────────────────────────────┘
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import logging
import sys
import csv
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

# プロジェクトルートをパスに追加（単体動作確認用）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# DatabaseManagerのインポート
try:
    from src.core.database import DatabaseManager
    _DB_AVAILABLE = True
except ImportError as e:
    logger.warning(f"DatabaseManagerのインポートに失敗: {e}")
    _DB_AVAILABLE = False


# ---------------------------------------------------------------------------
# OCR結果確認フレーム
# ---------------------------------------------------------------------------

class ResultViewFrame(ttk.Frame):
    """
    OCR結果の一覧表示・詳細確認・手動修正・エクスポートを行うフレーム。

    Attributes:
        db_manager:       DatabaseManagerインスタンス
        status_callback:  ステータスバー更新コールバック

        _forms:           様式データリスト
        _results:         現在表示中の様式のOCR結果リスト
        _selected_result: 詳細パネルに表示中の結果データ
        _field_entries:   詳細パネルのフィールド編集Entry辞書 {field_name: Entry}
    """

    # Treeviewのカラム定義
    RESULT_COLUMNS = [
        ("filename",     "ファイル名", 200),
        ("processed_at", "処理日時",   160),
        ("status",       "ステータス",  80),
        ("field_count",  "フィールド数", 80),
    ]

    def __init__(
        self,
        parent: tk.Widget,
        db_manager=None,
        status_callback: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.db_manager = db_manager
        self.status_callback = status_callback or (lambda msg: None)

        # 内部状態
        self._forms: list[dict] = []
        self._results: list[dict] = []
        self._selected_result: Optional[dict] = None
        self._field_entries: dict[str, tk.Entry] = {}
        self._field_result_map: dict[str, dict] = {}  # field_name -> OCR結果フィールドdict

        self._build_ui()
        self._load_forms()

    def _build_ui(self) -> None:
        """UIを構築する。"""
        # ---- ヘッダー: 様式選択 ----
        header = ttk.Frame(self, padding=(8, 6, 8, 4))
        header.pack(fill=tk.X)

        ttk.Label(header, text="様式選択:", font=("", 10)).pack(side=tk.LEFT)
        self._form_var = tk.StringVar()
        self._form_combo = ttk.Combobox(
            header,
            textvariable=self._form_var,
            state="readonly",
            width=36,
        )
        self._form_combo.pack(side=tk.LEFT, padx=(4, 8))
        self._form_combo.bind("<<ComboboxSelected>>", self._on_form_select)

        ttk.Button(
            header, text="更新", command=self._load_results, width=8
        ).pack(side=tk.LEFT)

        # エクスポートボタン（右端）
        ttk.Button(
            header,
            text="全件 CSV出力",
            command=lambda: self._on_export_csv(selected_only=False),
            width=14,
        ).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(
            header,
            text="選択件 CSV出力",
            command=lambda: self._on_export_csv(selected_only=True),
            width=14,
        ).pack(side=tk.RIGHT)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8)

        # ---- メインエリア: 一覧 | 詳細 ----
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # 左: 結果一覧パネル
        left_panel = self._build_result_list_panel(paned)
        paned.add(left_panel, weight=2)

        # 右: 詳細パネル
        right_panel = self._build_detail_panel(paned)
        paned.add(right_panel, weight=3)

    def _build_result_list_panel(self, parent: tk.Widget) -> ttk.Frame:
        """OCR結果一覧パネルを構築する。"""
        frame = ttk.LabelFrame(parent, text="OCR結果一覧", padding=6)

        # Treeview（スクロールバー付き）
        col_ids = [c[0] for c in self.RESULT_COLUMNS]
        self._result_tree = ttk.Treeview(
            frame,
            columns=col_ids,
            show="headings",
            selectmode="extended",  # 複数選択可（CSV出力用）
        )

        for col_id, col_label, col_width in self.RESULT_COLUMNS:
            self._result_tree.heading(col_id, text=col_label)
            self._result_tree.column(col_id, width=col_width, minwidth=40)

        v_scroll = ttk.Scrollbar(
            frame, orient=tk.VERTICAL, command=self._result_tree.yview
        )
        self._result_tree.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._result_tree.pack(fill=tk.BOTH, expand=True)

        # クリックで詳細表示
        self._result_tree.bind("<<TreeviewSelect>>", self._on_result_select)

        # 結果件数ラベル
        self._result_count_var = tk.StringVar(value="0 件")
        ttk.Label(
            frame, textvariable=self._result_count_var, font=("", 9), foreground="#666"
        ).pack(anchor=tk.W, pady=(4, 0))

        # ボタン
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(
            btn_frame, text="全選択", command=self._on_select_all
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            btn_frame, text="選択解除", command=self._on_deselect_all
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            btn_frame, text="削除", command=self._on_delete_result
        ).pack(side=tk.LEFT)

        return frame

    def _build_detail_panel(self, parent: tk.Widget) -> ttk.Frame:
        """詳細パネルを構築する。"""
        frame = ttk.LabelFrame(parent, text="詳細表示・修正", padding=8)

        # ---- ファイル情報 ----
        info_frame = ttk.Frame(frame)
        info_frame.pack(fill=tk.X, pady=(0, 8))
        info_frame.columnconfigure(1, weight=1)

        labels = [
            ("ファイル名:", "_detail_filename_var"),
            ("処理日時:",   "_detail_datetime_var"),
            ("ステータス:", "_detail_status_var"),
        ]
        for row_idx, (label_text, attr_name) in enumerate(labels):
            ttk.Label(info_frame, text=label_text, anchor=tk.W, width=12).grid(
                row=row_idx, column=0, sticky=tk.W, padx=(0, 6), pady=1
            )
            var = tk.StringVar(value="---")
            setattr(self, attr_name, var)
            ttk.Label(
                info_frame, textvariable=var, anchor=tk.W, foreground="#333"
            ).grid(row=row_idx, column=1, sticky=tk.EW, pady=1)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        # ---- フィールド認識結果（スクロール対応）----
        ttk.Label(frame, text="フィールド認識結果（クリックで編集）:", font=("", 9, "bold")).pack(
            anchor=tk.W, pady=(0, 4)
        )

        # フィールドエリア（スクロール対応: Canvasを使う）
        fields_outer = ttk.Frame(frame)
        fields_outer.pack(fill=tk.BOTH, expand=True)

        fields_canvas = tk.Canvas(fields_outer, highlightthickness=0)
        fields_scrollbar = ttk.Scrollbar(
            fields_outer, orient=tk.VERTICAL, command=fields_canvas.yview
        )
        fields_canvas.configure(yscrollcommand=fields_scrollbar.set)

        fields_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        fields_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # スクロール可能な内部フレーム
        self._fields_inner_frame = ttk.Frame(fields_canvas)
        self._fields_canvas_window = fields_canvas.create_window(
            0, 0, anchor=tk.NW, window=self._fields_inner_frame
        )

        # フレームサイズ変更時にCanvasのscrollregionを更新
        def _on_frame_configure(event):
            fields_canvas.configure(
                scrollregion=fields_canvas.bbox("all")
            )

        def _on_canvas_configure(event):
            fields_canvas.itemconfig(
                self._fields_canvas_window, width=event.width
            )

        self._fields_inner_frame.bind("<Configure>", _on_frame_configure)
        fields_canvas.bind("<Configure>", _on_canvas_configure)

        # マウスホイールでスクロール
        def _on_mousewheel(event):
            fields_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        fields_canvas.bind("<MouseWheel>", _on_mousewheel)

        # ---- 保存ボタン ----
        ttk.Button(
            frame,
            text="変更を保存",
            command=self._on_save_corrections,
            width=14,
        ).pack(side=tk.BOTTOM, anchor=tk.E, pady=(8, 0))

        return frame

    # -----------------------------------------------------------------------
    # データ操作
    # -----------------------------------------------------------------------

    def _load_forms(self) -> None:
        """様式一覧を読み込んでComboboxを更新する。"""
        self._forms = []
        if self.db_manager:
            try:
                self._forms = self.db_manager.list_forms()
            except Exception as e:
                logger.error(f"様式一覧取得に失敗: {e}")
        else:
            self._forms = [
                {"id": 1, "name": "住民票申請書（サンプル）"},
                {"id": 2, "name": "転出届（サンプル）"},
            ]

        form_names = [f["name"] for f in self._forms]
        self._form_combo["values"] = form_names
        if form_names:
            self._form_combo.current(0)
            self._load_results()

    def _load_results(self) -> None:
        """選択中様式のOCR結果一覧をDBから読み込む。"""
        idx = self._form_combo.current()
        if idx < 0 or idx >= len(self._forms):
            return

        form = self._forms[idx]

        if self.db_manager:
            try:
                self._results = self.db_manager.get_ocr_results(form["id"])
            except Exception as e:
                logger.error(f"OCR結果取得に失敗: {e}")
                messagebox.showerror("エラー", f"OCR結果の取得に失敗しました。\n{e}", parent=self)
                return
        else:
            # デモモード: サンプルデータ
            self._results = [
                {
                    "id": 1, "form_id": 1,
                    "source_file": "/path/to/sample1.pdf",
                    "processed_at": "2026-03-13T10:00:00",
                    "status": "success",
                    "fields": [
                        {"id": 1, "field_id": 1, "field_name": "name",
                         "recognized_text": "山田 太郎", "confidence": 0.92},
                        {"id": 2, "field_id": 2, "field_name": "address",
                         "recognized_text": "東京都新宿区...", "confidence": 0.85},
                    ],
                },
                {
                    "id": 2, "form_id": 1,
                    "source_file": "/path/to/sample2.pdf",
                    "processed_at": "2026-03-13T11:00:00",
                    "status": "partial",
                    "fields": [
                        {"id": 3, "field_id": 1, "field_name": "name",
                         "recognized_text": "鈴木 花子", "confidence": 0.78},
                        {"id": 4, "field_id": 2, "field_name": "address",
                         "recognized_text": "", "confidence": 0.0},
                    ],
                },
            ]

        self._refresh_result_tree()
        self._clear_detail_panel()
        self.status_callback(f"OCR結果を読み込みました（{len(self._results)}件）")

    def _refresh_result_tree(self) -> None:
        """OCR結果Treeviewを再描画する。"""
        for item in self._result_tree.get_children():
            self._result_tree.delete(item)

        for result in self._results:
            source_file = Path(result.get("source_file", "")).name
            processed_at = result.get("processed_at", "")
            # 日時を短縮表示（ISO形式から日時部分のみ抽出）
            if "T" in processed_at:
                processed_at = processed_at.replace("T", " ").split(".")[0]

            status = result.get("status", "")
            field_count = len(result.get("fields", []))

            # ステータスに応じて行のスタイルを変える（タグを使用）
            tag = "partial" if status == "partial" else "error" if status == "error" else ""

            self._result_tree.insert(
                "", tk.END,
                iid=str(result["id"]),
                values=(source_file, processed_at, status, field_count),
                tags=(tag,),
            )

        # ステータス別の色設定
        self._result_tree.tag_configure("partial", foreground="#e67e22")
        self._result_tree.tag_configure("error",   foreground="#c0392b")

        count = len(self._results)
        self._result_count_var.set(f"{count} 件")

    def _clear_detail_panel(self) -> None:
        """詳細パネルをクリアする。"""
        self._detail_filename_var.set("---")
        self._detail_datetime_var.set("---")
        self._detail_status_var.set("---")
        self._selected_result = None
        self._field_entries.clear()
        self._field_result_map.clear()

        # フィールドエリアをクリア
        for widget in self._fields_inner_frame.winfo_children():
            widget.destroy()

    def _show_detail(self, result: dict) -> None:
        """
        選択されたOCR結果の詳細を右パネルに表示する。

        Args:
            result: OCR結果データ dict
        """
        self._selected_result = result
        self._field_entries.clear()
        self._field_result_map.clear()

        # ファイル情報を更新
        source_file = Path(result.get("source_file", "")).name
        self._detail_filename_var.set(source_file)

        processed_at = result.get("processed_at", "---")
        if "T" in processed_at:
            processed_at = processed_at.replace("T", " ").split(".")[0]
        self._detail_datetime_var.set(processed_at)

        status = result.get("status", "---")
        self._detail_status_var.set(status)

        # フィールドエリアをクリアして再構築
        for widget in self._fields_inner_frame.winfo_children():
            widget.destroy()

        fields = result.get("fields", [])
        if not fields:
            ttk.Label(
                self._fields_inner_frame,
                text="認識されたフィールドがありません",
                foreground="#888",
            ).pack(pady=16)
            return

        # 各フィールドを行として表示
        self._fields_inner_frame.columnconfigure(1, weight=1)

        for row_idx, field in enumerate(fields):
            field_name = field.get("field_name", "")
            recognized_text = field.get("recognized_text", "")
            confidence = field.get("confidence", 0.0)

            # フィールドラベル（識別名）
            ttk.Label(
                self._fields_inner_frame,
                text=f"{field_name}:",
                anchor=tk.W,
                width=16,
            ).grid(row=row_idx, column=0, sticky=tk.W, padx=(0, 6), pady=2)

            # 認識テキスト入力欄
            text_var = tk.StringVar(value=recognized_text)
            entry = ttk.Entry(
                self._fields_inner_frame,
                textvariable=text_var,
                width=36,
            )
            entry.grid(row=row_idx, column=1, sticky=tk.EW, pady=2)

            # 信頼度インジケーター（色で信頼度を表示）
            conf_pct = int(confidence * 100)
            if confidence >= 0.8:
                conf_color = "#27ae60"   # 高信頼度: 緑
            elif confidence >= 0.5:
                conf_color = "#e67e22"   # 中信頼度: オレンジ
            else:
                conf_color = "#c0392b"   # 低信頼度: 赤

            ttk.Label(
                self._fields_inner_frame,
                text=f"{conf_pct}%",
                foreground=conf_color,
                width=5,
                anchor=tk.E,
                font=("", 9),
            ).grid(row=row_idx, column=2, padx=(4, 0), pady=2)

            # Entry と フィールドデータを紐付け
            self._field_entries[field_name] = entry
            self._field_result_map[field_name] = field

    # -----------------------------------------------------------------------
    # イベントハンドラ
    # -----------------------------------------------------------------------

    def _on_form_select(self, event=None) -> None:
        """様式Comboboxの変更イベント。"""
        self._load_results()

    def _on_result_select(self, event=None) -> None:
        """結果Treeviewのクリックイベント。詳細パネルを更新する。"""
        selection = self._result_tree.selection()
        if not selection:
            return

        # 最後に選択されたアイテムを表示
        iid = selection[-1]
        try:
            result_id = int(iid)
        except ValueError:
            return

        result = next(
            (r for r in self._results if r["id"] == result_id), None
        )
        if result:
            self._show_detail(result)
            source_name = Path(result.get("source_file", "")).name
            self.status_callback(f"詳細表示: {source_name}")

    def _on_select_all(self) -> None:
        """「全選択」ボタン。"""
        self._result_tree.selection_set(self._result_tree.get_children())

    def _on_deselect_all(self) -> None:
        """「選択解除」ボタン。"""
        self._result_tree.selection_remove(self._result_tree.selection())

    def _on_delete_result(self) -> None:
        """「削除」ボタン: 選択中のOCR結果を削除する。"""
        selection = self._result_tree.selection()
        if not selection:
            messagebox.showinfo("確認", "削除する結果を選択してください。", parent=self)
            return

        count = len(selection)
        if not messagebox.askyesno(
            "削除確認",
            f"{count}件のOCR結果を削除しますか？",
            icon=messagebox.WARNING,
            parent=self,
        ):
            return

        # NOTE: DatabaseManagerにはOCR結果削除メソッドが未実装のため
        # 現状はローカルデータからのみ削除する
        deleted_ids = set()
        for iid in selection:
            try:
                deleted_ids.add(int(iid))
            except ValueError:
                pass

        self._results = [r for r in self._results if r["id"] not in deleted_ids]
        self._refresh_result_tree()
        self._clear_detail_panel()
        self.status_callback(f"{count}件のOCR結果を削除しました")

    def _on_save_corrections(self) -> None:
        """
        「変更を保存」ボタン: 詳細パネルで編集された認識テキストをDBに保存する。

        NOTE: DatabaseManagerには個別フィールドのテキスト更新メソッドが
        現状未実装のため、デモモードでのみ動作する。
        将来的にDBへの保存機能を追加する際はここを修正する。
        """
        if self._selected_result is None:
            messagebox.showinfo("確認", "修正する結果を選択してください。", parent=self)
            return

        # Entryウィジェットから最新の値を取得
        has_changes = False
        for field_name, entry in self._field_entries.items():
            new_text = entry.get()
            field_data = self._field_result_map.get(field_name)
            if field_data is None:
                continue

            old_text = field_data.get("recognized_text", "")
            if new_text != old_text:
                field_data["recognized_text"] = new_text
                has_changes = True
                logger.info(
                    f"フィールド「{field_name}」を修正: "
                    f"'{old_text[:20]}' -> '{new_text[:20]}'"
                )

        if not has_changes:
            messagebox.showinfo("確認", "変更された内容はありません。", parent=self)
            return

        # 将来: DBへの永続化処理をここに追加
        # self.db_manager.update_ocr_field_text(field_id, new_text)

        messagebox.showinfo(
            "保存完了",
            "修正内容をメモリに反映しました。\n"
            "（現バージョンではDB保存には対応していません。CSV出力で保存してください）",
            parent=self,
        )
        self.status_callback("修正内容を反映しました")

    def _on_export_csv(self, selected_only: bool = False) -> None:
        """
        CSVエクスポートを実行する。

        Args:
            selected_only: TrueのときTreeviewで選択中の結果のみ出力する
        """
        # 出力対象を決定
        if selected_only:
            selection = self._result_tree.selection()
            if not selection:
                messagebox.showinfo("確認", "CSV出力する結果を選択してください。", parent=self)
                return
            selected_ids = {int(iid) for iid in selection if iid.isdigit()}
            target_results = [r for r in self._results if r["id"] in selected_ids]
        else:
            target_results = self._results

        if not target_results:
            messagebox.showinfo("確認", "出力するOCR結果がありません。", parent=self)
            return

        # 出力先の選択
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"ocr_result_{now}.csv"

        output_path_str = filedialog.asksaveasfilename(
            parent=self,
            title="CSV保存先を選択",
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSVファイル", "*.csv"), ("すべてのファイル", "*.*")],
        )
        if not output_path_str:
            return

        output_path = Path(output_path_str)

        # エンコーディング選択（簡易ダイアログ）
        # 本来はSettingsFrameの設定を参照したいが、
        # ここでは簡便に utf-8-sig（Excel対応BOM付きUTF-8）を使用
        encoding = "utf-8-sig"

        try:
            rows_written = self._write_csv(output_path, target_results, encoding)
            self.status_callback(f"CSV出力完了: {output_path.name} ({rows_written}行)")
            messagebox.showinfo(
                "CSV出力完了",
                f"{rows_written}件の結果をCSVに出力しました。\n\nファイル: {output_path}",
                parent=self,
            )
        except Exception as e:
            logger.error(f"CSV出力エラー: {e}")
            messagebox.showerror("CSV出力エラー", f"CSV出力に失敗しました。\n\n{e}", parent=self)

    def _write_csv(
        self,
        output_path: Path,
        results: list[dict],
        encoding: str = "utf-8-sig",
    ) -> int:
        """
        OCR結果リストをCSVファイルに書き出す。

        Args:
            output_path: 出力ファイルパス
            results:     書き出すOCR結果リスト
            encoding:    文字コード

        Returns:
            int: 書き出した行数
        """
        # 全フィールド名を収集（列名として使用）
        all_field_names: list[str] = []
        for result in results:
            for field in result.get("fields", []):
                fn = field.get("field_name", "")
                if fn and fn not in all_field_names:
                    all_field_names.append(fn)

        with open(output_path, "w", encoding=encoding, newline="") as f:
            writer = csv.writer(f)

            # ヘッダー行
            header = ["ファイル名", "処理日時", "ステータス"] + all_field_names
            writer.writerow(header)

            rows_written = 0
            for result in results:
                source_name = Path(result.get("source_file", "")).name
                processed_at = result.get("processed_at", "")
                if "T" in processed_at:
                    processed_at = processed_at.replace("T", " ").split(".")[0]

                status = result.get("status", "")

                # フィールドデータをマッピング
                field_data = {
                    f.get("field_name", ""): f.get("recognized_text", "")
                    for f in result.get("fields", [])
                }

                row = (
                    [source_name, processed_at, status]
                    + [field_data.get(fn, "") for fn in all_field_names]
                )
                writer.writerow(row)
                rows_written += 1

        return rows_written

    def refresh(self) -> None:
        """他の画面から戻ってきた際などに呼び出す外部向けリフレッシュ。"""
        self._load_forms()


# ---------------------------------------------------------------------------
# 単体動作確認用エントリーポイント
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("ResultViewFrame 単体起動モード（デモデータ使用）")

    root = tk.Tk()
    root.title("OCR結果確認 - 動作確認")
    root.geometry("1000x650")

    style = ttk.Style(root)
    style.theme_use("clam")

    frame = ResultViewFrame(
        root,
        db_manager=None,
        status_callback=lambda msg: print(f"[STATUS] {msg}"),
    )
    frame.pack(fill=tk.BOTH, expand=True)

    root.mainloop()

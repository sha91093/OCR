"""
form_management.py - 様式管理画面

担当: 木村 浩 (Hiroshi Kimura) - フロントエンド開発者
作成日: 2026-03-13

様式（フォーム定義）の一覧表示・作成・削除と、
各様式に属するフィールド定義の管理を行う画面。

レイアウト:
    ┌─────────────────────────────────────────────────────┐
    │  ┌─────────────┐  ┌──────────────────────────────┐  │
    │  │ 様式一覧     │  │ 様式詳細・フィールド定義        │  │
    │  │ (Listbox)   │  │                              │  │
    │  │             │  │ 様式名: [__________]         │  │
    │  │ ○ 様式A     │  │ 説明:  [__________]         │  │
    │  │ ○ 様式B     │  │                              │  │
    │  │             │  │ フィールド一覧 (Treeview)     │  │
    │  │ [新規] [削除] │  │                              │  │
    │  └─────────────┘  │ [追加] [削除] [領域設定] [保存] │  │
    │                   └──────────────────────────────┘  │
    └─────────────────────────────────────────────────────┘
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import logging
import sys
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# プロジェクトルートをパスに追加（単体動作確認用）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# FieldEditorDialogのインポート（未作成でもokなようにtry/except）
try:
    from src.ui.field_editor import FieldEditorDialog
    _FIELD_EDITOR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"FieldEditorDialogのインポートに失敗: {e}")
    _FIELD_EDITOR_AVAILABLE = False

# DatabaseManagerのインポート（未作成でもokなようにtry/except）
try:
    from src.core.database import DatabaseManager
    _DB_AVAILABLE = True
except ImportError as e:
    logger.warning(f"DatabaseManagerのインポートに失敗: {e}")
    _DB_AVAILABLE = False


# ---------------------------------------------------------------------------
# フィールド追加・編集ダイアログ
# ---------------------------------------------------------------------------

class FieldEditDialog(tk.Toplevel):
    """
    フィールド定義を手動で追加・編集するシンプルなダイアログ。

    FieldEditorDialog（画像上でマウス操作）が使えない場合や、
    細かい座標値を直接入力したい場合に使用する。
    """

    def __init__(self, parent: tk.Widget, field_data: Optional[dict] = None):
        """
        Args:
            parent:     親ウィジェット
            field_data: 編集対象フィールドデータ（新規の場合はNone）
        """
        super().__init__(parent)
        self.title("フィールド編集")
        self.resizable(False, False)
        self.grab_set()  # モーダルダイアログ

        # 戻り値（OKで更新、キャンセルでNone）
        self.result: Optional[dict] = None
        self._field_data = field_data or {}

        self._build_ui()

        # ダイアログを親ウィンドウの中央に表示
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, px)}+{max(0, py)}")

    def _build_ui(self) -> None:
        """ダイアログUIを構築する。"""
        pad = {"padx": 8, "pady": 4}

        form_frame = ttk.Frame(self, padding=12)
        form_frame.pack(fill=tk.BOTH, expand=True)

        # フィールド識別名
        ttk.Label(form_frame, text="フィールド識別名 (英数字):").grid(
            row=0, column=0, sticky=tk.W, **pad
        )
        self._name_var = tk.StringVar(value=self._field_data.get("field_name", ""))
        ttk.Entry(form_frame, textvariable=self._name_var, width=24).grid(
            row=0, column=1, sticky=tk.EW, **pad
        )

        # 表示ラベル
        ttk.Label(form_frame, text="表示ラベル (日本語可):").grid(
            row=1, column=0, sticky=tk.W, **pad
        )
        self._label_var = tk.StringVar(value=self._field_data.get("field_label", ""))
        ttk.Entry(form_frame, textvariable=self._label_var, width=24).grid(
            row=1, column=1, sticky=tk.EW, **pad
        )

        # ページ番号
        ttk.Label(form_frame, text="ページ番号:").grid(
            row=2, column=0, sticky=tk.W, **pad
        )
        self._page_var = tk.IntVar(value=self._field_data.get("page_number", 1))
        ttk.Spinbox(
            form_frame, textvariable=self._page_var, from_=1, to=99, width=8
        ).grid(row=2, column=1, sticky=tk.W, **pad)

        # 座標（x1, y1, x2, y2）
        ttk.Label(form_frame, text="座標 X1:").grid(row=3, column=0, sticky=tk.W, **pad)
        self._x1_var = tk.DoubleVar(value=self._field_data.get("x1", 0.0))
        ttk.Entry(form_frame, textvariable=self._x1_var, width=10).grid(
            row=3, column=1, sticky=tk.W, **pad
        )

        ttk.Label(form_frame, text="座標 Y1:").grid(row=4, column=0, sticky=tk.W, **pad)
        self._y1_var = tk.DoubleVar(value=self._field_data.get("y1", 0.0))
        ttk.Entry(form_frame, textvariable=self._y1_var, width=10).grid(
            row=4, column=1, sticky=tk.W, **pad
        )

        ttk.Label(form_frame, text="座標 X2:").grid(row=5, column=0, sticky=tk.W, **pad)
        self._x2_var = tk.DoubleVar(value=self._field_data.get("x2", 0.0))
        ttk.Entry(form_frame, textvariable=self._x2_var, width=10).grid(
            row=5, column=1, sticky=tk.W, **pad
        )

        ttk.Label(form_frame, text="座標 Y2:").grid(row=6, column=0, sticky=tk.W, **pad)
        self._y2_var = tk.DoubleVar(value=self._field_data.get("y2", 0.0))
        ttk.Entry(form_frame, textvariable=self._y2_var, width=10).grid(
            row=6, column=1, sticky=tk.W, **pad
        )

        # フィールド種別
        ttk.Label(form_frame, text="フィールド種別:").grid(
            row=7, column=0, sticky=tk.W, **pad
        )
        self._type_var = tk.StringVar(
            value=self._field_data.get("field_type", "text")
        )
        type_combo = ttk.Combobox(
            form_frame,
            textvariable=self._type_var,
            values=["text", "number", "date"],
            width=12,
            state="readonly",
        )
        type_combo.grid(row=7, column=1, sticky=tk.W, **pad)

        form_frame.columnconfigure(1, weight=1)

        # ボタン
        btn_frame = ttk.Frame(self, padding=(12, 4, 12, 12))
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(
            side=tk.RIGHT, padx=4
        )
        ttk.Button(btn_frame, text="キャンセル", command=self.destroy, width=10).pack(
            side=tk.RIGHT
        )

    def _on_ok(self) -> None:
        """OKボタン押下時のバリデーションと結果設定。"""
        name = self._name_var.get().strip()
        label = self._label_var.get().strip()

        if not name:
            messagebox.showwarning("入力エラー", "フィールド識別名を入力してください。", parent=self)
            return
        if not label:
            messagebox.showwarning("入力エラー", "表示ラベルを入力してください。", parent=self)
            return

        try:
            x1 = float(self._x1_var.get())
            y1 = float(self._y1_var.get())
            x2 = float(self._x2_var.get())
            y2 = float(self._y2_var.get())
        except (tk.TclError, ValueError):
            messagebox.showwarning("入力エラー", "座標には数値を入力してください。", parent=self)
            return

        self.result = {
            **self._field_data,  # 既存データ（idなど）を保持
            "field_name":  name,
            "field_label": label,
            "page_number": self._page_var.get(),
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "field_type":  self._type_var.get(),
        }
        self.destroy()


# ---------------------------------------------------------------------------
# 様式管理フレーム
# ---------------------------------------------------------------------------

class FormManagementFrame(ttk.Frame):
    """
    様式管理画面のメインフレーム。

    左パネルに様式一覧 (Listbox)、
    右パネルに様式詳細とフィールド定義 (Treeview) を表示する。

    Attributes:
        db_manager:       DatabaseManagerインスタンス
        status_callback:  ステータスバー更新コールバック
        _forms:           取得済み様式データリスト
        _current_form_id: 現在選択中の様式ID（未選択時はNone）
        _fields:          現在選択中様式のフィールドデータリスト
    """

    # Treeview のカラム定義: (カラムID, 表示名, 幅)
    FIELD_COLUMNS = [
        ("field_name",  "識別名",   100),
        ("field_label", "ラベル",   100),
        ("page_number", "ページ",    60),
        ("x1",          "X1",        60),
        ("y1",          "Y1",        60),
        ("x2",          "X2",        60),
        ("y2",          "Y2",        60),
        ("field_type",  "種別",      60),
    ]

    def __init__(
        self,
        parent: tk.Widget,
        db_manager=None,
        status_callback: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        """
        Args:
            parent:           親ウィジェット
            db_manager:       DatabaseManagerインスタンス（Noneでデモモード）
            status_callback:  ステータスバー更新関数
        """
        super().__init__(parent, **kwargs)
        self.db_manager = db_manager
        self.status_callback = status_callback or (lambda msg: None)

        # 内部状態
        self._forms: list[dict] = []
        self._current_form_id: Optional[int] = None
        self._fields: list[dict] = []

        self._build_ui()
        self._load_forms()

    def _build_ui(self) -> None:
        """左右パネルのレイアウトを構築する。"""
        # PanedWindow でリサイズ可能な左右分割レイアウト
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 左パネル（様式一覧）
        left_panel = self._build_left_panel(paned)
        paned.add(left_panel, weight=1)

        # 右パネル（様式詳細・フィールド定義）
        right_panel = self._build_right_panel(paned)
        paned.add(right_panel, weight=3)

    def _build_left_panel(self, parent: tk.Widget) -> ttk.Frame:
        """
        左パネル（様式一覧）を構築して返す。

        Listboxと「新規作成」「削除」ボタンで構成。
        """
        frame = ttk.LabelFrame(parent, text="様式一覧", padding=6)

        # Listbox（スクロールバー付き）
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self._form_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
            activestyle="none",
            font=("", 10),
            relief=tk.FLAT,
            bd=1,
            highlightthickness=1,
        )
        scrollbar.config(command=self._form_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._form_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 選択変更イベントをバインド
        self._form_listbox.bind("<<ListboxSelect>>", self._on_form_select)

        # ボタンエリア
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            btn_frame, text="新規作成", command=self._on_create_form
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(
            btn_frame, text="削除", command=self._on_delete_form
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

        return frame

    def _build_right_panel(self, parent: tk.Widget) -> ttk.Frame:
        """
        右パネル（様式詳細・フィールド定義）を構築して返す。

        様式名/説明の入力欄と、フィールド定義 Treeview で構成。
        """
        frame = ttk.LabelFrame(parent, text="様式詳細・フィールド定義", padding=6)

        # ---- 様式情報入力エリア ----
        info_frame = ttk.Frame(frame)
        info_frame.pack(fill=tk.X, pady=(0, 8))
        info_frame.columnconfigure(1, weight=1)

        ttk.Label(info_frame, text="様式名:").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 6), pady=2
        )
        self._form_name_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self._form_name_var, width=32).grid(
            row=0, column=1, sticky=tk.EW, pady=2
        )

        ttk.Label(info_frame, text="説明:").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 6), pady=2
        )
        self._form_desc_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self._form_desc_var).grid(
            row=1, column=1, sticky=tk.EW, pady=2
        )

        # ---- フィールド定義エリア ----
        field_label = ttk.Label(frame, text="フィールド定義", font=("", 9, "bold"))
        field_label.pack(anchor=tk.W)

        # Treeview（スクロールバー付き）
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(2, 6))

        col_ids = [c[0] for c in self.FIELD_COLUMNS]
        self._field_tree = ttk.Treeview(
            tree_frame,
            columns=col_ids,
            show="headings",
            selectmode="browse",
            height=10,
        )

        # カラムヘッダーと幅を設定
        for col_id, col_label, col_width in self.FIELD_COLUMNS:
            self._field_tree.heading(col_id, text=col_label)
            self._field_tree.column(col_id, width=col_width, minwidth=40)

        # スクロールバー
        v_scroll = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=self._field_tree.yview
        )
        h_scroll = ttk.Scrollbar(
            tree_frame, orient=tk.HORIZONTAL, command=self._field_tree.xview
        )
        self._field_tree.configure(
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set,
        )
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self._field_tree.pack(fill=tk.BOTH, expand=True)

        # ダブルクリックで編集
        self._field_tree.bind("<Double-1>", self._on_field_double_click)

        # ---- ボタンエリア ----
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(
            btn_frame, text="フィールド追加", command=self._on_add_field
        ).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Button(
            btn_frame, text="フィールド削除", command=self._on_delete_field
        ).pack(side=tk.LEFT, padx=(0, 4))

        # テンプレート画像で領域設定ボタン（FieldEditorDialogを起動）
        self._area_btn = ttk.Button(
            btn_frame,
            text="テンプレート画像で領域設定",
            command=self._on_open_field_editor,
        )
        self._area_btn.pack(side=tk.LEFT, padx=(0, 4))
        if not _FIELD_EDITOR_AVAILABLE:
            self._area_btn.configure(state=tk.DISABLED)

        # 保存ボタン（右端に配置）
        ttk.Button(
            btn_frame, text="保存", command=self._on_save_form, width=10
        ).pack(side=tk.RIGHT)

        return frame

    # -----------------------------------------------------------------------
    # データ操作メソッド
    # -----------------------------------------------------------------------

    def _load_forms(self) -> None:
        """DBから様式一覧を読み込んでListboxを更新する。"""
        self._forms = []
        if self.db_manager:
            try:
                self._forms = self.db_manager.list_forms()
            except Exception as e:
                logger.error(f"様式一覧の取得に失敗: {e}")
                messagebox.showerror("エラー", f"様式一覧の読み込みに失敗しました。\n{e}", parent=self)
        else:
            # デモモード: サンプルデータ
            self._forms = [
                {"id": 1, "name": "住民票申請書（サンプル）", "description": "デモ用サンプル"},
                {"id": 2, "name": "転出届（サンプル）",      "description": "デモ用サンプル"},
            ]

        # Listboxを更新
        self._form_listbox.delete(0, tk.END)
        for form in self._forms:
            self._form_listbox.insert(tk.END, form["name"])

        self.status_callback(f"様式一覧を読み込みました（{len(self._forms)}件）")

    def _load_fields(self, form_id: int) -> None:
        """指定様式のフィールド定義をDBから読み込んでTreeviewを更新する。"""
        self._fields = []
        if self.db_manager:
            try:
                self._fields = self.db_manager.get_form_fields(form_id)
            except Exception as e:
                logger.error(f"フィールド一覧の取得に失敗: {e}")
                messagebox.showerror("エラー", f"フィールド一覧の読み込みに失敗しました。\n{e}", parent=self)
        else:
            # デモモード: サンプルデータ
            self._fields = [
                {
                    "id": 1, "form_id": form_id,
                    "field_name": "name", "field_label": "氏名",
                    "page_number": 1,
                    "x1": 100.0, "y1": 200.0, "x2": 400.0, "y2": 240.0,
                    "field_type": "text", "order_index": 0,
                },
                {
                    "id": 2, "form_id": form_id,
                    "field_name": "address", "field_label": "住所",
                    "page_number": 1,
                    "x1": 100.0, "y1": 260.0, "x2": 600.0, "y2": 300.0,
                    "field_type": "text", "order_index": 1,
                },
            ]

        self._refresh_field_tree()

    def _refresh_field_tree(self) -> None:
        """フィールドTreeviewをself._fieldsで再描画する。"""
        # 既存のアイテムをすべて削除
        for item in self._field_tree.get_children():
            self._field_tree.delete(item)

        # フィールドデータを行として挿入
        for field in self._fields:
            values = (
                field.get("field_name", ""),
                field.get("field_label", ""),
                field.get("page_number", 1),
                f"{field.get('x1', 0):.0f}",
                f"{field.get('y1', 0):.0f}",
                f"{field.get('x2', 0):.0f}",
                f"{field.get('y2', 0):.0f}",
                field.get("field_type", "text"),
            )
            # iidにフィールドIDを使用してO(1)検索を可能にする
            iid = str(field.get("id", id(field)))
            self._field_tree.insert("", tk.END, iid=iid, values=values)

    # -----------------------------------------------------------------------
    # イベントハンドラ
    # -----------------------------------------------------------------------

    def _on_form_select(self, event=None) -> None:
        """様式一覧の選択変更イベント。選択された様式の詳細を右パネルに表示する。"""
        selection = self._form_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx >= len(self._forms):
            return

        form = self._forms[idx]
        self._current_form_id = form["id"]

        # 右パネルの入力欄を更新
        self._form_name_var.set(form.get("name", ""))
        self._form_desc_var.set(form.get("description", ""))

        # フィールド一覧を読み込む
        self._load_fields(self._current_form_id)
        self.status_callback(f"様式「{form['name']}」を選択しました（{len(self._fields)}フィールド）")

    def _on_create_form(self) -> None:
        """「新規作成」ボタン: 様式名入力後に新しい様式をDBに作成する。"""
        name = simpledialog.askstring(
            "新規様式作成",
            "様式名を入力してください:",
            parent=self,
        )
        if not name or not name.strip():
            return

        name = name.strip()

        if self.db_manager:
            try:
                new_id = self.db_manager.create_form(name=name)
                logger.info(f"様式を作成しました: id={new_id}, name={name}")
                self.status_callback(f"様式「{name}」を作成しました")
            except Exception as e:
                logger.error(f"様式作成に失敗: {e}")
                messagebox.showerror("エラー", f"様式の作成に失敗しました。\n{e}", parent=self)
                return
        else:
            # デモモード: ローカルにのみ追加
            new_id = max((f["id"] for f in self._forms), default=0) + 1
            self._forms.append({"id": new_id, "name": name, "description": ""})
            self._form_listbox.insert(tk.END, name)
            self.status_callback(f"様式「{name}」を作成しました（デモモード）")
            return

        # 一覧を再読み込みして選択
        self._load_forms()
        # 新規作成した様式を選択状態にする
        for i, form in enumerate(self._forms):
            if form["id"] == new_id:
                self._form_listbox.selection_set(i)
                self._form_listbox.see(i)
                self._on_form_select()
                break

    def _on_delete_form(self) -> None:
        """「削除」ボタン: 選択中の様式を削除する（確認ダイアログ付き）。"""
        selection = self._form_listbox.curselection()
        if not selection:
            messagebox.showinfo("確認", "削除する様式を選択してください。", parent=self)
            return

        idx = selection[0]
        form = self._forms[idx]

        if not messagebox.askyesno(
            "削除確認",
            f"様式「{form['name']}」を削除しますか？\n"
            "関連するフィールド定義・OCR結果もすべて削除されます。",
            icon=messagebox.WARNING,
            parent=self,
        ):
            return

        if self.db_manager:
            try:
                self.db_manager.delete_form(form["id"])
                logger.info(f"様式を削除しました: id={form['id']}")
            except Exception as e:
                logger.error(f"様式削除に失敗: {e}")
                messagebox.showerror("エラー", f"様式の削除に失敗しました。\n{e}", parent=self)
                return

        # 右パネルをクリア
        self._current_form_id = None
        self._form_name_var.set("")
        self._form_desc_var.set("")
        self._fields = []
        self._refresh_field_tree()

        # 一覧を再読み込み
        self._load_forms()
        self.status_callback(f"様式「{form['name']}」を削除しました")

    def _on_save_form(self) -> None:
        """「保存」ボタン: 様式名・説明をDBに保存する。"""
        name = self._form_name_var.get().strip()
        if not name:
            messagebox.showwarning("入力エラー", "様式名を入力してください。", parent=self)
            return

        if self._current_form_id is None:
            messagebox.showinfo("確認", "保存する様式を選択してください。", parent=self)
            return

        desc = self._form_desc_var.get().strip()

        if self.db_manager:
            try:
                self.db_manager.update_form(self._current_form_id, name=name, description=desc)
                logger.info(f"様式を更新しました: id={self._current_form_id}")
            except Exception as e:
                logger.error(f"様式更新に失敗: {e}")
                messagebox.showerror("エラー", f"様式の保存に失敗しました。\n{e}", parent=self)
                return
        else:
            # デモモード
            for form in self._forms:
                if form["id"] == self._current_form_id:
                    form["name"] = name
                    form["description"] = desc
                    break

        # Listboxの表示を更新
        self._load_forms()
        self.status_callback(f"様式「{name}」を保存しました")
        messagebox.showinfo("完了", "様式を保存しました。", parent=self)

    def _on_add_field(self) -> None:
        """「フィールド追加」ボタン: フィールド編集ダイアログを開いて新規フィールドを追加する。"""
        if self._current_form_id is None:
            messagebox.showinfo("確認", "フィールドを追加する様式を先に選択してください。", parent=self)
            return

        dialog = FieldEditDialog(self)
        self.wait_window(dialog)

        if dialog.result is None:
            return

        field_data = dialog.result
        # 並び順はフィールド数を元に設定
        field_data["order_index"] = len(self._fields)

        if self.db_manager:
            try:
                field_id = self.db_manager.save_form_field(self._current_form_id, field_data)
                field_data["id"] = field_id
                logger.info(f"フィールドを追加しました: id={field_id}")
            except Exception as e:
                logger.error(f"フィールド追加に失敗: {e}")
                messagebox.showerror("エラー", f"フィールドの追加に失敗しました。\n{e}", parent=self)
                return
        else:
            # デモモード
            field_data["id"] = max((f.get("id", 0) for f in self._fields), default=0) + 1
            field_data["form_id"] = self._current_form_id

        self._fields.append(field_data)
        self._refresh_field_tree()
        self.status_callback(f"フィールド「{field_data['field_label']}」を追加しました")

    def _on_delete_field(self) -> None:
        """「フィールド削除」ボタン: 選択中のフィールドを削除する。"""
        selection = self._field_tree.selection()
        if not selection:
            messagebox.showinfo("確認", "削除するフィールドを選択してください。", parent=self)
            return

        iid = selection[0]
        # フィールドIDはiidとして保存されている
        field = next((f for f in self._fields if str(f.get("id", id(f))) == iid), None)
        if field is None:
            return

        if not messagebox.askyesno(
            "削除確認",
            f"フィールド「{field.get('field_label', field.get('field_name', ''))}」を削除しますか？",
            parent=self,
        ):
            return

        if self.db_manager and field.get("id"):
            try:
                self.db_manager.delete_form_field(field["id"])
            except Exception as e:
                logger.error(f"フィールド削除に失敗: {e}")
                messagebox.showerror("エラー", f"フィールドの削除に失敗しました。\n{e}", parent=self)
                return

        self._fields = [f for f in self._fields if str(f.get("id", id(f))) != iid]
        self._refresh_field_tree()
        self.status_callback("フィールドを削除しました")

    def _on_field_double_click(self, event=None) -> None:
        """フィールドTreeviewのダブルクリック: 選択フィールドを編集する。"""
        selection = self._field_tree.selection()
        if not selection:
            return

        iid = selection[0]
        field = next((f for f in self._fields if str(f.get("id", id(f))) == iid), None)
        if field is None:
            return

        dialog = FieldEditDialog(self, field_data=field.copy())
        self.wait_window(dialog)

        if dialog.result is None:
            return

        updated = dialog.result

        if self.db_manager and field.get("id"):
            try:
                self.db_manager.save_form_field(self._current_form_id, updated)
            except Exception as e:
                logger.error(f"フィールド更新に失敗: {e}")
                messagebox.showerror("エラー", f"フィールドの更新に失敗しました。\n{e}", parent=self)
                return

        # ローカルデータを更新
        for i, f in enumerate(self._fields):
            if str(f.get("id", id(f))) == iid:
                self._fields[i] = updated
                break

        self._refresh_field_tree()
        self.status_callback(f"フィールド「{updated['field_label']}」を更新しました")

    def _on_open_field_editor(self) -> None:
        """
        「テンプレート画像で領域設定」ボタン: FieldEditorDialogを開く。

        FieldEditorDialogでの作業結果（フィールド一覧）を受け取り、
        DBへ一括保存してTreeviewを更新する。
        """
        if self._current_form_id is None:
            messagebox.showinfo("確認", "領域を設定する様式を先に選択してください。", parent=self)
            return

        if not _FIELD_EDITOR_AVAILABLE:
            messagebox.showwarning(
                "機能未利用",
                "FieldEditorDialogモジュールが見つかりません。\n"
                "src/ui/field_editor.py が存在するか確認してください。",
                parent=self,
            )
            return

        # FieldEditorDialogを起動
        dialog = FieldEditorDialog(
            self,
            form_id=self._current_form_id,
            existing_fields=self._fields.copy(),
            db_manager=self.db_manager,
        )
        self.wait_window(dialog)

        # ダイアログで保存が行われた場合は一覧を再読み込み
        if dialog.saved:
            self._load_fields(self._current_form_id)
            self.status_callback("領域設定を保存しました")

    def refresh(self) -> None:
        """
        他の画面から戻ってきたときなどに呼び出す外部向けリフレッシュメソッド。
        """
        self._load_forms()
        if self._current_form_id:
            self._load_fields(self._current_form_id)


# ---------------------------------------------------------------------------
# 単体動作確認用エントリーポイント
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("FormManagementFrame 単体起動モード（デモデータ使用）")

    root = tk.Tk()
    root.title("様式管理 - 動作確認")
    root.geometry("900x600")

    style = ttk.Style(root)
    style.theme_use("clam")

    frame = FormManagementFrame(
        root,
        db_manager=None,  # デモモード
        status_callback=lambda msg: print(f"[STATUS] {msg}"),
    )
    frame.pack(fill=tk.BOTH, expand=True)

    root.mainloop()

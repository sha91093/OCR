"""
field_editor.py - フィールド（領域）定義エディタ

担当: 木村 浩 (Hiroshi Kimura) - フロントエンド開発者
作成日: 2026-03-13

テンプレート画像（PDF/画像ファイル）をキャンバスに表示し、
マウスドラッグで読み取り領域を定義するダイアログ。

操作方法:
    - 左クリック + ドラッグ : 新規領域を矩形選択
    - 既存領域をクリック    : 選択（ハイライト表示）
    - Deleteキー           : 選択中の領域を削除
    - ダブルクリック        : 領域の名前/ラベルを編集

座標変換:
    画像は表示時にキャンバスサイズに合わせてスケーリングされるため、
    キャンバス座標を実座標に変換する際は scale_ratio を使用する。
    実座標 = キャンバス座標 / scale_ratio

低スペックPC対応:
    - 大きな画像は表示前に縮小してメモリ使用量を削減
    - PIL のサムネイル処理を使用（アスペクト比を保持）
    - Undoバッファは直近10操作までに制限
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import logging
import sys
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# プロジェクトルートをパスに追加（単体動作確認用）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Pillow のインポート（インストールされていない環境に対応）
try:
    from PIL import Image, ImageTk
    _PIL_AVAILABLE = True
except ImportError:
    logger.warning("Pillowが見つかりません。画像プレビュー機能が無効になります。")
    _PIL_AVAILABLE = False

# PyMuPDF (fitz) のインポート（PDFプレビュー用）
try:
    import fitz  # PyMuPDF
    _PYMUPDF_AVAILABLE = True
except ImportError:
    logger.info("PyMuPDFが見つかりません。PDF表示にはPillowのみ使用します。")
    _PYMUPDF_AVAILABLE = False

# DatabaseManagerのインポート
try:
    from src.core.database import DatabaseManager
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 最大表示サイズ（低スペックPC対応: これ以上大きい画像は縮小）
MAX_CANVAS_W = 900
MAX_CANVAS_H = 650

# テンプレートプレビュー時の解像度 (DPI)
# この値で PDF をラスタライズし、フィールド座標を記録する。
# OCR処理時と異なる場合は ocr_processor.py 内で座標変換が行われる。
PREVIEW_DPI = 150

# ページ画像キャッシュの上限 (ページ数)
# 低スペックPC対応: 1ページあたり約 5〜15 MB (150 DPI A4) を想定。
# 10ページ上限 ≒ 最大 150 MB 程度。
PAGE_CACHE_MAX = 10

# 矩形の描画色
RECT_COLOR_NORMAL   = "#2196F3"   # 通常の領域（青）
RECT_COLOR_SELECTED = "#F44336"   # 選択中の領域（赤）
RECT_COLOR_DRAFT    = "#4CAF50"   # ドラッグ中の新規領域（緑）
RECT_ALPHA_WIDTH    = 2           # 矩形の線幅


# ---------------------------------------------------------------------------
# 領域情報入力ダイアログ（フィールド名・ラベルを1画面で入力）
# ---------------------------------------------------------------------------

class _RegionInputDialog(tk.Toplevel):
    """
    領域のフィールド識別名と表示ラベルを1つのダイアログで入力させるカスタムダイアログ。

    FieldEditorDialog は grab_set() でモーダルになっているため、
    その上で simpledialog.askstring() を複数回呼ぶとネストモーダルになりフリーズする。
    本クラスは両入力を1画面に統合し、親の grab を一時解放してから自身の grab を
    取得することで競合を回避する。
    """

    def __init__(
        self,
        parent: tk.Toplevel,
        title: str,
        name_init: str = "",
        label_init: str = "",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self._parent = parent

        self.result_name: Optional[str] = None
        self.result_label: Optional[str] = None

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="フィールド識別名（英数字）:").grid(row=0, column=0, sticky=tk.W, pady=(0, 2))
        ttk.Label(frm, text="例: name, address, date_of_birth", foreground="gray").grid(
            row=1, column=0, sticky=tk.W, pady=(0, 6))
        self._name_var = tk.StringVar(value=name_init)
        name_entry = ttk.Entry(frm, textvariable=self._name_var, width=36)
        name_entry.grid(row=2, column=0, sticky=tk.EW, pady=(0, 10))

        ttk.Label(frm, text="表示ラベル:").grid(row=3, column=0, sticky=tk.W, pady=(0, 2))
        ttk.Label(frm, text="例: 氏名, 住所, 生年月日", foreground="gray").grid(
            row=4, column=0, sticky=tk.W, pady=(0, 6))
        self._label_var = tk.StringVar(value=label_init or name_init)
        label_entry = ttk.Entry(frm, textvariable=self._label_var, width=36)
        label_entry.grid(row=5, column=0, sticky=tk.EW, pady=(0, 12))

        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=6, column=0, sticky=tk.E)
        ttk.Button(btn_frm, text="キャンセル", command=self._on_cancel).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_frm, text="OK", command=self._on_ok).pack(side=tk.RIGHT)

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())

        # ウィンドウを親の中央に配置
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, px)}+{max(0, py)}")

        # 親の grab を一時解放してから自身の grab を取得（ネストモーダル競合を回避）
        try:
            parent.grab_release()
        except tk.TclError:
            pass
        self.grab_set()
        name_entry.focus_set()
        self.wait_window()
        # ダイアログが閉じた後、親の grab を復元する
        try:
            parent.grab_set()
        except tk.TclError:
            pass

    def _on_ok(self) -> None:
        self.result_name = self._name_var.get().strip()
        self.result_label = self._label_var.get().strip()
        self.destroy()

    def _on_cancel(self) -> None:
        self.destroy()


# ---------------------------------------------------------------------------
# フィールド領域定義ダイアログ
# ---------------------------------------------------------------------------

class FieldEditorDialog(tk.Toplevel):
    """
    テンプレート画像上でフィールド領域をマウス操作で定義するダイアログ。

    Attributes:
        form_id:         対象様式のID
        existing_fields: 既存フィールドデータのリスト
        db_manager:      DatabaseManagerインスタンス
        saved:           保存が実行されたかどうかのフラグ

        _pil_image:      現在表示中のPIL.Imageオブジェクト（元サイズ）
        _photo_image:    TkのPhotoImageオブジェクト（スケーリング済み）
        _scale_ratio:    キャンバス表示時のスケーリング比率（実座標換算に使用）
        _current_page:   現在表示中のページ番号（1始まり）
        _page_images:    ページ番号 -> PIL.Image のキャッシュ

        _regions:        定義済み領域リスト。各要素は dict:
                         {
                           "id":          int|None,  # DBのフィールドID（新規はNone）
                           "field_name":  str,
                           "field_label": str,
                           "page_number": int,
                           "x1": float, "y1": float,  # 実座標（元画像ピクセル）
                           "x2": float, "y2": float,
                           "field_type":  str,
                           "canvas_rect_id": int,  # Canvasアイテムのid
                           "canvas_text_id": int,  # ラベルテキストのid
                         }
        _selected_idx:   現在選択中の領域のインデックス（未選択は-1）

        # ドラッグ状態
        _drag_start_x:   ドラッグ開始X（キャンバス座標）
        _drag_start_y:   ドラッグ開始Y（キャンバス座標）
        _drag_rect_id:   ドラッグ中の仮矩形Canvas item ID
    """

    def __init__(
        self,
        parent: tk.Widget,
        form_id: int,
        existing_fields: Optional[list] = None,
        db_manager=None,
    ):
        """
        Args:
            parent:          親ウィジェット
            form_id:         対象様式のID
            existing_fields: 既存フィールドデータのリスト（編集開始時に表示）
            db_manager:      DatabaseManagerインスタンス
        """
        super().__init__(parent)
        self.title("テンプレート画像で領域設定")
        self.form_id = form_id
        self.db_manager = db_manager
        self.saved = False  # 保存完了フラグ

        # ウィンドウサイズ
        self.geometry("1100x750")
        self.minsize(800, 600)

        # 状態変数の初期化
        self._pil_image: Optional[object] = None  # PIL.Image
        self._photo_image: Optional[object] = None  # ImageTk.PhotoImage
        self._scale_ratio: float = 1.0
        self._current_page: int = 1
        self._page_count: int = 1
        # ページ画像キャッシュ (OrderedDict で LRU 管理)
        # PAGE_CACHE_MAX を超えた場合は最も古いページを自動解放してメモリを節約する。
        from collections import OrderedDict
        self._page_images: OrderedDict[int, object] = OrderedDict()
        self._pdf_doc = None  # PyMuPDFドキュメント

        # 領域データ
        self._regions: list[dict] = []
        self._selected_idx: int = -1

        # ドラッグ状態
        self._drag_start_x: int = 0
        self._drag_start_y: int = 0
        self._drag_rect_id: Optional[int] = None
        self._is_dragging: bool = False

        # 既存フィールドを領域データに変換
        for field in (existing_fields or []):
            region = {
                "id":            field.get("id"),
                "field_name":    field.get("field_name", ""),
                "field_label":   field.get("field_label", ""),
                "page_number":   field.get("page_number", 1),
                "x1":            float(field.get("x1", 0)),
                "y1":            float(field.get("y1", 0)),
                "x2":            float(field.get("x2", 0)),
                "y2":            float(field.get("y2", 0)),
                "field_type":    field.get("field_type", "text"),
                "order_index":   field.get("order_index", 0),
                "canvas_rect_id": None,
                "canvas_text_id": None,
            }
            self._regions.append(region)

        self._build_ui()

        # キーボードショートカット
        self.bind("<Delete>",  self._on_key_delete)
        self.bind("<Escape>",  lambda e: self._deselect_all())

        # ダイアログをモーダルに設定
        self.grab_set()
        self.focus_set()

        # ウィンドウを親の中央に配置
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, px)}+{max(0, py)}")

    def _build_ui(self) -> None:
        """ダイアログUIを構築する。"""
        # ---- ツールバー（上部）----
        toolbar = ttk.Frame(self, padding=(6, 4))
        toolbar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(
            toolbar, text="ファイルを開く", command=self._on_open_file
        ).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=4
        )

        # ページ切り替え
        ttk.Label(toolbar, text="ページ:").pack(side=tk.LEFT)
        self._page_var = tk.IntVar(value=1)
        self._page_spin = ttk.Spinbox(
            toolbar,
            textvariable=self._page_var,
            from_=1,
            to=999,
            width=4,
            command=self._on_page_change,
        )
        self._page_spin.pack(side=tk.LEFT, padx=(2, 0))
        self._page_count_label = ttk.Label(toolbar, text="/ 1")
        self._page_count_label.pack(side=tk.LEFT, padx=(2, 6))

        ttk.Button(
            toolbar, text="前ページ", command=self._prev_page
        ).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(
            toolbar, text="次ページ", command=self._next_page
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=4
        )

        # 操作ヒント
        ttk.Label(
            toolbar,
            text="ドラッグで領域選択  |  クリックで選択  |  Deleteキーで削除",
            foreground="#666666",
            font=("", 9),
        ).pack(side=tk.LEFT, padx=8)

        # 保存・閉じるボタン（右端）
        ttk.Button(
            toolbar, text="閉じる", command=self.destroy
        ).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(
            toolbar, text="保存", command=self._on_save
        ).pack(side=tk.RIGHT, padx=(0, 4))

        # ---- メインエリア（キャンバス | 領域リスト）----
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # キャンバスエリア
        canvas_outer = self._build_canvas_area(paned)
        paned.add(canvas_outer, weight=4)

        # 領域リストパネル
        list_panel = self._build_region_list_panel(paned)
        paned.add(list_panel, weight=1)

        # ---- ステータスバー ----
        self._status_var = tk.StringVar(value="ファイルを開いてください")
        ttk.Label(
            self,
            textvariable=self._status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=(4, 2),
        ).pack(side=tk.BOTTOM, fill=tk.X)

    def _build_canvas_area(self, parent: tk.Widget) -> ttk.Frame:
        """
        画像表示キャンバスエリアを構築する。

        スクロールバー付きのキャンバスで、
        大きな画像も縦横スクロールで確認できる。
        """
        frame = ttk.Frame(parent)

        # スクロールバー
        v_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        h_scroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL)

        # キャンバス本体
        self._canvas = tk.Canvas(
            frame,
            bg="#888888",  # 背景をグレーにして画像の境界を視認しやすく
            cursor="crosshair",
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set,
        )
        v_scroll.configure(command=self._canvas.yview)
        h_scroll.configure(command=self._canvas.xview)

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # マウスイベントをバインド
        self._canvas.bind("<ButtonPress-1>",   self._on_mouse_press)
        self._canvas.bind("<B1-Motion>",       self._on_mouse_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_mouse_release)
        self._canvas.bind("<Double-Button-1>", self._on_mouse_double_click)

        return frame

    def _build_region_list_panel(self, parent: tk.Widget) -> ttk.Frame:
        """領域リストパネルを構築する。"""
        frame = ttk.LabelFrame(parent, text="定義済み領域", padding=6)

        # Treeview（領域一覧）
        cols = ("label", "page", "coords")
        self._region_tree = ttk.Treeview(
            frame,
            columns=cols,
            show="headings",
            selectmode="browse",
            height=18,
        )
        self._region_tree.heading("label",  text="ラベル")
        self._region_tree.heading("page",   text="P")
        self._region_tree.heading("coords", text="座標")
        self._region_tree.column("label",  width=90,  minwidth=60)
        self._region_tree.column("page",   width=30,  minwidth=30)
        self._region_tree.column("coords", width=100, minwidth=80)

        tree_scroll = ttk.Scrollbar(
            frame, orient=tk.VERTICAL, command=self._region_tree.yview
        )
        self._region_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._region_tree.pack(fill=tk.BOTH, expand=True)

        # 選択変更でキャンバスの選択状態も同期
        self._region_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # ボタン
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(
            btn_frame, text="編集", command=self._on_edit_region
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(
            btn_frame, text="削除", command=self._on_delete_region_from_list
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

        return frame

    # -----------------------------------------------------------------------
    # ファイル操作
    # -----------------------------------------------------------------------

    def _on_open_file(self) -> None:
        """ファイルを開くダイアログ。PDF・画像ファイルに対応。"""
        filetypes = [
            ("対応ファイル", "*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
            ("PDFファイル", "*.pdf"),
            ("画像ファイル", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
            ("すべてのファイル", "*.*"),
        ]
        path = filedialog.askopenfilename(
            parent=self,
            title="テンプレートファイルを選択",
            filetypes=filetypes,
        )
        if not path:
            return

        self._load_file(Path(path))

    def _load_file(self, file_path: Path) -> None:
        """
        ファイルを読み込んでキャンバスに表示する。

        PDFの場合はPyMuPDFで各ページをレンダリングし、
        画像ファイルの場合はPillowで直接読み込む。

        Args:
            file_path: 読み込むファイルのパス
        """
        if not _PIL_AVAILABLE:
            messagebox.showwarning(
                "機能無効",
                "Pillowがインストールされていないため画像を表示できません。\n"
                "pip install Pillow でインストールしてください。",
                parent=self,
            )
            return

        suffix = file_path.suffix.lower()
        self._page_images = {}
        self._pdf_doc = None

        try:
            if suffix == ".pdf":
                self._load_pdf(file_path)
            else:
                self._load_image(file_path)
        except Exception as e:
            logger.error(f"ファイル読み込みに失敗: {e}")
            messagebox.showerror(
                "ファイル読み込みエラー",
                f"ファイルの読み込みに失敗しました。\n\nファイル: {file_path.name}\n原因: {e}",
                parent=self,
            )
            return

        # ページ操作UIを更新
        self._page_count_label.configure(text=f"/ {self._page_count}")
        self._page_spin.configure(to=self._page_count)
        self._current_page = 1
        self._page_var.set(1)

        # 最初のページを表示
        self._show_page(1)

        # 既存の領域を再描画（現在ページのみ）
        self._redraw_all_regions()

        self._status_var.set(
            f"読み込み完了: {file_path.name}  ({self._page_count}ページ)"
        )

    def _load_pdf(self, file_path: Path) -> None:
        """PDFファイルをロードしてページ数を確定する。"""
        if _PYMUPDF_AVAILABLE:
            import fitz
            self._pdf_doc = fitz.open(str(file_path))
            self._page_count = len(self._pdf_doc)
            logger.info(f"PDFを読み込みました: {file_path.name} ({self._page_count}ページ)")
        elif _PIL_AVAILABLE:
            # PyMuPDFがない場合はPillowでPDFの最初のページのみ表示
            try:
                img = Image.open(str(file_path))
                self._page_images[1] = img
                self._page_count = 1
                logger.warning("PyMuPDFがないためPDFの最初のページのみ表示します")
            except Exception:
                raise RuntimeError(
                    "PDFを開くには PyMuPDF が必要です。\n"
                    "pip install pymupdf でインストールしてください。"
                )
        else:
            raise RuntimeError("PDFを表示するためのライブラリがありません。")

    def _load_image(self, file_path: Path) -> None:
        """画像ファイルを読み込む（PIL使用）。"""
        img = Image.open(str(file_path))
        self._page_images[1] = img.copy()  # RGBに変換して保持
        self._page_count = 1
        logger.info(f"画像を読み込みました: {file_path.name} ({img.size})")

    def _get_page_image(self, page_num: int):
        """
        指定ページのPIL.Imageを返す。キャッシュがあれば返し、
        なければレンダリング（PDF）または変換（画像）する。

        Args:
            page_num: ページ番号（1始まり）

        Returns:
            PIL.Image または None
        """
        if page_num in self._page_images:
            # LRU: 参照されたページを末尾（最近使用）に移動
            self._page_images.move_to_end(page_num)
            return self._page_images[page_num]

        if self._pdf_doc is not None and _PYMUPDF_AVAILABLE:
            import fitz
            # PREVIEW_DPI で PDF をラスタライズする。
            # PyMuPDF のベースDPIは 72 DPI なので scale = PREVIEW_DPI / 72。
            _scale = PREVIEW_DPI / 72.0
            page = self._pdf_doc[page_num - 1]
            mat = fitz.Matrix(_scale, _scale)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            self._page_images[page_num] = img
            # キャッシュ上限チェック: 古いページ（先頭）を解放してメモリを節約
            while len(self._page_images) > PAGE_CACHE_MAX:
                evicted_page, _ = self._page_images.popitem(last=False)
                logger.debug(f"ページキャッシュを解放しました: page={evicted_page}")
            return img

        return None

    def _show_page(self, page_num: int) -> None:
        """
        指定ページをキャンバスに表示する。

        表示時にキャンバスサイズに合わせてスケーリングし、
        スケーリング比率を self._scale_ratio に保存する。

        Args:
            page_num: 表示するページ番号（1始まり）
        """
        img = self._get_page_image(page_num)
        if img is None:
            self._status_var.set(f"ページ {page_num} の画像を取得できませんでした")
            return

        # キャンバスサイズを取得（初回は更新が必要）
        self._canvas.update_idletasks()
        canvas_w = self._canvas.winfo_width() or MAX_CANVAS_W
        canvas_h = self._canvas.winfo_height() or MAX_CANVAS_H

        # アスペクト比を保持してスケーリング
        img_w, img_h = img.size
        scale_w = canvas_w / img_w
        scale_h = canvas_h / img_h
        self._scale_ratio = min(scale_w, scale_h, 1.0)  # 1.0を超えない（拡大しない）

        new_w = int(img_w * self._scale_ratio)
        new_h = int(img_h * self._scale_ratio)

        # 縮小処理（LANCZOS = 高品質だが低スペックでも許容できる速度）
        if self._scale_ratio < 1.0:
            scaled = img.resize((new_w, new_h), Image.LANCZOS)
        else:
            scaled = img

        # RGB変換（RGBA等への対応）
        if scaled.mode != "RGB":
            scaled = scaled.convert("RGB")

        self._pil_image = img
        self._photo_image = ImageTk.PhotoImage(scaled)

        # キャンバスに画像を描画
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor=tk.NW, image=self._photo_image, tags="image")
        self._canvas.configure(scrollregion=(0, 0, new_w, new_h))

        self._current_page = page_num

    # -----------------------------------------------------------------------
    # ページ操作
    # -----------------------------------------------------------------------

    def _on_page_change(self) -> None:
        """ページ番号入力変更イベント。"""
        try:
            page = int(self._page_var.get())
        except (tk.TclError, ValueError):
            return
        page = max(1, min(page, self._page_count))
        self._page_var.set(page)
        self._show_page(page)
        self._redraw_all_regions()

    def _prev_page(self) -> None:
        """前ページに移動する。"""
        if self._current_page > 1:
            self._current_page -= 1
            self._page_var.set(self._current_page)
            self._show_page(self._current_page)
            self._redraw_all_regions()

    def _next_page(self) -> None:
        """次ページに移動する。"""
        if self._current_page < self._page_count:
            self._current_page += 1
            self._page_var.set(self._current_page)
            self._show_page(self._current_page)
            self._redraw_all_regions()

    # -----------------------------------------------------------------------
    # 座標変換ユーティリティ
    # -----------------------------------------------------------------------

    def _canvas_to_real(self, cx: float, cy: float) -> tuple[float, float]:
        """
        キャンバス座標を実座標（元画像ピクセル）に変換する。

        Args:
            cx: キャンバスX座標
            cy: キャンバスY座標

        Returns:
            (real_x, real_y): 元画像ピクセル座標
        """
        if self._scale_ratio <= 0:
            return cx, cy
        return cx / self._scale_ratio, cy / self._scale_ratio

    def _real_to_canvas(self, rx: float, ry: float) -> tuple[float, float]:
        """
        実座標（元画像ピクセル）をキャンバス座標に変換する。

        Args:
            rx: 実X座標
            ry: 実Y座標

        Returns:
            (canvas_x, canvas_y)
        """
        return rx * self._scale_ratio, ry * self._scale_ratio

    # -----------------------------------------------------------------------
    # マウスイベント（矩形描画）
    # -----------------------------------------------------------------------

    def _on_mouse_press(self, event) -> None:
        """
        マウス左ボタン押下。
        既存領域のクリック選択、または新規領域ドラッグの開始を判定する。
        """
        cx, cy = self._canvas.canvasx(event.x), self._canvas.canvasy(event.y)

        # 既存の領域をクリックしたか確認
        clicked_idx = self._find_region_at(cx, cy)
        if clicked_idx >= 0:
            self._select_region(clicked_idx)
            self._is_dragging = False
            return

        # 新規ドラッグ開始
        self._deselect_all()
        self._drag_start_x = cx
        self._drag_start_y = cy
        self._is_dragging = True

        # ドラッグ中の仮矩形を作成
        self._drag_rect_id = self._canvas.create_rectangle(
            cx, cy, cx, cy,
            outline=RECT_COLOR_DRAFT,
            width=RECT_ALPHA_WIDTH,
            dash=(4, 2),
            tags="draft",
        )

    def _on_mouse_drag(self, event) -> None:
        """マウスドラッグ中: 仮矩形のサイズをリアルタイム更新する。"""
        if not self._is_dragging or self._drag_rect_id is None:
            return

        cx = self._canvas.canvasx(event.x)
        cy = self._canvas.canvasy(event.y)

        self._canvas.coords(
            self._drag_rect_id,
            self._drag_start_x, self._drag_start_y,
            cx, cy,
        )

        # ステータスバーに現在のサイズを表示
        rx1, ry1 = self._canvas_to_real(
            min(self._drag_start_x, cx),
            min(self._drag_start_y, cy),
        )
        rx2, ry2 = self._canvas_to_real(
            max(self._drag_start_x, cx),
            max(self._drag_start_y, cy),
        )
        w = rx2 - rx1
        h = ry2 - ry1
        self._status_var.set(
            f"選択中: ({rx1:.0f}, {ry1:.0f}) - ({rx2:.0f}, {ry2:.0f})  "
            f"サイズ: {w:.0f} x {h:.0f} px"
        )

    def _on_mouse_release(self, event) -> None:
        """
        マウスボタンリリース。
        ドラッグで選択した矩形が有効サイズ以上なら
        フィールド名入力ダイアログを開いて新規領域として追加する。
        """
        if not self._is_dragging:
            return
        self._is_dragging = False

        # 仮矩形を削除
        if self._drag_rect_id is not None:
            self._canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None

        cx_end = self._canvas.canvasx(event.x)
        cy_end = self._canvas.canvasy(event.y)

        # 最小サイズチェック（小さすぎる選択は無視）
        min_px = 5
        if (abs(cx_end - self._drag_start_x) < min_px or
                abs(cy_end - self._drag_start_y) < min_px):
            self._status_var.set("領域が小さすぎます。もう少し大きくドラッグしてください。")
            return

        # 実座標に変換（左上/右下を正規化）
        x1_c = min(self._drag_start_x, cx_end)
        y1_c = min(self._drag_start_y, cy_end)
        x2_c = max(self._drag_start_x, cx_end)
        y2_c = max(self._drag_start_y, cy_end)

        rx1, ry1 = self._canvas_to_real(x1_c, y1_c)
        rx2, ry2 = self._canvas_to_real(x2_c, y2_c)

        # フィールド情報を入力させる（after で呼ぶことでマウスイベント処理が完了してから開く）
        self.after(10, lambda: self._prompt_add_region(rx1, ry1, rx2, ry2))

    def _on_mouse_double_click(self, event) -> None:
        """ダブルクリック: 既存領域の名前・ラベルを編集する。"""
        cx = self._canvas.canvasx(event.x)
        cy = self._canvas.canvasy(event.y)
        idx = self._find_region_at(cx, cy)
        if idx >= 0:
            self._edit_region(idx)

    # -----------------------------------------------------------------------
    # 領域管理
    # -----------------------------------------------------------------------

    def _find_region_at(self, cx: float, cy: float) -> int:
        """
        指定キャンバス座標に存在する領域のインデックスを返す。

        複数の領域が重なっている場合は後から追加された（インデックスが大きい）
        ものを優先する。

        Args:
            cx: キャンバスX座標
            cy: キャンバスY座標

        Returns:
            int: 見つかった領域のインデックス。見つからない場合は -1。
        """
        # 現在表示中のページの領域のみ検索
        for i in range(len(self._regions) - 1, -1, -1):
            region = self._regions[i]
            if region["page_number"] != self._current_page:
                continue
            # キャンバス座標に変換して当たり判定
            cx1, cy1 = self._real_to_canvas(region["x1"], region["y1"])
            cx2, cy2 = self._real_to_canvas(region["x2"], region["y2"])
            if cx1 <= cx <= cx2 and cy1 <= cy <= cy2:
                return i
        return -1

    def _prompt_add_region(
        self,
        x1: float, y1: float,
        x2: float, y2: float,
    ) -> None:
        """
        新規領域のフィールド名・ラベルを入力するダイアログを表示し、
        入力内容をもとに領域を追加する。

        Args:
            x1, y1, x2, y2: 実座標（元画像ピクセル）
        """
        # フィールド識別名と表示ラベルをまとめて1つのダイアログで入力
        dlg = _RegionInputDialog(self, "フィールド情報の入力")
        name = dlg.result_name
        label = dlg.result_label
        if not name:
            return
        if not label:
            label = name

        # 新規領域データを追加
        region = {
            "id":            None,
            "field_name":    name,
            "field_label":   label,
            "page_number":   self._current_page,
            "x1":            x1,
            "y1":            y1,
            "x2":            x2,
            "y2":            y2,
            "field_type":    "text",
            "order_index":   len(self._regions),
            "canvas_rect_id": None,
            "canvas_text_id": None,
        }
        self._regions.append(region)
        idx = len(self._regions) - 1

        # キャンバスに描画
        self._draw_region(idx)

        # 領域リストを更新
        self._refresh_region_tree()

        # 追加した領域を選択状態に
        self._select_region(idx)

        self._status_var.set(
            f"領域「{label}」を追加しました "
            f"({x1:.0f}, {y1:.0f}) - ({x2:.0f}, {y2:.0f})"
        )

    def _draw_region(self, idx: int) -> None:
        """
        指定インデックスの領域をキャンバスに描画する。

        現在のページと異なるページの領域は描画しない。

        Args:
            idx: _regionsリストのインデックス
        """
        if idx < 0 or idx >= len(self._regions):
            return

        region = self._regions[idx]

        # 現在ページ以外はスキップ
        if region["page_number"] != self._current_page:
            return

        # キャンバス座標に変換
        cx1, cy1 = self._real_to_canvas(region["x1"], region["y1"])
        cx2, cy2 = self._real_to_canvas(region["x2"], region["y2"])

        color = RECT_COLOR_SELECTED if idx == self._selected_idx else RECT_COLOR_NORMAL

        # 既存の描画を削除してから再描画
        if region.get("canvas_rect_id"):
            self._canvas.delete(region["canvas_rect_id"])
        if region.get("canvas_text_id"):
            self._canvas.delete(region["canvas_text_id"])

        # 矩形を描画
        rect_id = self._canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline=color,
            width=RECT_ALPHA_WIDTH,
            tags=f"region_{idx}",
        )

        # ラベルテキストを描画（左上角）
        text_id = self._canvas.create_text(
            cx1 + 3, cy1 + 2,
            text=region["field_label"],
            fill=color,
            anchor=tk.NW,
            font=("", 9),
            tags=f"region_label_{idx}",
        )

        # IDを保存
        region["canvas_rect_id"] = rect_id
        region["canvas_text_id"] = text_id

    def _redraw_all_regions(self) -> None:
        """
        現在ページの全領域をキャンバスに再描画する。
        ページ切り替え時などに呼び出す。
        """
        # 全領域の描画情報をリセット（他ページのキャンバスIDが残らないよう）
        for region in self._regions:
            region["canvas_rect_id"] = None
            region["canvas_text_id"] = None

        # 既存の領域描画をすべて削除
        self._canvas.delete("region")

        # 現在ページの領域を再描画
        for i in range(len(self._regions)):
            self._draw_region(i)

        # 領域リストも更新（全ページ分）
        self._refresh_region_tree()

    def _select_region(self, idx: int) -> None:
        """
        指定インデックスの領域を選択状態にする。

        以前の選択領域は通常色に戻す。

        Args:
            idx: 選択する領域のインデックス
        """
        old_idx = self._selected_idx

        # 以前の選択を解除
        if old_idx >= 0 and old_idx < len(self._regions):
            self._selected_idx = -1
            self._draw_region(old_idx)

        # 新しい選択
        self._selected_idx = idx
        self._draw_region(idx)

        # 領域リストの選択も同期
        iid = str(idx)
        if iid in self._region_tree.get_children():
            self._region_tree.selection_set(iid)
            self._region_tree.see(iid)

        region = self._regions[idx]
        self._status_var.set(
            f"選択: 「{region['field_label']}」 ページ{region['page_number']}  "
            f"({region['x1']:.0f}, {region['y1']:.0f}) - ({region['x2']:.0f}, {region['y2']:.0f})"
        )

    def _deselect_all(self) -> None:
        """現在の選択を解除する。"""
        if self._selected_idx >= 0:
            old = self._selected_idx
            self._selected_idx = -1
            self._draw_region(old)
        self._region_tree.selection_remove(self._region_tree.selection())

    def _edit_region(self, idx: int) -> None:
        """
        領域のフィールド名・ラベルを編集するダイアログを開く。

        Args:
            idx: _regionsリストのインデックス
        """
        if idx < 0 or idx >= len(self._regions):
            return

        region = self._regions[idx]

        dlg = _RegionInputDialog(
            self, "フィールド情報の変更",
            name_init=region["field_name"],
            label_init=region["field_label"],
        )
        if dlg.result_name is None:
            return
        name = dlg.result_name or region["field_name"]
        label = dlg.result_label or region["field_label"]

        region["field_name"] = name
        region["field_label"] = label
        self._draw_region(idx)
        self._refresh_region_tree()

    def _delete_region(self, idx: int) -> None:
        """
        指定インデックスの領域を削除する。

        Args:
            idx: _regionsリストのインデックス
        """
        if idx < 0 or idx >= len(self._regions):
            return

        region = self._regions[idx]

        # キャンバスから削除
        if region.get("canvas_rect_id"):
            self._canvas.delete(region["canvas_rect_id"])
        if region.get("canvas_text_id"):
            self._canvas.delete(region["canvas_text_id"])

        label = region.get("field_label", "")
        del self._regions[idx]
        self._selected_idx = -1

        # 残りの領域を全て再描画（インデックスが変わるため）
        for remaining in self._regions:
            remaining["canvas_rect_id"] = None
            remaining["canvas_text_id"] = None
        self._redraw_all_regions()

        self._status_var.set(f"領域「{label}」を削除しました")

    # -----------------------------------------------------------------------
    # 領域リストイベント
    # -----------------------------------------------------------------------

    def _refresh_region_tree(self) -> None:
        """領域リストTreeviewを更新する（全ページ分を表示）。"""
        for item in self._region_tree.get_children():
            self._region_tree.delete(item)

        for i, region in enumerate(self._regions):
            coords = (
                f"{region['x1']:.0f},{region['y1']:.0f},"
                f"{region['x2']:.0f},{region['y2']:.0f}"
            )
            self._region_tree.insert(
                "", tk.END,
                iid=str(i),
                values=(region["field_label"], region["page_number"], coords),
            )

    def _on_tree_select(self, event=None) -> None:
        """領域リストの選択変更: キャンバスの選択状態も同期する。"""
        selection = self._region_tree.selection()
        if not selection:
            return
        try:
            idx = int(selection[0])
        except (ValueError, IndexError):
            return

        if idx >= len(self._regions):
            return

        # 対象領域のページに移動
        region = self._regions[idx]
        if region["page_number"] != self._current_page:
            self._current_page = region["page_number"]
            self._page_var.set(self._current_page)
            self._show_page(self._current_page)
            self._redraw_all_regions()

        self._select_region(idx)

    def _on_edit_region(self) -> None:
        """領域リストの「編集」ボタン。"""
        selection = self._region_tree.selection()
        if not selection:
            messagebox.showinfo("確認", "編集する領域を選択してください。", parent=self)
            return
        try:
            idx = int(selection[0])
        except (ValueError, IndexError):
            return
        self._edit_region(idx)

    def _on_delete_region_from_list(self) -> None:
        """領域リストの「削除」ボタン。"""
        selection = self._region_tree.selection()
        if not selection:
            messagebox.showinfo("確認", "削除する領域を選択してください。", parent=self)
            return
        try:
            idx = int(selection[0])
        except (ValueError, IndexError):
            return

        region = self._regions[idx]
        if messagebox.askyesno(
            "削除確認",
            f"領域「{region.get('field_label', '')}」を削除しますか？",
            parent=self,
        ):
            self._delete_region(idx)

    def _on_key_delete(self, event=None) -> None:
        """Deleteキー: 選択中の領域を削除する。"""
        if self._selected_idx >= 0:
            self._delete_region(self._selected_idx)

    # -----------------------------------------------------------------------
    # 保存処理
    # -----------------------------------------------------------------------

    def _on_save(self) -> None:
        """
        「保存」ボタン: 全領域定義をDBに保存する。

        既存フィールド（idあり）は更新、新規フィールド（idなし）は挿入を行う。
        DBが利用不可の場合はローカル状態のみ更新し savedフラグをTrueにする。
        """
        if not self._regions:
            messagebox.showinfo("確認", "保存する領域が定義されていません。", parent=self)
            return

        if self.db_manager:
            try:
                for i, region in enumerate(self._regions):
                    field_data = {
                        "id":           region.get("id"),
                        "field_name":   region["field_name"],
                        "field_label":  region["field_label"],
                        "page_number":  region["page_number"],
                        "x1":           region["x1"],
                        "y1":           region["y1"],
                        "x2":           region["x2"],
                        "y2":           region["y2"],
                        "field_type":   region.get("field_type", "text"),
                        "order_index":  i,
                        "template_dpi": PREVIEW_DPI,
                    }
                    saved_id = self.db_manager.save_form_field(self.form_id, field_data)
                    region["id"] = saved_id  # 新規の場合はIDを更新

                logger.info(
                    f"フィールド定義を保存しました: form_id={self.form_id}, "
                    f"{len(self._regions)}件"
                )
                self.saved = True
                messagebox.showinfo(
                    "保存完了",
                    f"{len(self._regions)}件のフィールド定義を保存しました。",
                    parent=self,
                )

            except Exception as e:
                logger.error(f"フィールド保存に失敗: {e}")
                messagebox.showerror(
                    "保存エラー",
                    f"フィールド定義の保存に失敗しました。\n\n{e}",
                    parent=self,
                )
                return
        else:
            # デモモード
            self.saved = True
            messagebox.showinfo(
                "保存完了（デモモード）",
                f"{len(self._regions)}件の領域定義をメモリに保存しました。\n"
                "（データベース未接続のため永続化されません）",
                parent=self,
            )

        self._status_var.set(f"{len(self._regions)}件のフィールド定義を保存しました")


# ---------------------------------------------------------------------------
# 単体動作確認用エントリーポイント
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("FieldEditorDialog 単体起動モード")

    if not _PIL_AVAILABLE:
        print("警告: Pillowがインストールされていません。")
        print("  pip install Pillow でインストールしてください。")

    root = tk.Tk()
    root.withdraw()  # ルートウィンドウを隠す

    # サンプルの既存フィールドデータ
    sample_fields = [
        {
            "id": 1, "form_id": 1,
            "field_name": "name", "field_label": "氏名",
            "page_number": 1,
            "x1": 100.0, "y1": 200.0, "x2": 400.0, "y2": 240.0,
            "field_type": "text", "order_index": 0,
        },
    ]

    dialog = FieldEditorDialog(
        root,
        form_id=1,
        existing_fields=sample_fields,
        db_manager=None,
    )
    root.wait_window(dialog)

    if dialog.saved:
        print(f"保存された領域数: {len(dialog._regions)}")
        for region in dialog._regions:
            print(
                f"  {region['field_label']}: "
                f"({region['x1']:.0f}, {region['y1']:.0f}) - "
                f"({region['x2']:.0f}, {region['y2']:.0f})"
            )
    else:
        print("保存はキャンセルされました")

    root.destroy()

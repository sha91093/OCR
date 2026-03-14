"""
ocr_processing.py - OCR処理画面

担当: 木村 浩 (Hiroshi Kimura) - フロントエンド開発者
作成日: 2026-03-13

ファイルを選択してOCR処理を実行する画面。
処理はバックグラウンドスレッドで実行し、
GUIのフリーズを防ぐ設計になっている。

処理の流れ:
    1. 様式を選択
    2. 処理するPDF/画像ファイルを選択（複数可）
    3. 「OCR処理実行」ボタンをクリック
    4. バックグラウンドスレッドでOCR処理が実行される
    5. ログエリアにリアルタイムでログが表示される
    6. 完了後、CSV出力オプションが利用可能になる

低スペックPC対応:
    - スレッドプールを使わず1ファイルずつ順番に処理（メモリ節約）
    - ログはScrolledTextで表示（大量ログでも表示が詰まらない）
    - 処理中はGUIの他の操作を適切に制限する
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText
import logging
import sys
import threading
import queue
import time
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

# OCREngineのインポート
try:
    from src.core.ocr_engine import OCREngine
    _OCR_ENGINE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"OCREngineのインポートに失敗: {e}")
    _OCR_ENGINE_AVAILABLE = False

# Pillowのインポート（画像読み込み用）
try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# PyMuPDF（PDF→画像変換用）
try:
    import fitz
    _PYMUPDF_AVAILABLE = True
except ImportError:
    _PYMUPDF_AVAILABLE = False


# ---------------------------------------------------------------------------
# スレッド間通信用メッセージ型
# ---------------------------------------------------------------------------

class _ProgressMsg:
    """OCR処理スレッドからGUIへ進捗を通知するメッセージ。"""
    def __init__(self, file_index: int, total: int, filename: str, log: str):
        self.file_index = file_index
        self.total = total
        self.filename = filename
        self.log = log


class _FinishMsg:
    """OCR処理スレッドからGUIへ処理完了を通知するメッセージ。"""
    def __init__(self, success_count: int, error_count: int, elapsed: float):
        self.success_count = success_count
        self.error_count = error_count
        self.elapsed = elapsed


class _ErrorMsg:
    """OCR処理スレッドからGUIへエラーを通知するメッセージ。"""
    def __init__(self, error: str):
        self.error = error


# テンプレート登録時(field_editor.py)の PREVIEW_DPI と合わせる必要がある。
# field_editor.py: PREVIEW_DPI = 150 → PyMuPDF scale = 150/72
# OCR処理でも同じDPIで描画することで座標系を一致させる。
_TEMPLATE_DPI = 150  # field_editor.py の PREVIEW_DPI と同値にすること


# ---------------------------------------------------------------------------
# OCR処理フレーム
# ---------------------------------------------------------------------------

class OCRProcessingFrame(ttk.Frame):
    """
    OCR処理実行画面のメインフレーム。

    Attributes:
        db_manager:      DatabaseManagerインスタンス
        status_callback: ステータスバー更新コールバック
        is_processing:   OCR処理中フラグ（MainWindowが参照する）

        _ocr_engine:     OCREngineインスタンス（遅延初期化）
        _msg_queue:      スレッド間通信キュー
        _worker_thread:  OCR処理バックグラウンドスレッド
        _selected_files: 処理対象ファイルパスのリスト
        _forms:          取得済み様式データリスト
    """

    def __init__(
        self,
        parent: tk.Widget,
        db_manager=None,
        status_callback: Optional[Callable[[str], None]] = None,
        navigate_callback: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.db_manager = db_manager
        self.status_callback = status_callback or (lambda msg: None)
        self.navigate_callback = navigate_callback  # 画面遷移コールバック (frame_key -> None)

        # 内部状態
        self.is_processing: bool = False
        self._ocr_engine = None
        self._msg_queue: queue.Queue = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._selected_files: list[Path] = []
        self._forms: list[dict] = []
        self._result_ids: list[int] = []  # 今回の処理で保存されたOCR結果IDリスト

        self._build_ui()
        self._load_forms()

    def _build_ui(self) -> None:
        """UIを上部（設定）・中部（実行）・下部（出力設定）の3段構成で構築する。"""
        # ---- 上部: 設定エリア ----
        top_frame = ttk.LabelFrame(self, text="処理設定", padding=8)
        top_frame.pack(fill=tk.X, padx=8, pady=(8, 4))
        self._build_settings_area(top_frame)

        # ---- 中部: 処理実行・ログ ----
        mid_frame = ttk.LabelFrame(self, text="処理実行", padding=8)
        mid_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._build_execution_area(mid_frame)

        # ---- 下部: 出力設定 ----
        bottom_frame = ttk.LabelFrame(self, text="CSV出力", padding=8)
        bottom_frame.pack(fill=tk.X, padx=8, pady=(4, 8))
        self._build_output_area(bottom_frame)

    def _build_settings_area(self, parent: tk.Widget) -> None:
        """処理設定エリア（様式選択・ファイル選択）を構築する。"""
        # 様式選択
        row1 = ttk.Frame(parent)
        row1.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(row1, text="使用する様式:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self._form_var = tk.StringVar()
        self._form_combo = ttk.Combobox(
            row1,
            textvariable=self._form_var,
            state="readonly",
            width=40,
        )
        self._form_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            row1, text="更新", command=self._load_forms, width=6
        ).pack(side=tk.LEFT, padx=(4, 0))

        # ファイル選択
        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(row2, text="処理ファイル:", width=14, anchor=tk.W).pack(side=tk.LEFT)

        file_btn_frame = ttk.Frame(row2)
        file_btn_frame.pack(side=tk.RIGHT)
        ttk.Button(
            file_btn_frame, text="ファイル追加", command=self._on_add_files
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            file_btn_frame, text="一覧クリア", command=self._on_clear_files
        ).pack(side=tk.LEFT)

        # 選択ファイル一覧（Listbox）
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.X, pady=(2, 0))

        file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self._file_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=file_scrollbar.set,
            selectmode=tk.EXTENDED,  # 複数選択可
            height=5,
            font=("", 9),
            activestyle="none",
        )
        file_scrollbar.configure(command=self._file_listbox.yview)
        file_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._file_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ファイル一覧からの削除（右クリックメニューまたはDeleteキー）
        self._file_listbox.bind("<Delete>", self._on_remove_selected_files)

        # ファイル数ラベル
        self._file_count_var = tk.StringVar(value="0 ファイル選択中")
        ttk.Label(
            parent, textvariable=self._file_count_var, font=("", 9), foreground="#666"
        ).pack(anchor=tk.W)

    def _build_execution_area(self, parent: tk.Widget) -> None:
        """処理実行エリア（実行ボタン・プログレス・ログ）を構築する。"""
        # 実行ボタン + プログレスバー
        exec_row = ttk.Frame(parent)
        exec_row.pack(fill=tk.X, pady=(0, 6))

        self._run_btn = ttk.Button(
            exec_row,
            text="OCR処理実行",
            command=self._on_run_ocr,
            width=16,
        )
        self._run_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._stop_btn = ttk.Button(
            exec_row,
            text="中止",
            command=self._on_stop_ocr,
            width=8,
            state=tk.DISABLED,
        )
        self._stop_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._goto_result_btn = ttk.Button(
            exec_row,
            text="結果確認へ →",
            command=self._on_goto_result,
            width=14,
            state=tk.DISABLED,
        )
        self._goto_result_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress_bar = ttk.Progressbar(
            exec_row,
            variable=self._progress_var,
            maximum=100.0,
            length=300,
            mode="determinate",
        )
        self._progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._progress_label_var = tk.StringVar(value="")
        ttk.Label(
            exec_row, textvariable=self._progress_label_var, width=20, font=("", 9)
        ).pack(side=tk.LEFT, padx=(4, 0))

        # ログ表示エリア（ScrolledText）
        log_label_frame = ttk.Frame(parent)
        log_label_frame.pack(fill=tk.X)
        ttk.Label(log_label_frame, text="処理ログ:", font=("", 9, "bold")).pack(
            side=tk.LEFT
        )
        ttk.Button(
            log_label_frame, text="ログクリア", command=self._clear_log, width=10
        ).pack(side=tk.RIGHT)

        self._log_text = ScrolledText(
            parent,
            height=12,
            font=("Courier", 9),
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg="#1e1e1e",    # ダークバックグラウンド（ターミナル風）
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
        )
        self._log_text.pack(fill=tk.BOTH, expand=True, pady=(2, 0))

        # ログ色タグの設定
        self._log_text.tag_configure("info",    foreground="#4ec9b0")
        self._log_text.tag_configure("success", foreground="#6fdd6f")
        self._log_text.tag_configure("warning", foreground="#dcdcaa")
        self._log_text.tag_configure("error",   foreground="#f48771")

    def _build_output_area(self, parent: tk.Widget) -> None:
        """CSV出力設定エリアを構築する。"""
        row1 = ttk.Frame(parent)
        row1.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(row1, text="出力フォルダ:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self._output_dir_var = tk.StringVar(
            value=str(Path.home() / ".ocr_shinseisho" / "export")
        )
        ttk.Entry(row1, textvariable=self._output_dir_var, width=40).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(
            row1, text="参照...", command=self._on_browse_output_dir, width=8
        ).pack(side=tk.LEFT, padx=(4, 0))

        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(row2, text="ファイル名形式:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self._filename_format_var = tk.StringVar(value="{form_name}_{date}")
        format_combo = ttk.Combobox(
            row2,
            textvariable=self._filename_format_var,
            values=[
                "{form_name}_{date}",
                "{form_name}_{datetime}",
                "ocr_result_{date}",
                "ocr_result_{datetime}",
            ],
            width=30,
        )
        format_combo.pack(side=tk.LEFT)

        ttk.Label(row2, text="  文字コード:", anchor=tk.W).pack(side=tk.LEFT)
        self._encoding_var = tk.StringVar(value="utf-8-sig")
        encoding_combo = ttk.Combobox(
            row2,
            textvariable=self._encoding_var,
            values=["utf-8-sig", "utf-8", "shift_jis"],
            width=14,
            state="readonly",
        )
        encoding_combo.pack(side=tk.LEFT, padx=(4, 0))

        row3 = ttk.Frame(parent)
        row3.pack(fill=tk.X)

        self._csv_btn = ttk.Button(
            row3,
            text="CSV出力",
            command=self._on_export_csv,
            width=12,
            state=tk.DISABLED,  # 処理完了後に有効化
        )
        self._csv_btn.pack(side=tk.LEFT)

        self._csv_status_var = tk.StringVar(value="OCR処理を実行してからCSV出力が可能です")
        ttk.Label(
            row3,
            textvariable=self._csv_status_var,
            font=("", 9),
            foreground="#666",
        ).pack(side=tk.LEFT, padx=(8, 0))

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
            # デモモード
            self._forms = [
                {"id": 1, "name": "住民票申請書（サンプル）"},
                {"id": 2, "name": "転出届（サンプル）"},
            ]

        form_names = [f["name"] for f in self._forms]
        self._form_combo["values"] = form_names
        if form_names:
            self._form_combo.current(0)

    def _get_selected_form(self) -> Optional[dict]:
        """現在選択中の様式データを返す。未選択の場合はNone。"""
        idx = self._form_combo.current()
        if idx < 0 or idx >= len(self._forms):
            return None
        return self._forms[idx]

    def _get_form_fields(self, form_id: int) -> list[dict]:
        """様式のフィールド定義を取得する。"""
        if self.db_manager:
            try:
                return self.db_manager.get_form_fields(form_id)
            except Exception as e:
                logger.error(f"フィールド取得に失敗: {e}")
                return []
        else:
            # デモモード: ダミーフィールド
            return [
                {
                    "id": 1, "field_name": "name", "field_label": "氏名",
                    "page_number": 1,
                    "x1": 100.0, "y1": 200.0, "x2": 400.0, "y2": 240.0,
                    "field_type": "text",
                },
            ]

    # -----------------------------------------------------------------------
    # ログ操作
    # -----------------------------------------------------------------------

    def _append_log(self, message: str, tag: str = "info") -> None:
        """
        ログエリアにメッセージを追記する。

        スレッドセーフ: after()で呼び出しをGUIスレッドに委譲。

        Args:
            message: ログメッセージ
            tag:     色タグ ("info" / "success" / "warning" / "error")
        """
        def _do_append():
            self._log_text.configure(state=tk.NORMAL)
            timestamp = datetime.now().strftime("%H:%M:%S")
            self._log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
            self._log_text.see(tk.END)  # 最新行にスクロール
            self._log_text.configure(state=tk.DISABLED)

        # GUIスレッドから呼ばれる場合は直接実行、スレッドからの場合はafterで委譲
        try:
            self.after(0, _do_append)
        except RuntimeError:
            pass  # ウィンドウが閉じられた後の呼び出しを無視

    def _clear_log(self) -> None:
        """ログエリアをクリアする。"""
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)

    # -----------------------------------------------------------------------
    # ファイル操作イベント
    # -----------------------------------------------------------------------

    def _on_add_files(self) -> None:
        """「ファイル追加」ボタン: ファイル選択ダイアログを開く。"""
        filetypes = [
            ("対応ファイル", "*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
            ("PDFファイル", "*.pdf"),
            ("画像ファイル", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
            ("すべてのファイル", "*.*"),
        ]
        paths = filedialog.askopenfilenames(
            parent=self,
            title="処理するファイルを選択（複数選択可）",
            filetypes=filetypes,
        )
        if not paths:
            return

        added = 0
        for path_str in paths:
            p = Path(path_str)
            if p not in self._selected_files:
                self._selected_files.append(p)
                self._file_listbox.insert(tk.END, p.name)
                added += 1

        self._update_file_count()
        if added > 0:
            self._append_log(f"{added}件のファイルを追加しました", "info")

    def _on_clear_files(self) -> None:
        """「一覧クリア」ボタン: ファイル一覧をクリアする。"""
        self._selected_files.clear()
        self._file_listbox.delete(0, tk.END)
        self._update_file_count()

    def _on_remove_selected_files(self, event=None) -> None:
        """Deleteキー: 選択中のファイルを一覧から削除する。"""
        selection = list(self._file_listbox.curselection())
        if not selection:
            return
        # 後ろから削除してインデックスのずれを防ぐ
        for idx in sorted(selection, reverse=True):
            del self._selected_files[idx]
            self._file_listbox.delete(idx)
        self._update_file_count()

    def _update_file_count(self) -> None:
        """ファイル数表示を更新する。"""
        count = len(self._selected_files)
        self._file_count_var.set(f"{count} ファイル選択中")

    def _on_browse_output_dir(self) -> None:
        """「参照...」ボタン: CSV出力先フォルダ選択ダイアログ。"""
        current = self._output_dir_var.get()
        initial_dir = current if Path(current).is_dir() else str(Path.home())

        selected = filedialog.askdirectory(
            parent=self,
            title="CSV出力フォルダを選択",
            initialdir=initial_dir,
        )
        if selected:
            self._output_dir_var.set(selected)

    # -----------------------------------------------------------------------
    # OCR処理実行
    # -----------------------------------------------------------------------

    def _on_run_ocr(self) -> None:
        """「OCR処理実行」ボタン: バリデーション後にOCR処理を開始する。"""
        if self.is_processing:
            messagebox.showinfo("処理中", "OCR処理が既に実行中です。", parent=self)
            return

        # バリデーション
        form = self._get_selected_form()
        if form is None:
            messagebox.showwarning("入力エラー", "様式を選択してください。", parent=self)
            return

        if not self._selected_files:
            messagebox.showwarning(
                "入力エラー", "処理するファイルを追加してください。", parent=self
            )
            return

        # 必要ライブラリの確認
        if not _PIL_AVAILABLE:
            messagebox.showwarning(
                "ライブラリ不足",
                "Pillowがインストールされていないため処理できません。\n"
                "pip install Pillow でインストールしてください。",
                parent=self,
            )
            return

        # フィールド定義の確認
        fields = self._get_form_fields(form["id"])
        if not fields:
            messagebox.showwarning(
                "フィールド未設定",
                f"様式「{form['name']}」にフィールドが設定されていません。\n"
                "先に様式管理画面でフィールドを定義してください。",
                parent=self,
            )
            return

        # 処理開始
        self._result_ids = []
        self.is_processing = True
        self._run_btn.configure(state=tk.DISABLED)
        self._stop_btn.configure(state=tk.NORMAL)
        self._csv_btn.configure(state=tk.DISABLED)
        self._goto_result_btn.configure(state=tk.DISABLED)
        self._progress_var.set(0.0)

        self._append_log(
            f"OCR処理を開始します: 様式「{form['name']}」 "
            f"({len(self._selected_files)}ファイル)",
            "info",
        )

        # OCRエンジンを遅延初期化
        if self._ocr_engine is None and _OCR_ENGINE_AVAILABLE:
            self._append_log("OCRエンジンを初期化中...", "info")
            try:
                self._ocr_engine = OCREngine()
                self._append_log(
                    f"OCRエンジン: {self._ocr_engine.engine_name}", "info"
                )
            except Exception as e:
                self._append_log(f"OCRエンジン初期化エラー: {e}", "warning")
                self._ocr_engine = None

        # バックグラウンドスレッドで処理開始
        self._stop_flag = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._ocr_worker,
            args=(form, fields, list(self._selected_files)),
            daemon=True,
            name="OCRWorker",
        )
        self._worker_thread.start()

        # メッセージポーリングを開始
        self.after(100, self._poll_ocr_messages)

    def _on_stop_ocr(self) -> None:
        """「中止」ボタン: OCR処理を中止する。"""
        if not self.is_processing:
            return
        if messagebox.askyesno(
            "処理中止",
            "OCR処理を中止しますか？\n処理済みのファイルの結果は保存されます。",
            parent=self,
        ):
            self._stop_flag.set()
            self._append_log("中止要求を送信しました...", "warning")

    def _ocr_worker(
        self,
        form: dict,
        fields: list[dict],
        files: list[Path],
    ) -> None:
        """
        OCR処理のバックグラウンドワーカー。

        別スレッドで実行されるため、GUIへの操作は
        _msg_queue を通じてメインスレッドに委譲する。

        Args:
            form:   様式データ dict
            fields: フィールド定義リスト
            files:  処理対象ファイルパスリスト
        """
        success_count = 0
        error_count = 0
        start_time = time.time()

        for i, file_path in enumerate(files):
            # 中止フラグの確認
            if self._stop_flag.is_set():
                self._msg_queue.put(
                    _ProgressMsg(i, len(files), file_path.name, "処理を中止しました")
                )
                break

            self._msg_queue.put(
                _ProgressMsg(
                    i, len(files), file_path.name,
                    f"処理開始: {file_path.name}"
                )
            )

            try:
                result_id = self._process_single_file(form, fields, file_path)
                if result_id is not None:
                    success_count += 1
                    self._msg_queue.put(
                        _ProgressMsg(
                            i + 1, len(files), file_path.name,
                            f"完了: {file_path.name}"
                        )
                    )
            except Exception as e:
                error_count += 1
                error_msg = f"エラー: {file_path.name} - {e}"
                logger.error(f"OCR処理エラー: {e}", exc_info=True)
                self._msg_queue.put(
                    _ProgressMsg(i + 1, len(files), file_path.name, error_msg)
                )

        elapsed = time.time() - start_time
        self._msg_queue.put(_FinishMsg(success_count, error_count, elapsed))

    def _process_single_file(
        self,
        form: dict,
        fields: list[dict],
        file_path: Path,
    ) -> Optional[int]:
        """
        1ファイルのOCR処理を実行してDBに保存する。

        Args:
            form:      様式データ
            fields:    フィールド定義リスト
            file_path: 処理対象ファイルパス

        Returns:
            int: 保存されたOCR結果のID。エラーの場合はNone。
        """
        suffix = file_path.suffix.lower()

        # ページ別に画像を取得
        page_images: dict[int, object] = {}  # page_number -> PIL.Image

        if suffix == ".pdf" and _PYMUPDF_AVAILABLE:
            import fitz
            doc = fitz.open(str(file_path))
            for page_num in range(len(doc)):
                page = doc[page_num]
                # _TEMPLATE_DPI と同じスケールでレンダリングして座標系を一致させる
                _scale = _TEMPLATE_DPI / 72.0
                mat = fitz.Matrix(_scale, _scale)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                page_images[page_num + 1] = img
            doc.close()
        elif _PIL_AVAILABLE:
            img = Image.open(str(file_path))
            if img.mode != "RGB":
                img = img.convert("RGB")
            page_images[1] = img
        else:
            raise RuntimeError("画像処理ライブラリが利用できません")

        # 各フィールドのOCR処理
        field_results: list[dict] = []

        for field in fields:
            page_num = field.get("page_number", 1)
            img = page_images.get(page_num)

            if img is None:
                field_results.append({
                    "field_id":        field.get("id"),
                    "field_name":      field["field_name"],
                    "recognized_text": "",
                    "confidence":      0.0,
                })
                continue

            # OCR処理
            if self._ocr_engine is not None:
                # template_dpi と OCR描画DPI が異なる場合は座標をスケール変換する
                template_dpi = field.get("template_dpi", _TEMPLATE_DPI)
                coord_scale = _TEMPLATE_DPI / template_dpi if template_dpi > 0 else 1.0
                region = (
                    int(field.get("x1", 0) * coord_scale),
                    int(field.get("y1", 0) * coord_scale),
                    int(field.get("x2", 0) * coord_scale),
                    int(field.get("y2", 0) * coord_scale),
                )
                ocr_result = self._ocr_engine.recognize_text(img, region=region)
                recognized_text = ocr_result.get("text", "")
                confidence = ocr_result.get("confidence", 0.0)
            else:
                # OCRエンジンが無い場合はモック結果
                recognized_text = f"[モック: {field['field_label']}]"
                confidence = 0.0

            field_results.append({
                "field_id":        field.get("id"),
                "field_name":      field["field_name"],
                "recognized_text": recognized_text,
                "confidence":      confidence,
            })

        # 結果をDBに保存
        result_id = None
        if self.db_manager:
            result_id = self.db_manager.save_ocr_result(
                form_id=form["id"],
                source_file=str(file_path),
                fields=field_results,
                status="success",
            )
            # メインスレッドでresult_idsに追加するためqueueを使う
            # (スレッドセーフのためafter経由で操作するのが理想だが
            #  ここでは簡便さを優先してスレッドセーフなリストに直接追加)
            self._result_ids.append(result_id)
        else:
            # デモモード: ダミーID
            self._result_ids.append(len(self._result_ids) + 1)

        log_lines = []
        for fr in field_results:
            log_lines.append(
                f"  {fr['field_name']}: '{fr['recognized_text'][:30]}' "
                f"(conf: {fr['confidence']:.2f})"
            )
        logger.debug("フィールド認識結果:\n" + "\n".join(log_lines))

        return result_id

    def _poll_ocr_messages(self) -> None:
        """
        スレッド間キューからメッセージを受け取り、GUIを更新する。

        処理が続いている間は自分自身をafterで再スケジュールする。
        """
        try:
            while True:
                msg = self._msg_queue.get_nowait()

                if isinstance(msg, _ProgressMsg):
                    # 進捗更新
                    pct = (msg.file_index / max(msg.total, 1)) * 100.0
                    self._progress_var.set(pct)
                    self._progress_label_var.set(
                        f"{msg.file_index}/{msg.total}"
                    )

                    tag = "error" if "エラー" in msg.log else "success" if "完了" in msg.log else "info"
                    self._append_log(msg.log, tag)
                    self.status_callback(msg.log)

                elif isinstance(msg, _FinishMsg):
                    # 処理完了
                    self._on_ocr_finished(msg)
                    return

                elif isinstance(msg, _ErrorMsg):
                    # 致命的エラー
                    self._append_log(f"致命的エラー: {msg.error}", "error")
                    self._on_ocr_finished(
                        _FinishMsg(0, len(self._selected_files), 0.0)
                    )
                    return

        except queue.Empty:
            pass

        # 処理継続中: 100ms後に再チェック
        if self.is_processing:
            self.after(100, self._poll_ocr_messages)

    def _on_ocr_finished(self, msg: _FinishMsg) -> None:
        """
        OCR処理完了時のGUI更新処理。

        Args:
            msg: 完了メッセージ
        """
        self.is_processing = False
        self._run_btn.configure(state=tk.NORMAL)
        self._stop_btn.configure(state=tk.DISABLED)

        # プログレスバーを100%にして完了を示す
        self._progress_var.set(100.0)
        self._progress_label_var.set("完了")

        summary = (
            f"処理完了: 成功 {msg.success_count}件 / "
            f"エラー {msg.error_count}件 "
            f"({msg.elapsed:.1f}秒)"
        )
        self._append_log(summary, "success" if msg.error_count == 0 else "warning")
        self.status_callback(summary)

        # CSV出力ボタンと結果確認ボタンを有効化（結果がある場合）
        if self._result_ids:
            self._csv_btn.configure(state=tk.NORMAL)
            self._csv_status_var.set(f"{len(self._result_ids)}件の結果が出力可能です")
            self._goto_result_btn.configure(state=tk.NORMAL)

    def _on_goto_result(self) -> None:
        """「結果確認へ →」ボタン: 結果確認画面に遷移する。"""
        if self.navigate_callback:
            self.navigate_callback("result_view")

    # -----------------------------------------------------------------------
    # CSV出力
    # -----------------------------------------------------------------------

    def _on_export_csv(self) -> None:
        """「CSV出力」ボタン: 処理済み結果をCSVファイルに書き出す。"""
        if not self._result_ids:
            messagebox.showinfo("確認", "エクスポートするOCR結果がありません。", parent=self)
            return

        output_dir = Path(self._output_dir_var.get())
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                messagebox.showerror("エラー", f"出力フォルダを作成できません。\n{e}", parent=self)
                return

        # ファイル名の生成
        form = self._get_selected_form()
        form_name = form["name"] if form else "ocr_result"
        now = datetime.now()
        fmt = self._filename_format_var.get()
        filename = fmt.replace("{form_name}", form_name)
        filename = filename.replace("{date}", now.strftime("%Y%m%d"))
        filename = filename.replace("{datetime}", now.strftime("%Y%m%d_%H%M%S"))
        # ファイル名に使えない文字を置換
        for c in r'\/:*?"<>|':
            filename = filename.replace(c, "_")
        filename += ".csv"

        output_path = output_dir / filename

        # DBから結果を取得してCSV書き出し
        encoding = self._encoding_var.get()
        try:
            rows_written = self._write_csv(output_path, encoding)
            self._append_log(
                f"CSV出力完了: {output_path.name} ({rows_written}行)", "success"
            )
            self.status_callback(f"CSV出力完了: {output_path}")
            messagebox.showinfo(
                "CSV出力完了",
                f"{rows_written}件の結果をCSVに出力しました。\n\n"
                f"ファイル: {output_path}",
                parent=self,
            )
        except Exception as e:
            logger.error(f"CSV出力エラー: {e}")
            messagebox.showerror("CSV出力エラー", f"CSV出力に失敗しました。\n\n{e}", parent=self)

    def _write_csv(self, output_path: Path, encoding: str) -> int:
        """
        OCR結果をCSVファイルに書き出す。

        Args:
            output_path: 出力ファイルパス
            encoding:    文字コード（"utf-8-sig" / "utf-8" / "shift_jis"）

        Returns:
            int: 書き出した行数（ヘッダー行を除く）
        """
        import csv

        if not self.db_manager:
            # デモモード: ダミーCSV
            with open(output_path, "w", encoding=encoding, newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["ファイル名", "処理日時", "フィールド", "認識テキスト", "信頼度"])
                writer.writerow(
                    ["sample.pdf", datetime.now().isoformat(), "氏名", "山田太郎", "0.95"]
                )
            return 1

        # DBから結果を取得
        results = self.db_manager.get_ocr_results_by_ids(self._result_ids)
        if not results:
            raise ValueError("エクスポートする結果データが見つかりません")

        # 全フィールド名を収集（CSV列名として使用）
        all_field_names: list[str] = []
        field_label_map: dict[str, str] = {}
        for result in results:
            for field in result.get("fields", []):
                fn = field.get("field_name", "")
                fl = field.get("field_name", "")  # ラベルはスナップショットを使う
                if fn and fn not in all_field_names:
                    all_field_names.append(fn)
                    field_label_map[fn] = fl

        # CSV書き出し
        with open(output_path, "w", encoding=encoding, newline="") as f:
            writer = csv.writer(f)

            # ヘッダー行
            header = ["ファイル名", "処理日時", "ステータス"] + all_field_names
            writer.writerow(header)

            # データ行
            rows_written = 0
            for result in results:
                row_data: dict[str, str] = {
                    f["field_name"]: f.get("recognized_text", "")
                    for f in result.get("fields", [])
                }
                row = [
                    Path(result.get("source_file", "")).name,
                    result.get("processed_at", ""),
                    result.get("status", ""),
                ] + [row_data.get(fn, "") for fn in all_field_names]
                writer.writerow(row)
                rows_written += 1

        return rows_written

    def refresh(self) -> None:
        """外部から呼び出せるリフレッシュメソッド。"""
        self._load_forms()


# ---------------------------------------------------------------------------
# 単体動作確認用エントリーポイント
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("OCRProcessingFrame 単体起動モード（デモモード）")

    root = tk.Tk()
    root.title("OCR処理 - 動作確認")
    root.geometry("900x700")

    style = ttk.Style(root)
    style.theme_use("clam")

    frame = OCRProcessingFrame(
        root,
        db_manager=None,
        status_callback=lambda msg: print(f"[STATUS] {msg}"),
    )
    frame.pack(fill=tk.BOTH, expand=True)

    root.mainloop()

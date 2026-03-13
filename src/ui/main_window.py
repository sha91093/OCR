"""
main_window.py - OCR申請書読み取りツール メインウィンドウ

担当: 木村 浩 (Hiroshi Kimura) - フロントエンド開発者
作成日: 2026-03-13

アプリケーション全体のルートウィンドウを管理するモジュール。
左サイドバーにナビゲーションメニューを配置し、
メインコンテンツエリアでフレームを切り替える構成を採用。

低スペックPC対応のため:
  - 不必要なアニメーション・エフェクトは使用しない
  - ウィジェット数を最小限に抑える
  - 画像の遅延読み込みを行う
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# プロジェクトルートをパスに追加（単体動作確認用）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 各フレームのインポート（未作成でも起動できるようtry/exceptで保護）
try:
    from src.ui.form_management import FormManagementFrame
    _FORM_MANAGEMENT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"FormManagementFrameのインポートに失敗: {e}")
    _FORM_MANAGEMENT_AVAILABLE = False

try:
    from src.ui.ocr_processing import OCRProcessingFrame
    _OCR_PROCESSING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"OCRProcessingFrameのインポートに失敗: {e}")
    _OCR_PROCESSING_AVAILABLE = False

try:
    from src.ui.result_view import ResultViewFrame
    _RESULT_VIEW_AVAILABLE = True
except ImportError as e:
    logger.warning(f"ResultViewFrameのインポートに失敗: {e}")
    _RESULT_VIEW_AVAILABLE = False

try:
    from src.ui.settings_frame import SettingsFrame
    _SETTINGS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"SettingsFrameのインポートに失敗: {e}")
    _SETTINGS_AVAILABLE = False


# ---------------------------------------------------------------------------
# プレースホルダーフレーム（対応モジュールが未作成の場合に表示）
# ---------------------------------------------------------------------------

class _PlaceholderFrame(ttk.Frame):
    """
    モジュールが未作成・未インポートのときに表示するプレースホルダー。
    開発中の単体動作確認に役立てる。
    """

    def __init__(self, parent: tk.Widget, title: str, **kwargs):
        super().__init__(parent, **kwargs)
        # 中央にメッセージを表示するだけのシンプルな実装
        label = ttk.Label(
            self,
            text=f"【{title}】\n\nこの画面は現在開発中です。",
            font=("", 12),
            justify=tk.CENTER,
            foreground="#888888",
        )
        label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)


# ---------------------------------------------------------------------------
# メインウィンドウ
# ---------------------------------------------------------------------------

class MainWindow(tk.Tk):
    """
    OCR申請書読み取りツールのメインウィンドウ。

    レイアウト:
        ┌─────────────────────────────────────────┐
        │ タイトルバー (OS標準)                      │
        ├──────────┬──────────────────────────────┤
        │          │                              │
        │ サイドバー │   メインコンテンツエリア         │
        │ (幅150px) │   (可変幅)                   │
        │          │                              │
        ├──────────┴──────────────────────────────┤
        │ ステータスバー                             │
        └─────────────────────────────────────────┘

    Attributes:
        db_manager: DatabaseManagerインスタンス（Noneの場合はデモモード）
        debug:      デバッグモードフラグ
        _frames:    フレーム名 -> フレームインスタンスのマッピング
        _current_frame: 現在表示中のフレーム名
    """

    # ウィンドウサイズ定数
    WINDOW_WIDTH = 1024
    WINDOW_HEIGHT = 768
    MIN_WIDTH = 800
    MIN_HEIGHT = 600

    # サイドバー定数
    SIDEBAR_WIDTH = 160

    # ナビゲーション項目定義: (表示名, フレームキー, 説明)
    NAV_ITEMS = [
        ("様式管理",  "form_management", "読み取り様式の登録・フィールド定義"),
        ("OCR処理",  "ocr_processing",  "ファイルを選択してOCR処理を実行"),
        ("結果確認",  "result_view",     "OCR結果の確認・修正・エクスポート"),
        ("設定",     "settings",        "エンジン設定・出力設定の変更"),
    ]

    def __init__(
        self,
        db_manager=None,
        debug: bool = False,
        **kwargs,
    ):
        """
        メインウィンドウを初期化する。

        Args:
            db_manager: DatabaseManagerインスタンス。
                        Noneの場合はデモ用モックを使用する。
            debug:      デバッグモードフラグ。
        """
        # main.py が tk.Tk() を作成してから MainWindow(root, ...) で渡す設計なので
        # 直接 super().__init__() せずに既存ルートを再利用するケースにも対応するため、
        # このクラスは「tk.Tk を継承したウィンドウとして使う」と「tk.Tklを受け取って
        # 設定する」の両方のユースケースに対応できるよう実装する。
        #
        # main.py の launch_gui では tk.Tk() 後に MainWindow(root, ...) として呼ばれるため、
        # ここでは tk.Frame のように振る舞い、root に対して設定を行う形にする。
        # （クラス継承ではなくコンポジション的な設計）
        #
        # ただし単体起動（python main_window.py）のために tk.Tk 継承も維持する。
        super().__init__(**kwargs)

        self.db_manager = db_manager
        self.debug = debug

        # フレームの管理辞書
        self._frames: dict[str, ttk.Frame] = {}
        self._current_frame: str = ""

        # サイドバーのボタン参照（選択状態の視覚的フィードバック用）
        self._nav_buttons: dict[str, tk.Button] = {}

        # ウィンドウ全体の設定
        self._configure_window()

        # ttk テーマ設定（低スペックPC向けに軽量な "clam" テーマを使用）
        self._configure_style()

        # UI構築
        self._build_ui()

        # 初期画面を「様式管理」に設定
        self.show_frame("form_management")

        logger.info("MainWindow の初期化が完了しました")

    def _configure_window(self) -> None:
        """ウィンドウの基本設定（タイトル・サイズ・位置）を行う。"""
        self.title("OCR申請書読み取りツール")

        # ウィンドウサイズと最小サイズの設定
        self.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")
        self.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)

        # ウィンドウを画面中央に配置
        self.update_idletasks()  # 画面サイズ取得のため先に更新
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - self.WINDOW_WIDTH) // 2)
        y = max(0, (screen_h - self.WINDOW_HEIGHT) // 2)
        self.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}+{x}+{y}")

        # ウィンドウクローズ時の確認ダイアログ
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_style(self) -> None:
        """
        ttk テーマとカスタムスタイルを設定する。

        低スペックPC対応:
        - 軽量な "clam" テーマを優先使用
        - フォントはOSのデフォルトに任せてレンダリング負荷を下げる
        """
        style = ttk.Style(self)

        # 利用可能なテーマから軽量なものを選択
        available = style.theme_names()
        for preferred in ("clam", "alt", "default"):
            if preferred in available:
                style.theme_use(preferred)
                logger.debug(f"ttk テーマ: {preferred}")
                break

        # サイドバーボタンのスタイル設定
        # 通常状態
        style.configure(
            "Sidebar.TButton",
            padding=(10, 8),
            anchor=tk.W,
            font=("", 10),
        )
        # 選択中状態（背景色で強調）
        style.configure(
            "SidebarActive.TButton",
            padding=(10, 8),
            anchor=tk.W,
            font=("", 10, "bold"),
        )

        # ステータスバーのスタイル
        style.configure(
            "Status.TLabel",
            padding=(4, 2),
            font=("", 9),
        )

    def _build_ui(self) -> None:
        """メインUI（サイドバー・コンテンツエリア・ステータスバー）を構築する。"""
        # ------------------------------------------------------------------
        # ルートレイアウト: サイドバー | コンテンツ (水平方向)
        # ------------------------------------------------------------------
        # ステータスバーは最下部に固定
        self._build_statusbar()

        # メインエリア（サイドバー + コンテンツ）
        main_frame = ttk.Frame(self)
        main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # サイドバー（左側・固定幅）
        self._build_sidebar(main_frame)

        # 区切り線
        separator = ttk.Separator(main_frame, orient=tk.VERTICAL)
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=0)

        # コンテンツエリア（右側・可変幅）
        self._content_area = ttk.Frame(main_frame)
        self._content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 各フレームを事前に生成してコンテンツエリアに重ねて配置
        self._build_frames()

    def _build_sidebar(self, parent: tk.Widget) -> None:
        """
        左サイドバーを構築する。

        アプリケーション名（ヘッダー）と
        ナビゲーションボタン群で構成する。
        """
        sidebar = tk.Frame(
            parent,
            width=self.SIDEBAR_WIDTH,
            bg="#2c3e50",  # ダークネイビー
        )
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)  # 幅を固定（子ウィジェットによるリサイズ防止）

        # アプリ名ヘッダー
        header = tk.Label(
            sidebar,
            text="OCR\n申請書\n読み取り",
            font=("", 11, "bold"),
            fg="#ecf0f1",
            bg="#2c3e50",
            pady=16,
            justify=tk.CENTER,
        )
        header.pack(fill=tk.X)

        # 区切り線（ヘッダーとメニューの間）
        tk.Frame(sidebar, height=1, bg="#4a6278").pack(fill=tk.X, padx=8, pady=4)

        # ナビゲーションボタン
        for label, key, tooltip in self.NAV_ITEMS:
            btn = tk.Button(
                sidebar,
                text=f"  {label}",
                font=("", 10),
                fg="#ecf0f1",
                bg="#2c3e50",
                activeforeground="#ffffff",
                activebackground="#1a252f",
                relief=tk.FLAT,
                anchor=tk.W,
                cursor="hand2",
                command=lambda k=key: self.show_frame(k),
                padx=4,
                pady=8,
                bd=0,
            )
            btn.pack(fill=tk.X)
            self._nav_buttons[key] = btn

            # ツールチップ的な情報をStatusbarに表示するためのバインド
            btn.bind("<Enter>", lambda e, t=tooltip: self.set_status(t))
            btn.bind("<Leave>", lambda e: self.set_status(""))

        # サイドバー下部にバージョン情報
        tk.Frame(sidebar, bg="#2c3e50").pack(fill=tk.BOTH, expand=True)
        tk.Label(
            sidebar,
            text="v1.0.0",
            font=("", 8),
            fg="#7f8c8d",
            bg="#2c3e50",
            pady=6,
        ).pack(side=tk.BOTTOM)

        # デバッグモード表示
        if self.debug:
            tk.Label(
                sidebar,
                text="[DEBUG]",
                font=("", 8),
                fg="#e74c3c",
                bg="#2c3e50",
            ).pack(side=tk.BOTTOM)

    def _build_statusbar(self) -> None:
        """ウィンドウ最下部のステータスバーを構築する。"""
        statusbar_frame = tk.Frame(self, bd=1, relief=tk.SUNKEN, bg="#ecf0f1")
        statusbar_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # 処理状況テキスト（左側）
        self._status_var = tk.StringVar(value="準備完了")
        self._status_label = tk.Label(
            statusbar_frame,
            textvariable=self._status_var,
            font=("", 9),
            fg="#2c3e50",
            bg="#ecf0f1",
            anchor=tk.W,
            padx=6,
            pady=2,
        )
        self._status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # DB接続状態インジケーター（右側）
        db_status = "DB: 接続済み" if self.db_manager else "DB: デモモード"
        db_color = "#27ae60" if self.db_manager else "#e67e22"
        tk.Label(
            statusbar_frame,
            text=db_status,
            font=("", 9),
            fg=db_color,
            bg="#ecf0f1",
            padx=8,
            pady=2,
        ).pack(side=tk.RIGHT)

    def _build_frames(self) -> None:
        """
        コンテンツエリアに全フレームを生成・配置する。

        フレームは重ねて配置し、show_frame() で表示を切り替える。
        これにより画面遷移時にウィジェットを再生成するコストを避ける。
        （低スペックPC対応: 初回のみ生成コストが発生する）
        """
        # 様式管理フレーム
        if _FORM_MANAGEMENT_AVAILABLE:
            frame = FormManagementFrame(
                self._content_area,
                db_manager=self.db_manager,
                status_callback=self.set_status,
            )
        else:
            frame = _PlaceholderFrame(self._content_area, "様式管理")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._frames["form_management"] = frame

        # OCR処理フレーム
        if _OCR_PROCESSING_AVAILABLE:
            frame = OCRProcessingFrame(
                self._content_area,
                db_manager=self.db_manager,
                status_callback=self.set_status,
            )
        else:
            frame = _PlaceholderFrame(self._content_area, "OCR処理")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._frames["ocr_processing"] = frame

        # 結果確認フレーム
        if _RESULT_VIEW_AVAILABLE:
            frame = ResultViewFrame(
                self._content_area,
                db_manager=self.db_manager,
                status_callback=self.set_status,
            )
        else:
            frame = _PlaceholderFrame(self._content_area, "結果確認")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._frames["result_view"] = frame

        # 設定フレーム
        if _SETTINGS_AVAILABLE:
            frame = SettingsFrame(
                self._content_area,
                db_manager=self.db_manager,
                status_callback=self.set_status,
            )
        else:
            frame = _PlaceholderFrame(self._content_area, "設定")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._frames["settings"] = frame

    def show_frame(self, frame_key: str) -> None:
        """
        指定キーのフレームをコンテンツエリアに表示する。

        サイドバーの選択状態（ハイライト）も同時に更新する。

        Args:
            frame_key: フレームの識別キー
                       ("form_management" / "ocr_processing" /
                        "result_view" / "settings")
        """
        if frame_key not in self._frames:
            logger.warning(f"不明なフレームキー: {frame_key}")
            return

        # フレームを前面に表示
        self._frames[frame_key].lift()
        self._current_frame = frame_key

        # サイドバーボタンの選択状態を更新
        for key, btn in self._nav_buttons.items():
            if key == frame_key:
                # 選択中: 背景を明るくしてアクティブ状態を示す
                btn.configure(bg="#1a252f", fg="#ffffff", font=("", 10, "bold"))
            else:
                # 非選択: デフォルトカラーに戻す
                btn.configure(bg="#2c3e50", fg="#ecf0f1", font=("", 10, "normal"))

        # ステータスバーを更新
        label = next(
            (name for name, key, _ in self.NAV_ITEMS if key == frame_key),
            frame_key,
        )
        self.set_status(f"{label} 画面を表示しています")
        logger.debug(f"フレーム切り替え: {frame_key}")

    def set_status(self, message: str) -> None:
        """
        ステータスバーのメッセージを更新する。

        各フレームからコールバックとして呼び出される。

        Args:
            message: 表示するメッセージ文字列
        """
        self._status_var.set(message)
        # ステータスバーを即座に更新（スレッドから呼ばれることも考慮）
        self._status_label.update_idletasks()

    def _on_close(self) -> None:
        """
        ウィンドウクローズ時の処理。

        処理中の場合は確認ダイアログを表示する。
        """
        # OCR処理中かどうかを確認（OCRProcessingFrameが提供するフラグ）
        ocr_frame = self._frames.get("ocr_processing")
        if ocr_frame and hasattr(ocr_frame, "is_processing") and ocr_frame.is_processing:
            if not messagebox.askyesno(
                "確認",
                "OCR処理が実行中です。\n本当に終了しますか？",
                icon=messagebox.WARNING,
            ):
                return

        logger.info("アプリケーションを終了します")
        self.quit()
        self.destroy()


# ---------------------------------------------------------------------------
# 単体動作確認用エントリーポイント
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # ロギング設定（単体起動時）
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    print("MainWindow 単体起動モード（デモ用DB使用）")
    print("各フレームモジュールが未作成でもプレースホルダーで動作確認できます。")

    # デモ用: DatabaseManagerを使わずに起動
    app = MainWindow(db_manager=None, debug=True)
    app.mainloop()

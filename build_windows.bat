@echo off
rem ==============================================================================
rem build_windows.bat - Windows 向けビルドスクリプト
rem
rem 前提条件:
rem   - Python 3.9 以上がインストールされていること
rem   - 仮想環境が有効化されていること
rem   - pip install -r requirements.txt が完了していること
rem   - pip install pyinstaller が完了していること
rem ==============================================================================

echo ========================================
echo OCR申請書読み取りツール - Windows ビルド
echo ========================================

rem PyInstaller のバージョン確認
pyinstaller --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [エラー] PyInstaller がインストールされていません。
    echo 以下のコマンドでインストールしてください:
    echo   pip install pyinstaller
    exit /b 1
)

rem 前回のビルド成果物を削除
if exist dist\ocr_shinseisho (
    echo 既存のビルド成果物を削除しています...
    rmdir /s /q dist\ocr_shinseisho
)
if exist build (
    rmdir /s /q build
)

rem ビルド実行
echo ビルドを開始します...
pyinstaller ocr_shinseisho.spec --clean

if %ERRORLEVEL% neq 0 (
    echo [エラー] ビルドに失敗しました。
    exit /b 1
)

echo.
echo ========================================
echo ビルド完了
echo 出力先: dist\ocr_shinseisho\
echo 実行ファイル: dist\ocr_shinseisho\ocr_shinseisho.exe
echo ========================================

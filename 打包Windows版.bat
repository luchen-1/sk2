@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo 未找到 .venv，请先运行“安装环境.bat”。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 (
    echo PyInstaller 安装失败。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" build_windows_release.py
if errorlevel 1 (
    echo 打包失败，请查看上方错误。
    pause
    exit /b 1
)
echo.
echo 打包完成：release\护肤品价格助手-windows.zip
pause

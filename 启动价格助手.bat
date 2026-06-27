@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo 未找到 .venv 环境，请先双击“安装环境.bat”完成首次安装。
    pause
    exit /b 1
)
start "" "http://127.0.0.1:8765/"
".venv\Scripts\python.exe" dashboard.py
pause

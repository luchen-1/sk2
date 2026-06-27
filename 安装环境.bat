@echo off
chcp 65001 >nul
setlocal EnableExtensions
title 护肤品价格助手 - 首次环境安装

cd /d "%~dp0"

echo ==================================================
echo 护肤品价格助手 - 首次环境安装
echo 当前目录：%CD%
echo ==================================================
echo.

echo [1/9] 检查必要文件...
set "MISSING=0"
for %%F in ("products.xlsx" "dashboard.py" "main.py" "requirements.txt" "启动价格助手.bat") do (
    if not exist "%%~F" (
        echo 缺失文件：%%~F
        set "MISSING=1"
    )
)
if "%MISSING%"=="1" (
    echo.
    echo 必要文件缺失，安装已停止。请确认项目文件完整后再运行。
    pause
    exit /b 1
)
echo 必要文件检查通过。
echo.

echo [2/9] 检查 Python 是否安装...
set "PYTHON_CMD="
py -3 --version >nul 2>nul
if "%ERRORLEVEL%"=="0" (
    set "PYTHON_CMD=py -3"
) else (
    python --version >nul 2>nul
    if "%ERRORLEVEL%"=="0" (
        set "PYTHON_CMD=python"
    )
)

if "%PYTHON_CMD%"=="" (
    echo 未检测到 Python，请先安装 Python 3.10 或以上版本，并勾选 Add Python to PATH。
    echo 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)
echo 已检测到 Python：%PYTHON_CMD%
%PYTHON_CMD% --version
echo.

echo [3/9] 检查 Python 版本...
%PYTHON_CMD% -c "import sys; print(f'当前 Python 版本：{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); raise SystemExit(0 if sys.version_info >= (3, 10) else 10)"
set "VERSION_STATUS=%ERRORLEVEL%"
if "%VERSION_STATUS%"=="10" (
    echo 当前 Python 版本低于 3.10，建议升级到 Python 3.10 或以上版本后再使用。
) else (
    if not "%VERSION_STATUS%"=="0" (
        echo 无法准确判断 Python 版本，将继续尝试安装。
    )
)
echo.

echo [4/9] 创建或复用虚拟环境...
if not exist ".venv" (
    echo 未发现 .venv，正在创建虚拟环境...
    %PYTHON_CMD% -m venv ".venv"
    if errorlevel 1 (
        echo 创建虚拟环境失败，请检查 Python 安装是否完整。
        pause
        exit /b 1
    )
) else (
    echo .venv 已存在，跳过创建。
)

if not exist ".venv\Scripts\python.exe" (
    echo .venv 中未找到 Python，尝试重新初始化虚拟环境...
    %PYTHON_CMD% -m venv ".venv"
    if errorlevel 1 (
        echo 虚拟环境不可用，请删除 .venv 后重新运行本脚本。
        pause
        exit /b 1
    )
)
echo.

echo [5/9] 安装 Python 依赖...
if not exist "requirements.txt" (
    echo requirements.txt 不存在，无法安装依赖。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo pip 升级失败，请检查网络或 Python 环境。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 (
    echo 依赖安装失败，请检查网络或 requirements.txt。
    pause
    exit /b 1
)
echo.

echo [6/9] 检查 .env 邮件配置文件...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
    ) else (
        > ".env" echo SMTP_HOST=smtp.qq.com
        >> ".env" echo SMTP_PORT=465
        >> ".env" echo SMTP_USER=请填写邮箱
        >> ".env" echo SMTP_PASSWORD=请填写邮箱SMTP授权码
        >> ".env" echo EMAIL_FROM=请填写邮箱
        >> ".env" echo EMAIL_TO=请填写接收提醒的邮箱
    )
    echo 已创建 .env，请用记事本打开填写邮箱配置。
) else (
    echo .env 已存在，跳过创建。不会显示或覆盖现有配置。
)
echo.

echo [7/9] 检查运行目录...
for %%D in ("reports" "backups" "screenshots") do (
    if not exist "%%~D" (
        mkdir "%%~D"
        echo 已创建目录：%%~D
    ) else (
        echo 目录已存在：%%~D
    )
)
echo.

echo [8/9] 运行 Python 语法检查...
".venv\Scripts\python.exe" -m compileall . -q
if errorlevel 1 (
    echo 语法检查失败，项目中可能存在代码问题。请查看上方错误信息。
    pause
    exit /b 1
)
echo 语法检查通过。
echo.

echo [9/9] 运行基础检查（不发送邮件）...
".venv\Scripts\python.exe" main.py --once --no-email
if errorlevel 1 (
    echo 基础检查失败，请查看上方错误信息。
    pause
    exit /b 1
)
echo 基础检查通过。
echo.

echo ==================================================
echo 安装完成。
echo.
echo 下一步：
echo 1. 打开 .env 填写邮箱配置。
echo 2. 双击“启动价格助手.bat”。
echo 3. 在网页里点击“系统自检”。
echo 4. 使用“测试邮件”或命令 .\.venv\Scripts\python main.py --test-email 验证邮箱。
echo ==================================================
echo.
pause

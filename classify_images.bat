@echo off
chcp 65001 >nul
title 智序者 · 美术资源库自动分类
rem ============================================================
rem  智序者 · 美术资源库自动分类（双击运行）
rem  扫描 assets/images/_inbox 里的图片，按类型自动归档，
rem  并更新资源索引 catalog.md。运行完窗口自动停留供查看。
rem ============================================================

setlocal
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [错误] 未找到虚拟环境 Python：
    echo   %PY%
    echo 请先创建 .venv 并安装依赖：
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    echo   .venv\Scripts\pip install torch open_clip_torch -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
)

rem 模型下载走国内 HF 镜像
set "HF_ENDPOINT=https://hf-mirror.com"

echo.
echo ==== 智序者 · 美术资源库自动分类 ====
echo.
"%PY%" "%~dp0engine\tools\image_librarian.py" --inbox "%~dp0assets\images\_inbox"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo 分类完成。图片已归档到 assets\images\ 对应类型目录。
) else (
    echo 分类过程中出现错误，请查看上方提示。
)
echo.
pause
endlocal

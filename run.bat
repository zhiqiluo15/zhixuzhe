@echo off
setlocal enabledelayedexpansion
title 智序者 zhixuzhe v1
cd /d "%~dp0"

echo ╔══════════════════════════════════════╗
echo ║          智序者 zhixuzhe v1         ║
echo ╚══════════════════════════════════════╝
echo.

REM 检查 .env
if not exist ".env" (
    echo   首次运行，需要设置 DeepSeek API Key.
    echo   获取 Key: https://platform.deepseek.com/api_keys
    echo.
    set /p KEY="  请输入 DEEPSEEK_API_KEY: "
    if "!KEY!"=="" (
        echo   错误: 未输入 Key，退出.
        pause
        exit /b 1
    )
    echo DEEPSEEK_API_KEY=!KEY!> .env
    echo   已保存到 .env
    echo.
)

python -m engine.core
pause

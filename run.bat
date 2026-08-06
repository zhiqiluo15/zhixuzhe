@echo off
setlocal enabledelayedexpansion
title zhixuzhe CLI
cd /d "%~dp0"

echo ==========================================
echo         zhixuzhe v1 - CLI
echo ==========================================
echo.

REM Check .env
if not exist ".env" (
    echo   First run: need DeepSeek API Key
    echo   Get Key: https://platform.deepseek.com/api_keys
    echo.
    set /p KEY="  Enter DEEPSEEK_API_KEY: "
    if "!KEY!"=="" (
        echo   Error: no key entered
        pause
        exit /b 1
    )
    echo DEEPSEEK_API_KEY=!KEY!> .env
    echo   Saved to .env
    echo.
)

REM Start CLI Agent
echo   Starting zhixuzhe Agent...
echo.
python -m engine.core
pause

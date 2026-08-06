@echo off
setlocal enabledelayedexpansion
title 智序者 Web UI
cd /d "%~dp0"

echo ╔══════════════════════════════════════╗
echo ║       智序者 zhixuzhe v1 - Web     ║
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

echo   启动中... 稍后会自动打开浏览器
echo   如果未打开，请访问 http://localhost:8080
echo.

REM 启动 Web Server（后台不阻塞）+ 延时后打开浏览器
start "智序者 Web" python engine\web_server.py 8080

REM 等 2 秒让服务启动
timeout /t 2 /nobreak > nul

start "" http://localhost:8080

echo.
echo   服务运行中。关闭此窗口将停止服务。
pause

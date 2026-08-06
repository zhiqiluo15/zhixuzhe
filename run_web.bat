@echo off
setlocal enabledelayedexpansion
title zhixuzhe Web
cd /d "%~dp0"

echo ==========================================
echo        zhixuzhe v1 - Web
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

REM Kill any existing process on port 8080
echo   Checking port 8080...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING') do (
    echo   Killing existing process (PID %%a^)...
    taskkill /f /pid %%a > nul 2>&1
)

REM Start web server (background, hidden window)
echo   Starting server...
start "" /min python engine\web_server.py 8080

REM Wait and verify
echo   Waiting for server...
set /a count=0
:wait_loop
timeout /t 1 /nobreak > nul
set /a count+=1
netstat -ano | findstr ":8080" | findstr "LISTENING" > nul
if %errorlevel%==0 goto :server_ok
if %count% lss 10 goto :wait_loop

echo   ERROR: server failed to start
echo   Check that Python is installed and dependencies are met
pause
exit /b 1

:server_ok
echo   Server ready: http://localhost:8080
echo.

REM Open browser
start "" http://localhost:8080

echo   Service is running. Close this window to stop.
pause

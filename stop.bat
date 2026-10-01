@echo off
REM ============================================================
REM  StuGo - serverni to'xtatish
REM ============================================================
title StuGo - to'xtatish
cd /d "%~dp0"

set "PORT=8000"
set "FOUND=0"

for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":%PORT%"') do (
    echo   %PORT%-portdagi server to'xtatilmoqda ^(PID %%p^)...
    taskkill /PID %%p /T /F >nul 2>&1
    set /a FOUND+=1
)

REM Telegram bot ham alohida jarayon bo'lishi mumkin
for /f "tokens=2" %%p in ('wmic process where "name='python.exe'" get processid^,commandline 2^>nul ^| findstr "telegram_bot"') do (
    echo   Telegram bot to'xtatilmoqda ^(PID %%p^)...
    taskkill /PID %%p /T /F >nul 2>&1
)

echo.
if "%FOUND%"=="0" (
    echo   Ishga tushirilgan server topilmadi.
) else (
    echo   Server to'xtatildi.
)
timeout /t 2 /nobreak >nul
@echo off
REM ============================================================
REM  StuGo - lokal serverni ishga tushirish
REM  Ishga tushirish:  run.bat
REM  To'xtatish:      Ctrl+C  (yoki stop.bat)
REM ============================================================
setlocal
title StuGo Server
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
set "PORT=8000"
set "HOST=0.0.0.0"
set "URL=http://127.0.0.1:%PORT%"

echo.
echo   ==========================================
echo     StuGo  -  talabalar ekotizimi
echo   ==========================================
echo.

REM --- 1. Virtual muhit bormi? ---------------------------------------
if not exist "%PY%" (
    echo   [XATO] .venv topilmadi: %PY%
    echo.
    echo   Birinchi marta quyidagini bajaring:
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM --- 2. .env bormi? ------------------------------------------------
if not exist ".env" (
    echo   [XATO] .env topilmadi.
    echo   Namuna:  copy .env.example .env
    echo.
    pause
    exit /b 1
)

REM --- 3. 8000-port band qilib qo'yilganini tekshiramiz ---------------
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":%PORT%"') do (
    echo   8000-portdagi eski server to'xtatilmoqda ^(PID %%p^)
    taskkill /PID %%p /F >nul 2>&1
)

REM --- 4. Migratsiyalar ----------------------------------------------
echo   Migratsiyalar tekshirilmoqda...
"%PY%" manage.py migrate --noinput
if errorlevel 1 (
    echo.
    echo   [XATO] Migratsiya muvaffaqiyatsiz. Yuqoridagi xabarni o'qing.
    pause
    exit /b 1
)

REM --- 5. Tarmoq (LAN) manzilini aniqlash -----------------------------
set "LAN="
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue ^| Where-Object { $_.IPAddress -notlike '127.*' -and $_.InterfaceAlias -notmatch 'Loopback|vEthernet|WSL|VMware|VirtualBox' } ^| Select-Object -First 1 -ExpandProperty IPAddress)"`) do set "LAN=%%a"

echo.
echo   --------------------------------------------------------
echo     Bu kompyuterda:    %URL%
if defined LAN echo     Boshqa qurilmada:  http://!LAN!:%PORT%/
echo.
echo     Admin panel:       %URL%/admin/
echo     API hujjati:       %URL%/api/docs/
echo   --------------------------------------------------------
echo     To'xtatish uchun bu oynada Ctrl+C bosing.
echo.

REM --- 6. Brauzerni avtomatik ochish ----------------------------------
REM  Aks holda oyna ochilib, "nima bo'ldi?" deb o'tirib qoladi.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 4; Start-Process '%URL%'"

REM --- 7. Server ------------------------------------------------------
REM  0.0.0.0 = barcha tarmoq interfeyslari, shuning uchun boshqa
REM  kompyuter/telefondan ham ochiladi.
"%PY%" -m daphne -b %HOST% -p %PORT% config.asgi:application

echo.
echo   Server to'xtadi.
pause
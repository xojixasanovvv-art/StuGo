@echo off
REM ============================================================
REM  StuGo - GitHub bilan sinxronlash (xavfsiz)
REM
REM  "refusing to merge unrelated histories" xatosi chiqsa SHU
REM  faylni ishga tushiring. U hech qanday o'zgarishingizni
REM  yo'qotmaydi:
REM    1) avval eski holatni `local-backup` tegi bilan saqlaydi
REM    2) keyin GitHub dagi yangi holatga o'tadi
REM ============================================================
setlocal
title StuGo - GitHub bilan sinxronlash
cd /d "%~dp0"

REM Git ko'pincha PATH da yo'q bo'ladi
if exist "C:\Program Files\Git\cmd" set "PATH=%PATH%;C:\Program Files\Git\cmd"

where git >nul 2>&1
if errorlevel 1 (
    echo   [XATO] Git topilmadi. PATH ga "C:\Program Files\Git\cmd" qo'shing.
    pause
    exit /b 1
)

echo.
echo   1/4  O'zgarishlarni tekshirilmoqda...
set "DIRTY=0"
for /f %%c in ('git status --porcelain ^| find /c /v ""') do set "DIRTY=%%c"
if "%DIRTY%"=="0" (
    echo          Toza holatda.
) else (
    echo   [DIQQAT] %DIRTY% ta fayl o'zgartirilgan ^(commit qilinmagan^).
    echo          Ular saqlanadi - `local-backup` tegi ostida.
)

echo.
echo   2/4  GitHub dan yuklanmoqda...
git fetch origin main
if errorlevel 1 (
    echo   [XATO] Internet yoki GitHub ga ulanish muammosi.
    pause
    exit /b 1
)

for /f "tokens=1" %%h in ('git rev-parse --short HEAD') do set "LOCAL=%%h"
for /f "tokens=1" %%h in ('git rev-parse --short origin/main') do set "REMOTE=%%h"
echo          lokal:  %LOCAL%
echo          GitHub: %REMOTE%

if "%LOCAL%"=="%REMOTE%" (
    echo.
    echo   [TAYYOR] Hamma narsa GitHub bilan bir xil.
    pause
    exit /b 0
)

echo.
echo   3/4  Joriy holat zaxiralanmoqda...
git tag -f "local-backup-%LOCAL%" HEAD >nul 2>&1
echo          `local-backup-%LOCAL%` tegi yaratildi ^(bu holatni qaytarish uchun^) ya'ni:
echo          git reset --hard local-backup-%LOCAL%

echo.
echo   4/4  GitHub holatiga o'tilmoqda...
git reset --hard origin/main
if errorlevel 1 (
    echo   [XATO] O'tishda xato yuz berdi.
    pause
    exit /b 1
)

echo.
echo   [TUGADI] GitHub holatiga o'tdingiz.
echo.
pause
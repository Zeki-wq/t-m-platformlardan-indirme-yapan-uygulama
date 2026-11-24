@echo off
chcp 65001 >nul
title Indirici - EXE derleme
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python bulunamadi.
    pause
    exit /b 1
)

echo Gerekli paketler kontrol ediliyor...
python -m pip install --upgrade -r requirements.txt pyinstaller
if errorlevel 1 (
    echo Paket kurulumu basarisiz oldu.
    pause
    exit /b 1
)

echo.
echo Indirici.exe derleniyor... (birkac dakika surebilir)
pyinstaller --noconfirm --clean --windowed --name Indirici ^
    --icon "assets\indirici.ico" ^
    --add-data "static;static" ^
    --collect-all yt_dlp ^
    --collect-all imageio_ffmpeg ^
    --collect-all webview ^
    --collect-all pythonnet ^
    --collect-all clr_loader ^
    desktop.py

if errorlevel 1 (
    echo.
    echo Derleme basarisiz oldu.
    pause
    exit /b 1
)

echo.
echo Tamamlandi: dist\Indirici\Indirici.exe

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if exist "%ISCC%" (
    echo.
    echo Kurulum dosyasi olusturuluyor...
    "%ISCC%" kurulum.iss
    if errorlevel 1 (
        echo Kurulum dosyasi olusturulamadi.
    ) else (
        echo Kurulum hazir: kurulum\Indirici-Setup-1.2.0.exe
    )
) else (
    echo.
    echo Inno Setup 6 bulunamadi; sadece exe derlendi.
    echo Kurulum dosyasi icin: https://jrsoftware.org/isdl.php
)

pause

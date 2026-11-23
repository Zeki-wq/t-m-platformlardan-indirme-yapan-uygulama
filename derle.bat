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
    --add-data "ayarlar.json;." ^
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
echo Bu klasoru istedigin yere tasiyabilirsin.
pause

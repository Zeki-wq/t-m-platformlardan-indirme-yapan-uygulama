@echo off
chcp 65001 >nul
title Indirici
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python bulunamadi.
    echo https://www.python.org/downloads/ adresinden Python 3.10 veya uzerini kurun.
    echo Kurulum ekraninda "Add python.exe to PATH" secenegini isaretleyin.
    echo.
    pause
    exit /b 1
)

python -c "import flask, yt_dlp, imageio_ffmpeg, webview" >nul 2>nul
if errorlevel 1 (
    echo Gerekli paketler kuruluyor, ilk seferde birkac dakika surebilir...
    python -m pip install --upgrade pip >nul 2>nul
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Paket kurulumu basarisiz oldu. Internet baglantisini kontrol edin.
        pause
        exit /b 1
    )
)

start "" pythonw "%~dp0desktop.py"
exit /b 0

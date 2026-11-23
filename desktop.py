# -*- coding: utf-8 -*-
"""İndirici — masaüstü uygulaması.

Flask sunucusunu arka planda çalıştırır, arayüzü pywebview (Edge WebView2)
penceresinde açar. WebView2 yoksa tarayıcıya düşer.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

WINDOW_TITLE = "İndirici"
TEST_MODE = os.environ.get("INDIRICI_TEST") == "1"


def log_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    return base / "indirici-hata.log"


def log_exception() -> None:
    try:
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(time.strftime("[%Y-%m-%d %H:%M:%S]\n"))
            handle.write(traceback.format_exc())
            handle.write("\n")
    except Exception:
        pass


def show_error(message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, WINDOW_TITLE, 0x10)
    except Exception:
        print(message)


def serve(app, port: int) -> None:
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True, use_reloader=False)


def wait_for_server(url: str, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/status", timeout=1.5) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def keep_alive(url: str) -> None:
    """Pencere açılamazsa tarayıcıya düş ve sunucuyu ayakta tut."""
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def main() -> None:
    try:
        from app import app, pick_port
    except Exception:
        log_exception()
        show_error(
            "Uygulama modülleri yüklenemedi. Gerekli paketler kurulu mu?\n\n"
            "baslat.bat dosyasını çalıştırıp tekrar dene. Ayrıntı: indirici-hata.log"
        )
        return

    port = pick_port(int(os.environ.get("PORT", "8765")))
    url = f"http://127.0.0.1:{port}"
    threading.Thread(target=serve, args=(app, port), daemon=True, name="sunucu").start()

    if not wait_for_server(url):
        show_error("Sunucu başlatılamadı. Ayrıntı için indirici-hata.log dosyasına bak.")
        return

    try:
        import webview
    except Exception:
        log_exception()
        keep_alive(url)
        return

    try:
        window = webview.create_window(
            WINDOW_TITLE,
            url,
            width=1140,
            height=830,
            min_size=(420, 600),
            background_color="#080a10",
            hidden=TEST_MODE,
        )
        if TEST_MODE:
            def auto_close() -> None:
                time.sleep(4)
                try:
                    window.destroy()
                except Exception:
                    pass

            webview.start(auto_close)
        else:
            webview.start()
    except Exception:
        log_exception()
        show_error(
            "Masaüstü penceresi açılamadı, uygulama tarayıcıda açılıyor.\n\n"
            "Ayrıntı: indirici-hata.log"
        )
        keep_alive(url)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_exception()
        show_error("İndirici başlatılamadı. Ayrıntı: indirici-hata.log")
        raise

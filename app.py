# -*- coding: utf-8 -*-
"""Medya İndirici — linki yapıştır ya da ara, MP4 / MP3 olarak indir.

Yerel bir Flask uygulamasıdır; indirme motoru olarak yt-dlp kullanır.
Çalıştırmak için:  python app.py   (ya da baslat.bat)
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path

import yt_dlp
from flask import Flask, jsonify, request, send_from_directory
from yt_dlp.utils import DownloadCancelled

APP_VERSION = "1.2.0"

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    BASE_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    _home = Path.home()
    _downloads = next(
        (folder for folder in (_home / "Downloads", _home / "İndirilenler") if folder.exists()),
        _home,
    )
    DOWNLOAD_DIR = _downloads / "Indirici"
else:
    BASE_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = BASE_DIR
    DOWNLOAD_DIR = BASE_DIR / "indirilenler"

STATIC_DIR = RESOURCE_DIR / "static"
CONFIG_PATH = BASE_DIR / "ayarlar.json"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

URL_RE = re.compile(r"^https?://", re.I)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")


# --------------------------------------------------------------------------- #
#  Yardımcılar
# --------------------------------------------------------------------------- #
def find_ffmpeg() -> str | None:
    """PATH'te ffmpeg ara, yoksa imageio-ffmpeg paketinin binary'sini kullan."""
    exe = shutil.which("ffmpeg")
    if exe:
        return str(Path(exe).resolve())
    try:
        import imageio_ffmpeg

        return str(Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve())
    except Exception:
        return None


FFMPEG = find_ffmpeg()


DEFAULT_CONFIG = {"cookies_from_browser": "", "cookies_file": ""}

BROWSERS = [
    {"value": "", "label": "Kullanma (girişsiz)"},
    {"value": "chrome", "label": "Chrome"},
    {"value": "edge", "label": "Microsoft Edge"},
    {"value": "firefox", "label": "Firefox"},
    {"value": "brave", "label": "Brave"},
    {"value": "opera", "label": "Opera"},
    {"value": "vivaldi", "label": "Vivaldi"},
    {"value": "chromium", "label": "Chromium"},
    {"value": "safari", "label": "Safari (macOS)"},
]
BROWSER_VALUES = {item["value"] for item in BROWSERS}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:
            pass
    else:
        try:
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
    return cfg


CONFIG = load_config()


def save_config() -> None:
    try:
        CONFIG_PATH.write_text(
            json.dumps(CONFIG, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except Exception:
        pass


def active_cookie_source() -> str:
    """Etkin çerez kaynağını döndürür: 'dosya:yol', 'tarayıcı:ad' veya ''."""
    cookie_file = str(CONFIG.get("cookies_file") or "").strip()
    if cookie_file and Path(cookie_file).is_file():
        return f"dosya:{cookie_file}"
    browser = str(CONFIG.get("cookies_from_browser") or "").strip()
    if browser:
        return f"tarayıcı:{browser}"
    return ""


def base_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 25,
        "retries": 5,
        "fragment_retries": 5,
        "extractor_retries": 3,
        "nocheckcertificate": True,
    }
    if FFMPEG:
        opts["ffmpeg_location"] = FFMPEG
    cookie_file = str(CONFIG.get("cookies_file") or "").strip()
    if cookie_file and Path(cookie_file).is_file():
        opts["cookiefile"] = cookie_file
    elif CONFIG.get("cookies_from_browser"):
        opts["cookiesfrombrowser"] = (str(CONFIG["cookies_from_browser"]),)
    return opts


def is_url(value: str) -> bool:
    return bool(URL_RE.match((value or "").strip()))


def entry_url(entry: dict | None) -> str:
    if not entry:
        return ""
    url = entry.get("webpage_url") or entry.get("url") or ""
    if url.startswith("http"):
        return url
    if re.fullmatch(r"[\w-]{11}", url or ""):
        return f"https://www.youtube.com/watch?v={url}"
    return ""


def pick_thumbnail(info: dict | None) -> str | None:
    if not info:
        return None
    if info.get("thumbnail"):
        return info["thumbnail"]
    for thumb in reversed(info.get("thumbnails") or []):
        if thumb.get("url"):
            return thumb["url"]
    return None


def friendly_error(exc: Exception | str) -> str:
    msg = ANSI_RE.sub("", str(exc)).strip()
    msg = msg.split("\n")[0]
    msg = re.sub(r"^ERROR:\s*", "", msg).strip()
    low = msg.lower()
    if "sign in to confirm" in low or "not a bot" in low:
        return (
            msg
            + ' — YouTube bot kontrolüne takıldı. Proje klasöründeki ayarlar.json dosyasına '
            '{"cookies_from_browser": "chrome"} yazıp uygulamayı yeniden başlat (Chrome kapalı olsun).'
        )
    if "ffmpeg" in low and ("not" in low or "install" in low or "missing" in low):
        return msg + " — FFmpeg bulunamadı. baslat.bat dosyasını çalıştırıp tekrar dene."
    if "unsupported url" in low:
        return msg + " — Bu site/link desteklenmiyor."
    if (
        "empty media response" in low
        or "login required" in low
        or "requires authentication" in low
        or "rate-limit" in low
        or "rate limit" in low
    ):
        return (
            msg
            + " — Bu içerik giriş (çerez) istiyor. Sağ üstteki ⚙ Ayarlar'dan tarayıcını seç "
            "(Chrome/Edge) ya da cookies.txt dosyanı göster, sonra tekrar dene."
        )
    if "ip address is blocked" in low or "blocked from accessing" in low:
        return msg + " — Bu site IP adresini engelliyor (VPN/ağ kısıtı). Farklı bir bağlantı dene."
    if "could not copy" in low and "cookie" in low:
        return (
            msg
            + " — Tarayıcı açık olduğu için çerez dosyası kilitli. Tarayıcıyı tamamen kapatıp "
            "tekrar dene ya da ⚙ Ayarlar'dan cookies.txt dosyası kullan."
        )
    if "private" in low:
        return msg + " — İçerik gizli/özel olduğu için indirilemiyor."
    if "unavailable" in low:
        return msg + " — İçerik kullanılamıyor (kaldırılmış veya bölgene kapalı olabilir)."
    return msg or "Bilinmeyen bir hata oluştu."


def extract(url: str, extra: dict | None = None) -> dict:
    opts = base_opts()
    if extra:
        opts.update(extra)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info or {}


INFO_CACHE: dict[str, tuple[float, dict]] = {}
INFO_TTL = 600


def cached_info(url: str) -> dict:
    now = time.time()
    hit = INFO_CACHE.get(url)
    if hit and now - hit[0] < INFO_TTL:
        return hit[1]
    info = extract(url, {"extract_flat": "in_playlist", "noplaylist": True})
    INFO_CACHE[url] = (now, info)
    if len(INFO_CACHE) > 80:
        for key in sorted(INFO_CACHE, key=lambda k: INFO_CACHE[k][0])[:20]:
            INFO_CACHE.pop(key, None)
    return info


AUDIO_BITRATES = [320, 256, 192, 128]


def video_heights(info: dict) -> list[int]:
    formats = info.get("formats") or []
    heights = sorted(
        {
            int(f["height"])
            for f in formats
            if f.get("height") and f.get("vcodec") not in (None, "none")
        },
        reverse=True,
    )
    return [h for h in heights if 120 <= h <= 4320]


def single_payload(info: dict) -> dict:
    heights = video_heights(info)
    return {
        "title": info.get("title") or "Başlık yok",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": info.get("duration"),
        "thumbnail": pick_thumbnail(info),
        "webpage_url": info.get("webpage_url") or info.get("original_url") or "",
        "is_live": bool(info.get("is_live")),
        "is_playlist": False,
        "count": 1,
        "first_url": "",
        "video_qualities": heights or [1080, 720, 480, 360],
        "audio_bitrates": AUDIO_BITRATES,
    }


def info_payload(url: str) -> dict:
    info = cached_info(url)
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        count = info.get("playlist_count") or len(entries)
        first = entries[0] if entries else None
        first_url = entry_url(first)
        payload = {
            "title": info.get("title") or "Oynatma listesi",
            "uploader": info.get("uploader") or info.get("channel") or "",
            "duration": None,
            "thumbnail": pick_thumbnail(info) or pick_thumbnail(first),
            "webpage_url": info.get("webpage_url") or url,
            "is_live": False,
            "is_playlist": True,
            "count": count,
            "first_url": first_url,
            "video_qualities": [2160, 1440, 1080, 720, 480, 360],
            "audio_bitrates": AUDIO_BITRATES,
        }
        if first_url:
            try:
                first_info = extract(first_url, {"noplaylist": True})
                options = single_payload(first_info)
                payload["video_qualities"] = options["video_qualities"]
                payload["audio_bitrates"] = options["audio_bitrates"]
                payload["thumbnail"] = payload["thumbnail"] or options["thumbnail"]
            except Exception:
                pass
        return payload
    return single_payload(info)


# --------------------------------------------------------------------------- #
#  İndirme kuyruğu
# --------------------------------------------------------------------------- #
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
JOB_QUEUE: "queue.Queue[str]" = queue.Queue()
WORKER_COUNT = 2


def public_job(job: dict) -> dict:
    return {
        "id": job["id"],
        "url": job["url"],
        "title": job.get("title") or job["url"],
        "mode": job.get("mode"),
        "quality": job.get("quality"),
        "container": job.get("container"),
        "audio_format": job.get("audio_format"),
        "playlist": bool(job.get("playlist")),
        "status": job.get("status"),
        "percent": round(float(job.get("percent") or 0), 1),
        "speed": job.get("speed"),
        "eta": job.get("eta"),
        "size": job.get("size"),
        "filename": job.get("filename"),
        "error": job.get("error"),
        "index": job.get("index"),
        "count": job.get("count"),
        "created": job.get("created"),
    }


def build_ydl_opts(job: dict) -> dict:
    def hook(d: dict) -> None:
        if job.get("cancel"):
            raise DownloadCancelled("İptal edildi")
        info = d.get("info_dict") or {}
        if info.get("playlist_index"):
            job["index"] = info.get("playlist_index")
            job["count"] = info.get("playlist_count") or job.get("count")
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            if total:
                job["percent"] = max(0.0, min(99.0, done * 100.0 / total))
            job["speed"] = d.get("speed")
            job["eta"] = d.get("eta")
            job["size"] = total
            job["status"] = "downloading"
            if d.get("filename"):
                job["filename"] = os.path.basename(d["filename"])
        elif status == "finished":
            job["percent"] = 100.0
            job["speed"] = None
            job["eta"] = 0
            job["status"] = "processing"
            if d.get("filename"):
                job["filename"] = os.path.basename(d["filename"])

    def pp_hook(d: dict) -> None:
        if job.get("cancel"):
            raise DownloadCancelled("İptal edildi")
        status = d.get("status")
        if status in ("started", "processing", "finished"):
            job["status"] = "processing"
        if status == "finished":
            filepath = (d.get("info_dict") or {}).get("filepath")
            if filepath:
                job["filename"] = os.path.basename(filepath)

    opts = {
        **base_opts(),
        "outtmpl": str(DOWNLOAD_DIR / "%(title).150B [%(id)s].%(ext)s"),
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
        "noplaylist": not job.get("playlist"),
        "windowsfilenames": True,
        "concurrent_fragment_downloads": 4,
        "continuedl": True,
        "overwrites": False,
        "ignoreerrors": False,
    }

    if job["mode"] == "audio":
        codec = (job.get("audio_format") or "mp3").lower()
        if codec not in ("mp3", "m4a", "aac", "opus", "vorbis", "wav", "flac", "best"):
            codec = "mp3"
        quality = str(job.get("quality") or "192")
        postprocessor = {"key": "FFmpegExtractAudio", "preferredcodec": codec}
        if codec in ("mp3", "m4a", "aac", "opus", "vorbis") and quality not in ("0", "best", ""):
            postprocessor["preferredquality"] = quality
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [postprocessor, {"key": "FFmpegMetadata", "add_metadata": True}]
    else:
        quality = str(job.get("quality") or "1080")
        if quality in ("best", "", "none"):
            selector = "bestvideo+bestaudio/best"
        else:
            selector = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best"
        container = (job.get("container") or "mp4").lower()
        if container not in ("mp4", "mkv", "webm"):
            container = "mp4"
        opts["format"] = selector
        opts["merge_output_format"] = container
        opts["format_sort"] = ["res", "ext:mp4:m4a", "vcodec:h264"]

    return opts


def run_job(job: dict) -> None:
    if job.get("cancel"):
        job["status"] = "cancelled"
        return

    job["status"] = "starting"
    job["started"] = time.time()
    try:
        opts = build_ydl_opts(job)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(job["url"], download=True)
            if info and info.get("_type") == "playlist":
                job["count"] = info.get("playlist_count") or job.get("count")
            elif info and info.get("filepath"):
                job["filename"] = os.path.basename(info["filepath"])
        if job.get("cancel"):
            job["status"] = "cancelled"
        else:
            job["status"] = "done"
            job["percent"] = 100.0
            job["speed"] = None
            job["eta"] = 0
    except DownloadCancelled:
        job["status"] = "cancelled"
    except Exception as exc:  # noqa: BLE001
        if job.get("cancel"):
            job["status"] = "cancelled"
        else:
            job["status"] = "error"
            job["error"] = friendly_error(exc)
    finally:
        job["finished"] = time.time()


def worker_loop() -> None:
    while True:
        job_id = JOB_QUEUE.get()
        try:
            job = JOBS.get(job_id)
            if job:
                run_job(job)
        except Exception:  # noqa: BLE001
            pass
        finally:
            JOB_QUEUE.task_done()


for _i in range(WORKER_COUNT):
    threading.Thread(target=worker_loop, name=f"indirici-{_i + 1}", daemon=True).start()


# --------------------------------------------------------------------------- #
#  API
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/status")
def api_status():
    return jsonify(
        version=APP_VERSION,
        frozen=FROZEN,
        ffmpeg=bool(FFMPEG),
        ffmpeg_path=FFMPEG,
        ytdlp=yt_dlp.version.__version__,
        download_dir=str(DOWNLOAD_DIR),
        cookies=bool(active_cookie_source()),
        cookies_source=active_cookie_source(),
        cookies_from_browser=CONFIG.get("cookies_from_browser") or "",
        cookies_file=CONFIG.get("cookies_file") or "",
    )


def settings_payload() -> dict:
    return {
        "cookies_from_browser": CONFIG.get("cookies_from_browser") or "",
        "cookies_file": CONFIG.get("cookies_file") or "",
        "browsers": BROWSERS,
        "active": active_cookie_source(),
        "config_path": str(CONFIG_PATH),
    }


@app.get("/api/settings")
def api_get_settings():
    return jsonify(settings_payload())


@app.post("/api/settings")
def api_save_settings():
    data = request.get_json(silent=True) or {}
    browser = str(data.get("cookies_from_browser") or "").strip().lower()
    if browser and browser not in BROWSER_VALUES:
        return jsonify(error="Geçersiz tarayıcı seçimi."), 400

    cookies_file = str(data.get("cookies_file") or "").strip().strip('"')
    if cookies_file and not Path(cookies_file).is_file():
        return jsonify(error=f"Dosya bulunamadı: {cookies_file}"), 400

    CONFIG["cookies_from_browser"] = browser
    CONFIG["cookies_file"] = cookies_file
    save_config()
    INFO_CACHE.clear()
    payload = settings_payload()
    payload["ok"] = True
    return jsonify(payload)


@app.post("/api/test-cookies")
def api_test_cookies():
    data = request.get_json(silent=True) or {}
    browser = str(data.get("cookies_from_browser") or CONFIG.get("cookies_from_browser") or "").strip().lower()
    cookies_file = str(data.get("cookies_file") or CONFIG.get("cookies_file") or "").strip().strip('"')

    if not browser and not cookies_file:
        return jsonify(error="Önce bir tarayıcı seç ya da cookies.txt dosyasının yolunu gir."), 400

    try:
        if cookies_file:
            if not Path(cookies_file).is_file():
                return jsonify(error=f"Dosya bulunamadı: {cookies_file}"), 400
            import http.cookiejar

            jar = http.cookiejar.MozillaCookieJar(cookies_file)
            jar.load(ignore_discard=True, ignore_expires=True)
            count = sum(1 for _ in jar)
            insta = sum(1 for c in jar if "instagram" in (c.domain or ""))
            return jsonify(ok=True, count=count, instagram=insta, source="dosya")

        from yt_dlp.cookies import extract_cookies_from_browser

        jar = extract_cookies_from_browser(browser)
        count = sum(1 for _ in jar)
        insta = sum(1 for c in jar if "instagram" in (c.domain or ""))
        return jsonify(ok=True, count=count, instagram=insta, source=browser)
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=friendly_error(exc)), 502



@app.get("/api/search")
def api_search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify(error="Arama kutusu boş."), 400
    if len(query) > 200:
        return jsonify(error="Arama çok uzun."), 400
    try:
        limit = max(1, min(int(request.args.get("limit", 12)), 30))
    except ValueError:
        limit = 12

    try:
        info = extract(
            f"ytsearch{limit}:{query}",
            {"extract_flat": "in_playlist", "playlistend": limit, "noplaylist": False},
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=friendly_error(exc)), 502

    results = []
    for entry in info.get("entries") or []:
        if not entry:
            continue
        results.append(
            {
                "id": entry.get("id"),
                "title": entry.get("title") or "Başlık yok",
                "url": entry_url(entry),
                "duration": entry.get("duration"),
                "uploader": entry.get("uploader") or entry.get("channel") or "",
                "thumbnail": pick_thumbnail(entry),
                "is_live": bool(entry.get("is_live")),
            }
        )
    return jsonify(query=query, results=results)


@app.get("/api/info")
def api_info():
    url = (request.args.get("url") or "").strip()
    if not is_url(url):
        return jsonify(error="Geçerli bir http(s) linki gir."), 400
    try:
        return jsonify(info_payload(url))
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=friendly_error(exc)), 502


@app.post("/api/download")
def api_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not is_url(url):
        return jsonify(error="Geçerli bir http(s) linki gir."), 400

    mode = "audio" if data.get("mode") == "audio" else "video"
    quality = str(data.get("quality") or ("192" if mode == "audio" else "1080"))
    job = {
        "id": uuid.uuid4().hex[:12],
        "url": url,
        "title": (data.get("title") or url)[:300],
        "mode": mode,
        "quality": quality,
        "container": (data.get("container") or "mp4").lower(),
        "audio_format": (data.get("audio_format") or "mp3").lower(),
        "playlist": bool(data.get("playlist")),
        "count": data.get("count"),
        "status": "queued",
        "percent": 0.0,
        "speed": None,
        "eta": None,
        "size": None,
        "filename": None,
        "error": None,
        "index": None,
        "created": time.time(),
        "cancel": False,
    }
    with JOBS_LOCK:
        JOBS[job["id"]] = job
    JOB_QUEUE.put(job["id"])
    return jsonify(job=public_job(job)), 202


@app.get("/api/jobs")
def api_jobs():
    with JOBS_LOCK:
        jobs = [public_job(j) for j in JOBS.values()]
    jobs.sort(key=lambda j: j["created"], reverse=True)
    return jsonify(jobs=jobs[:60])


@app.post("/api/jobs/<job_id>/cancel")
def api_cancel_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return jsonify(error="İndirme bulunamadı."), 404
    if job.get("status") in ("done", "error", "cancelled"):
        return jsonify(ok=False, error="Bu indirme zaten bitmiş."), 409
    job["cancel"] = True
    if job.get("status") == "queued":
        job["status"] = "cancelled"
    else:
        job["status"] = "cancelling"
    return jsonify(ok=True)


@app.delete("/api/jobs/<job_id>")
def api_delete_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return jsonify(error="İndirme bulunamadı."), 404
    if job.get("status") not in ("done", "error", "cancelled"):
        return jsonify(error="Devam eden indirme kaldırılamaz, önce iptal et."), 409
    with JOBS_LOCK:
        JOBS.pop(job_id, None)
    return jsonify(ok=True)


@app.post("/api/jobs/clear")
def api_clear_jobs():
    with JOBS_LOCK:
        for job_id in [
            k
            for k, j in JOBS.items()
            if j.get("status") in ("done", "error", "cancelled")
        ]:
            JOBS.pop(job_id, None)
    return jsonify(ok=True)


@app.post("/api/open-folder")
def api_open_folder():
    try:
        if sys.platform == "win32":
            os.startfile(str(DOWNLOAD_DIR))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(DOWNLOAD_DIR)])
        else:
            subprocess.Popen(["xdg-open", str(DOWNLOAD_DIR)])
        return jsonify(ok=True)
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=str(exc)), 500


@app.post("/api/update")
def api_update():
    if FROZEN:
        return (
            jsonify(
                error="Bu sürüm .exe olarak paketlendiği için yt-dlp güncellemesi yapılamaz. "
                "Projenin yeni sürümünü indirip çalıştır."
            ),
            400,
        )
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=f"Güncelleme başlatılamadı: {exc}"), 500

    output = (proc.stdout or "") + (proc.stderr or "")
    installed = ""
    match = re.search(r"Successfully installed ([^\s]+)", output)
    if match:
        installed = match.group(1)
    if proc.returncode != 0:
        tail = "\n".join([line for line in output.splitlines() if line.strip()][-6:])
        return jsonify(error=f"Güncelleme başarısız:\n{tail}"), 500
    return jsonify(ok=True, installed=installed or "yt-dlp", restart=True)


# --------------------------------------------------------------------------- #
#  Başlatma
# --------------------------------------------------------------------------- #
def pick_port(start: int) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    port = pick_port(int(os.environ.get("PORT", "8765")))
    url = f"http://127.0.0.1:{port}"
    print("=" * 58)
    print("  İndirici")
    print(f"  Adres   : {url}")
    print(f"  Klasör  : {DOWNLOAD_DIR}")
    print(f"  FFmpeg  : {'hazır' if FFMPEG else 'BULUNAMADI'}")
    print(f"  yt-dlp  : {yt_dlp.version.__version__}")
    print("  Kapatmak için bu pencereyi kapat veya Ctrl+C")
    print("=" * 58)

    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host="127.0.0.1", port=port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()

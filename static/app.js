/* Medya İndirici — arayüz mantığı */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const modalEl = $("#modal");
  const modalBody = $("#modalBody");
  const jobsEl = $("#jobs");
  const resultsEl = $("#results");
  const qInput = $("#q");
  const goBtn = $("#goBtn");

  let modal = null;
  let jobs = [];
  let lastJobsSignature = "";
  const seenStatus = new Map();
  let pollBusy = false;

  /* ----------------------------- yardımcılar ----------------------------- */
  const STATUS_LABELS = {
    queued: "Sırada",
    starting: "Hazırlanıyor",
    downloading: "İndiriliyor",
    processing: "Dönüştürülüyor",
    cancelling: "İptal ediliyor",
    done: "Tamamlandı",
    error: "Hata",
    cancelled: "İptal edildi",
  };

  const ACTIVE_STATES = new Set(["queued", "starting", "downloading", "processing", "cancelling"]);

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[ch]));
  }

  function fmtDuration(seconds) {
    if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "";
    let total = Math.round(Number(seconds));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
  }

  function fmtBytes(bytes) {
    const n = Number(bytes);
    if (!n || n <= 0) return "";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = n;
    let i = 0;
    while (value >= 1024 && i < units.length - 1) {
      value /= 1024;
      i += 1;
    }
    return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
  }

  function fmtSpeed(bytesPerSec) {
    return bytesPerSec ? `${fmtBytes(bytesPerSec)}/sn` : "";
  }

  function fmtEta(seconds) {
    if (seconds === null || seconds === undefined || seconds === "" || Number.isNaN(Number(seconds))) return "";
    const total = Math.round(Number(seconds));
    if (total <= 0) return "";
    if (total < 60) return `${total} sn`;
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m} dk ${s} sn`;
  }

  function videoLabel(height) {
    const h = Number(height);
    if (h >= 4320) return "8K";
    if (h >= 2160) return "4K";
    if (h >= 1440) return "2K";
    return `${h}p`;
  }

  function normalizeInput(value) {
    let text = String(value || "").trim();
    if (!text) return "";
    if (!/^https?:\/\//i.test(text) && /^[\w-]+(\.[\w-]+)+\//.test(text)) {
      text = "https://" + text;
    }
    return text;
  }

  function isUrl(value) {
    return /^https?:\/\//i.test(normalizeInput(value));
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    if (!response.ok) {
      throw new Error((data && data.error) || `Sunucu hatası (${response.status})`);
    }
    return data || {};
  }

  function toast(message, kind = "ok") {
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.textContent = message;
    $("#toasts").appendChild(el);
    window.setTimeout(() => {
      el.classList.add("out");
      window.setTimeout(() => el.remove(), 260);
    }, 4200);
  }

  function skeletons(count) {
    return Array.from({ length: count }, () => `
      <div class="skeleton">
        <div class="sk-thumb"></div>
        <div class="sk-line"></div>
        <div class="sk-line short"></div>
      </div>`).join("");
  }

  /* ------------------------------- durum -------------------------------- */
  async function loadStatus() {
    const pill = $("#statusPill");
    const text = $("#statusText");
    try {
      const status = await api("/api/status");
      pill.classList.remove("err", "warn", "ok");
      if (status.ffmpeg) {
        pill.classList.add("ok");
        text.textContent = "FFmpeg hazır";
        pill.title = `FFmpeg: ${status.ffmpeg_path}`;
      } else {
        pill.classList.add("warn");
        text.textContent = "FFmpeg yok";
        pill.title = "FFmpeg bulunamadı — MP3 dönüştürme ve video birleştirme çalışmaz. baslat.bat dosyasını çalıştır.";
      }
      $("#ytdlpVer").textContent = `yt-dlp ${status.ytdlp}`;
      if (status.frozen) {
        const updateButton = $("#updateBtn");
        if (updateButton) updateButton.hidden = true;
      }
    } catch {
      pill.classList.remove("ok", "warn");
      pill.classList.add("err");
      text.textContent = "Sunucu kapalı";
      pill.title = "Uygulama sunucusuna ulaşılamadı.";
    }
  }

  /* ------------------------------- arama -------------------------------- */
  function setGoLabel() {
    goBtn.textContent = isUrl(qInput.value) ? "Getir" : "Ara";
  }

  async function doSearch(rawQuery) {
    const query = String(rawQuery || "").trim();
    if (!query) return;

    const section = $("#resultsSection");
    section.hidden = false;
    $("#resultsTitle").textContent = `“${query}” için sonuçlar`;
    $("#resultsEmpty").hidden = true;
    resultsEl.innerHTML = skeletons(8);
    section.scrollIntoView({ behavior: "smooth", block: "start" });

    try {
      const data = await api(`/api/search?q=${encodeURIComponent(query)}`);
      renderResults(data.results || []);
    } catch (error) {
      resultsEl.innerHTML = `<div class="errorbox">${esc(error.message)}</div>`;
    }
  }

  function renderResults(items) {
    if (!items.length) {
      resultsEl.innerHTML = "";
      $("#resultsEmpty").hidden = false;
      return;
    }
    $("#resultsEmpty").hidden = true;
    resultsEl.innerHTML = items.map((item) => {
      const thumb = item.thumbnail
        ? `<img loading="lazy" src="${esc(item.thumbnail)}" alt="">`
        : `<div class="noimg">♪</div>`;
      const duration = item.duration ? `<span class="dur">${fmtDuration(item.duration)}</span>` : "";
      const live = item.is_live ? `<span class="live-badge">CANLI</span>` : "";
      return `
        <article class="card" data-url="${esc(item.url)}">
          <div class="thumb">${thumb}${live}${duration}</div>
          <div class="body">
            <h3 title="${esc(item.title)}">${esc(item.title)}</h3>
            <p class="who">${esc(item.uploader || "Bilinmeyen kanal")}</p>
            <div class="actions">
              <button type="button" class="btn primary small" data-dl>İndir</button>
            </div>
          </div>
        </article>`;
    }).join("");
  }

  /* ------------------------------- modal -------------------------------- */
  function defaultVideoQuality(list) {
    const nums = list.map(Number).filter((n) => Number.isFinite(n));
    if (nums.includes(1080)) return "1080";
    if (nums.length) return String(nums[0]);
    return "best";
  }

  function defaultAudioQuality(list) {
    const nums = list.map(String);
    if (nums.includes("192")) return "192";
    return nums[0] || "192";
  }

  function openModal(url) {
    modal = {
      url,
      info: null,
      tab: "video",
      quality: "1080",
      container: "mp4",
      audioFormat: "mp3",
      playlist: false,
    };
    modalEl.hidden = false;
    document.body.classList.add("locked");
    modalBody.innerHTML = loadingHtml();
    loadInfo(url);
  }

  function loadingHtml() {
    return `<div class="modal-loading"><span class="spinner"></span><p>Bilgiler alınıyor…</p></div>`;
  }

  async function loadInfo(url) {
    try {
      const info = await api(`/api/info?url=${encodeURIComponent(url)}`);
      if (!modal) return;
      modal.info = info;
      modal.tab = "video";
      modal.container = "mp4";
      modal.audioFormat = "mp3";
      modal.playlist = !!info.is_playlist;
      modal.quality = defaultVideoQuality(info.video_qualities || []);
      renderModal();
    } catch (error) {
      if (!modal) return;
      modalBody.innerHTML = `
        <div class="errorbox">
          ${esc(error.message)}
          <div style="margin-top:14px">
            <button type="button" class="btn ghost small" id="retryInfo">Tekrar dene</button>
          </div>
        </div>`;
    }
  }

  function qualityChipsHtml(list, selected, isAudio) {
    const options = isAudio
      ? [{ value: "0", label: "En iyi" }].concat(
          list.map((value) => ({ value: String(value), label: `${value} kbps` }))
        )
      : [{ value: "best", label: "En iyi" }].concat(
          list.map((value) => ({ value: String(value), label: videoLabel(value) }))
        );

    return options.map((option) => `
      <button type="button" class="chip ${option.value === selected ? "selected" : ""}"
              data-quality="${esc(option.value)}">${esc(option.label)}</button>`).join("");
  }

  function renderModal() {
    if (!modal || !modal.info) return;
    const info = modal.info;
    const isAudio = modal.tab === "audio";
    const isLossless = isAudio && ["wav", "flac"].includes(modal.audioFormat);
    const qualities = isAudio ? info.audio_bitrates || [] : info.video_qualities || [];

    const thumb = info.thumbnail
      ? `<img class="modal-thumb" src="${esc(info.thumbnail)}" alt="">`
      : `<div class="modal-thumb"></div>`;

    const metaBits = [];
    if (info.uploader) metaBits.push(esc(info.uploader));
    if (info.duration) metaBits.push(fmtDuration(info.duration));
    if (info.is_live) metaBits.push("CANLI");

    const playlistNote = info.is_playlist
      ? `<div class="note">Oynatma listesi · ${info.count ? esc(info.count) + " video" : "tüm videolar"}</div>`
      : "";

    const audioFormats = [
      ["mp3", "MP3 — her yerde çalar"],
      ["m4a", "M4A (AAC) — daha iyi kalite/boyut"],
      ["opus", "OPUS — en verimli"],
      ["wav", "WAV — kayıpsız (büyük dosya)"],
      ["flac", "FLAC — kayıpsız sıkıştırılmış"],
    ];

    const containers = [
      ["mp4", "MP4 — en uyumlu"],
      ["mkv", "MKV — en yüksek kalite"],
      ["webm", "WEBM — açık format"],
    ];

    const formatOptions = (isAudio ? audioFormats : containers).map(([value, label]) => {
      const current = isAudio ? modal.audioFormat : modal.container;
      return `<option value="${value}" ${value === current ? "selected" : ""}>${esc(label)}</option>`;
    }).join("");

    modalBody.innerHTML = `
      <div class="modal-head">
        ${thumb}
        <div>
          <h3 id="modalTitle">${esc(info.title || "Başlık yok")}</h3>
          <p class="muted">${metaBits.join(" · ")}</p>
        </div>
      </div>

      ${playlistNote}

      <div class="tabs">
        <button type="button" data-tab="video" class="${!isAudio ? "active" : ""}">🎬 Video (MP4)</button>
        <button type="button" data-tab="audio" class="${isAudio ? "active" : ""}">🎵 Müzik (MP3)</button>
      </div>

      <div class="field" id="qualityField" ${isLossless ? "hidden" : ""}>
        <label>Kalite</label>
        <div class="chips">${qualityChipsHtml(qualities, modal.quality, isAudio)}</div>
      </div>

      <div class="field">
        <label>${isAudio ? "Ses formatı" : "Video formatı"}</label>
        <select id="fmtSelect">${formatOptions}</select>
      </div>

      ${info.is_playlist ? `
        <label class="check">
          <input type="checkbox" id="playlistChk" ${modal.playlist ? "checked" : ""}>
          Tüm listeyi indir${info.count ? ` (${esc(info.count)} video)` : ""}
        </label>` : ""}

      <div class="modal-actions">
        <button type="button" class="btn primary wide" id="startDl">İndirmeyi başlat</button>
      </div>`;
  }

  function closeModal() {
    modalEl.hidden = true;
    document.body.classList.remove("locked");
    modal = null;
    modalBody.innerHTML = "";
  }

  /* ------------------------------- ayarlar ------------------------------- */
  async function openSettings() {
    modal = null;
    modalEl.hidden = false;
    document.body.classList.add("locked");
    modalBody.innerHTML = loadingHtml();
    try {
      const settings = await api("/api/settings");
      renderSettings(settings);
    } catch (error) {
      modalBody.innerHTML = `<div class="errorbox">${esc(error.message)}</div>`;
    }
  }

  function renderSettings(settings) {
    const options = (settings.browsers || []).map((item) => `
      <option value="${esc(item.value)}" ${item.value === settings.cookies_from_browser ? "selected" : ""}>
        ${esc(item.label)}
      </option>`).join("");

    const activeNote = settings.active
      ? `<p class="hint-small ok">Etkin çerez kaynağı: ${esc(settings.active)}</p>`
      : `<p class="hint-small">Şu an çerez kullanılmıyor — giriş gerektiren siteler çalışmaz.</p>`;

    modalBody.innerHTML = `
      <div class="settings">
        <h3 id="modalTitle">⚙ Ayarlar</h3>
        <p class="muted">
          Instagram, TikTok, Facebook gibi siteler çoğu zaman giriş (çerez) ister.
          Tarayıcını seç ya da dışa aktardığın <code>cookies.txt</code> dosyasını göster.
        </p>
        ${activeNote}

        <div class="field">
          <label>Çerezleri al — tarayıcı</label>
          <select id="setBrowser">${options}</select>
          <p class="hint-small">
            Seçtiğin tarayıcıda ilgili siteye giriş yapmış olmalısın.
            Tarayıcı açıkken çerez dosyası kilitli olabilir; o durumda tarayıcıyı tamamen kapatıp
            <b>Test et</b>'e bas.
          </p>
        </div>

        <div class="field">
          <label>veya cookies.txt dosyası (tam yol)</label>
          <input id="setCookiesFile" type="text" spellcheck="false"
                 placeholder="C:\\Users\\Zeki\\Downloads\\cookies.txt"
                 value="${esc(settings.cookies_file || "")}">
          <p class="hint-small">
            Chrome/Edge için <b>“Get cookies.txt LOCALLY”</b> uzantısıyla instagram.com çerezlerini
            dışa aktarabilirsin. Dosya yolu varsa tarayıcı seçiminden önce gelir.
          </p>
        </div>

        <div class="modal-actions settings-actions">
          <button type="button" class="btn ghost" id="testCookies">Test et</button>
          <button type="button" class="btn primary" id="saveSettings">Kaydet</button>
        </div>
        <div id="settingsResult" class="hint-small"></div>
        <p class="hint-small muted">Ayar dosyası: ${esc(settings.config_path || "ayarlar.json")}</p>
      </div>`;
  }

  async function saveSettings(showToast = true) {
    const browser = $("#setBrowser") ? $("#setBrowser").value : "";
    const file = $("#setCookiesFile") ? $("#setCookiesFile").value.trim() : "";
    const result = $("#settingsResult");
    try {
      await api("/api/settings", {
        method: "POST",
        body: JSON.stringify({ cookies_from_browser: browser, cookies_file: file }),
      });
      if (result) {
        result.textContent = "Kaydedildi. Giriş gerektiren siteler artık çalışmalı.";
        result.className = "hint-small ok";
      }
      if (showToast) toast("Ayarlar kaydedildi.", "ok");
      loadStatus();
      return true;
    } catch (error) {
      if (result) {
        result.textContent = error.message;
        result.className = "hint-small err";
      } else {
        toast(error.message, "err");
      }
      return false;
    }
  }

  async function testCookies() {
    const result = $("#settingsResult");
    if (result) {
      result.textContent = "Test ediliyor…";
      result.className = "hint-small";
    }
    if (!(await saveSettings(false))) return;
    try {
      const data = await api("/api/test-cookies", { method: "POST" });
      if (result) {
        result.textContent = `Çerezler okundu: ${data.count} adet` +
          (data.instagram ? ` (Instagram: ${data.instagram})` : " — Instagram çerezi görünmüyor, sitede giriş yapmış mıydın?");
        result.className = "hint-small ok";
      }
    } catch (error) {
      if (result) {
        result.textContent = error.message;
        result.className = "hint-small err";
      }
    }
  }

  async function startDownload() {
    if (!modal || !modal.info) return;
    const info = modal.info;
    const button = $("#startDl");
    if (button) {
      button.disabled = true;
      button.textContent = "Başlatılıyor…";
    }

    const usePlaylist = !!(info.is_playlist && modal.playlist);
    const url = info.is_playlist && !usePlaylist ? info.first_url || modal.url : modal.url;

    try {
      await api("/api/download", {
        method: "POST",
        body: JSON.stringify({
          url,
          title: info.title,
          mode: modal.tab,
          quality: modal.quality,
          container: modal.container,
          audio_format: modal.audioFormat,
          playlist: usePlaylist,
          count: info.count,
        }),
      });
      closeModal();
      toast("İndirme kuyruğa eklendi.", "ok");
      await refreshJobs();
    } catch (error) {
      toast(error.message, "err");
      if (button) {
        button.disabled = false;
        button.textContent = "İndirmeyi başlat";
      }
    }
  }

  /* ------------------------------ indirmeler ----------------------------- */
  function jobModeLabel(job) {
    if (job.mode === "audio") {
      const codec = (job.audio_format || "mp3").toUpperCase();
      const lossless = ["WAV", "FLAC"].includes(codec);
      const rate = job.quality && job.quality !== "0" && !lossless ? ` · ${job.quality} kbps` : "";
      return `${codec}${rate}`;
    }
    const container = (job.container || "mp4").toUpperCase();
    const quality = job.quality === "best" ? "en iyi" : job.quality ? `${job.quality}p` : "";
    return `${container}${quality ? ` · ${quality}` : ""}`;
  }

  function renderJobs() {
    const signature = JSON.stringify(
      jobs.map((job) => [job.id, job.status, job.percent, job.speed, job.eta, job.error, job.index])
    );
    if (signature === lastJobsSignature) return;
    lastJobsSignature = signature;

    $("#jobsEmpty").hidden = jobs.length > 0;
    jobsEl.innerHTML = jobs.map((job) => {
      const active = ACTIVE_STATES.has(job.status);
      const statusClass = ["done", "error", "cancelled", "processing"].includes(job.status)
        ? job.status
        : "";
      const percent = Math.max(0, Math.min(100, Number(job.percent) || 0));
      const meta = [`<span>${esc(jobModeLabel(job))}</span>`];

      if (job.status === "downloading" && job.speed) meta.push(`<span>${fmtSpeed(job.speed)}</span>`);
      if (job.status === "downloading" && job.eta) meta.push(`<span>${fmtEta(job.eta)} kaldı</span>`);
      if (job.size) meta.push(`<span>${fmtBytes(job.size)}</span>`);
      if (job.index && job.count) meta.push(`<span>${job.index}/${job.count}</span>`);
      meta.push(`<span class="pct">%${Math.round(percent)}</span>`);

      return `
        <div class="job ${statusClass}">
          <div class="job-head">
            <div class="job-title" title="${esc(job.title)}">${esc(job.title)}</div>
            <div class="job-right">
              <span class="badge ${statusClass}">${STATUS_LABELS[job.status] || job.status}</span>
            </div>
          </div>
          <div class="progress"><i style="width:${percent}%"></i></div>
          <div class="job-meta">${meta.join("")}</div>
          ${job.status === "done" && job.filename
            ? `<div class="job-file" title="${esc(job.filename)}">${esc(job.filename)}</div>`
            : ""}
          ${job.error ? `<div class="job-error">${esc(job.error)}</div>` : ""}
          <div class="job-actions">
            ${active
              ? `<button type="button" class="iconbtn danger" data-act="cancel" data-id="${job.id}">İptal</button>`
              : `<button type="button" class="iconbtn" data-act="remove" data-id="${job.id}">Kaldır</button>`}
          </div>
        </div>`;
    }).join("");
  }

  async function refreshJobs() {
    if (pollBusy) return;
    pollBusy = true;
    try {
      const data = await api("/api/jobs");
      const nextJobs = data.jobs || [];

      for (const job of nextJobs) {
        const previous = seenStatus.get(job.id);
        if (previous && previous !== job.status) {
          if (job.status === "done") toast(`Tamamlandı: ${job.title}`, "ok");
          if (job.status === "error") toast(job.error || `İndirilemedi: ${job.title}`, "err");
        }
        seenStatus.set(job.id, job.status);
      }

      jobs = nextJobs;
      renderJobs();
    } catch {
      /* sunucu geçici olarak yanıt vermiyor olabilir */
    } finally {
      pollBusy = false;
    }
  }

  async function pollLoop() {
    await refreshJobs();
    window.setTimeout(pollLoop, 1200);
  }

  /* ------------------------------- olaylar ------------------------------- */
  $("#searchForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const value = normalizeInput(qInput.value);
    if (!value) return;
    qInput.value = value;
    if (isUrl(value)) {
      openModal(value);
    } else {
      doSearch(value);
    }
  });

  qInput.addEventListener("input", setGoLabel);

  $("#pasteBtn").addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text && text.trim()) {
        qInput.value = text.trim();
        setGoLabel();
        qInput.focus();
      }
    } catch {
      qInput.focus();
      toast("Panoya erişilemedi. Ctrl+V ile yapıştırabilirsin.", "warn");
    }
  });

  $("#hints").addEventListener("click", (event) => {
    const chip = event.target.closest("[data-q]");
    if (!chip) return;
    qInput.value = chip.dataset.q;
    setGoLabel();
    doSearch(chip.dataset.q);
  });

  resultsEl.addEventListener("click", (event) => {
    const card = event.target.closest(".card");
    if (!card || !card.dataset.url) return;
    openModal(card.dataset.url);
  });

  $("#clearResults").addEventListener("click", () => {
    $("#resultsSection").hidden = true;
    resultsEl.innerHTML = "";
    $("#resultsEmpty").hidden = true;
  });

  modalEl.addEventListener("click", (event) => {
    if (event.target.closest("[data-close]")) closeModal();
  });

  modalBody.addEventListener("click", async (event) => {
    if (event.target.closest("#saveSettings")) {
      await saveSettings();
      return;
    }
    if (event.target.closest("#testCookies")) {
      await testCookies();
      return;
    }
    if (!modal) return;

    const tabButton = event.target.closest("[data-tab]");
    if (tabButton && modal.info) {
      const tab = tabButton.dataset.tab;
      if (tab !== modal.tab) {
        modal.tab = tab;
        modal.quality = tab === "audio"
          ? defaultAudioQuality(modal.info.audio_bitrates || [])
          : defaultVideoQuality(modal.info.video_qualities || []);
        renderModal();
      }
      return;
    }

    const qualityButton = event.target.closest("[data-quality]");
    if (qualityButton && modal.info) {
      modal.quality = qualityButton.dataset.quality;
      renderModal();
      return;
    }

    if (event.target.closest("#startDl")) {
      startDownload();
      return;
    }

    if (event.target.closest("#retryInfo")) {
      modalBody.innerHTML = loadingHtml();
      loadInfo(modal.url);
    }
  });

  modalBody.addEventListener("change", (event) => {
    if (!modal || !modal.info) return;
    if (event.target.id === "fmtSelect") {
      if (modal.tab === "audio") {
        modal.audioFormat = event.target.value;
      } else {
        modal.container = event.target.value;
      }
      renderModal();
    } else if (event.target.id === "playlistChk") {
      modal.playlist = event.target.checked;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modalEl.hidden) closeModal();
  });

  jobsEl.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-act]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.act;

    button.disabled = true;
    try {
      if (action === "cancel") {
        await api(`/api/jobs/${id}/cancel`, { method: "POST" });
        toast("İndirme iptal ediliyor…", "warn");
      } else if (action === "remove") {
        await api(`/api/jobs/${id}`, { method: "DELETE" });
        seenStatus.delete(id);
      }
      await refreshJobs();
    } catch (error) {
      toast(error.message, "err");
      button.disabled = false;
    }
  });

  $("#clearJobs").addEventListener("click", async () => {
    try {
      await api("/api/jobs/clear", { method: "POST" });
      lastJobsSignature = "";
      await refreshJobs();
    } catch (error) {
      toast(error.message, "err");
    }
  });

  $("#openFolder").addEventListener("click", async () => {
    try {
      await api("/api/open-folder", { method: "POST" });
    } catch (error) {
      toast(error.message, "err");
    }
  });

  $("#updateBtn").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Güncelleniyor…";
    try {
      const data = await api("/api/update", { method: "POST" });
      toast(`yt-dlp güncellendi (${data.installed}). Uygulamayı kapatıp yeniden başlat.`, "ok");
    } catch (error) {
      toast(error.message, "err");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  });

  /* ------------------------------- başlangıç ----------------------------- */
  setGoLabel();
  loadStatus();
  pollLoop();
  window.setInterval(loadStatus, 60000);

  $("#settingsBtn").addEventListener("click", openSettings);
  if (location.hash === "#ayarlar") openSettings();
})();

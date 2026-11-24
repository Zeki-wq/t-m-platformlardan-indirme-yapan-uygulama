## İndirici 1.2.0

### Yenilikler

- **⚙ Ayarlar ekranı (masaüstü):** Instagram, TikTok, Facebook gibi giriş isteyen siteler için tarayıcı çerezlerini (Chrome, Edge, Firefox, Brave, Opera, Vivaldi) tek tıkla seç ya da `cookies.txt` dosyanın yolunu göster. **Test et** düğmesi çerezlerin gerçekten okunduğunu söyler.
- **Android APK (ilk sürüm):** Aynı motoru (yt-dlp + Python + FFmpeg) taşıyan native Android uygulaması. Android 7.0 ve üzeri, `arm64-v8a` + `armeabi-v7a`.
- **Android'de yt-dlp güncelleme:** İlk açılışta otomatik güncellenir; ayrıca “yt-dlp'yi güncelle” düğmesi var.
- **Android paylaş menüsü:** Instagram/TikTok'ta “Paylaş → İndirici” ile link doğrudan uygulamaya gelir.
- **Daha anlaşılır hatalar:** IP engeli, kilitli çerez veritabanı, giriş gereksinimi ve **sessiz videolarda MP3** için Türkçe açıklama.
- **Sessiz video kontrolü:** Kaynakta ses akışı yoksa MP3 sekmesi kapanır, uygulama MP4 önerir (bazı Instagram reels'leri sessizdir).
- yt-dlp **2026.11.23**'e güncellendi.

### Kurulum

- **Windows:** `Indirici-Setup-1.2.0.exe` — yönetici izni gerekmez, kullanıcı bazlı kurulum.
- **Android:** `Indirici-1.0.0.apk` — telefona indir, aç, “Bilinmeyen kaynaklara izin ver”, kur.

### Bilinen sınırlamalar

- TikTok bazı ağlarda “IP address is blocked” döndürüyor; bu site tarafındaki engeldir, farklı ağ/mobil veri gerekir.
- Tarayıcı açıkken çerez dosyası kilitli olabilir; tarayıcıyı kapatıp **Test et**'e bas ya da `cookies.txt` kullan.

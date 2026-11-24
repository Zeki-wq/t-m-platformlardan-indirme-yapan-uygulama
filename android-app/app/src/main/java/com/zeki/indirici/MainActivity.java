package com.zeki.indirici;

import android.Manifest;
import android.app.DownloadManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.text.TextUtils;
import android.util.Log;
import android.view.View;
import android.webkit.MimeTypeMap;
import android.widget.ArrayAdapter;
import android.widget.EditText;
import android.widget.RadioGroup;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.google.android.material.button.MaterialButton;
import com.google.android.material.progressindicator.LinearProgressIndicator;
import com.yausername.ffmpeg.FFmpeg;
import com.yausername.youtubedl_android.YoutubeDL;
import com.yausername.youtubedl_android.YoutubeDLRequest;
import com.yausername.youtubedl_android.YoutubeDLResponse;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import kotlin.Unit;
import kotlin.jvm.functions.Function3;

public class MainActivity extends AppCompatActivity {

    private static final String TAG = "Indirici";
    private static final String PROCESS_ID = "indirici-download";
    private static final Pattern URL_PATTERN = Pattern.compile("https?://\\S+");

    private static final String[] VIDEO_OPTIONS = {"1080p", "2160p", "1440p", "720p", "480p", "360p", "En iyi"};
    private static final String[] AUDIO_OPTIONS = {"192 kbps", "320 kbps", "256 kbps", "128 kbps"};

    private EditText etUrl;
    private RadioGroup rgMode;
    private Spinner spQuality;
    private MaterialButton btnDownload;
    private MaterialButton btnCancel;
    private MaterialButton btnPaste;
    private MaterialButton btnOpenFolder;
    private MaterialButton btnUpdate;
    private LinearProgressIndicator progress;
    private TextView tvStatus;
    private TextView tvLast;

    private volatile boolean ready = false;
    private volatile boolean downloading = false;

    private final Function3<Float, Long, String, Unit> progressCallback =
            new Function3<Float, Long, String, Unit>() {
                @Override
                public Unit invoke(Float value, Long eta, String line) {
                    final float percent = value == null ? 0f : value;
                    final String text = line == null ? "" : line.trim();
                    runOnUiThread(() -> {
                        progress.setProgress((int) Math.max(0, Math.min(100, percent)));
                        if (!text.isEmpty()) {
                            tvStatus.setText(shorten(text, 120));
                        } else if (percent > 0) {
                            tvStatus.setText(String.format(Locale.US, "%%%d indiriliyor…", (int) percent));
                        }
                    });
                    return Unit.INSTANCE;
                }
            };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        etUrl = findViewById(R.id.etUrl);
        rgMode = findViewById(R.id.rgMode);
        spQuality = findViewById(R.id.spQuality);
        btnDownload = findViewById(R.id.btnDownload);
        btnCancel = findViewById(R.id.btnCancel);
        btnPaste = findViewById(R.id.btnPaste);
        btnOpenFolder = findViewById(R.id.btnOpenFolder);
        btnUpdate = findViewById(R.id.btnUpdate);
        progress = findViewById(R.id.progress);
        tvStatus = findViewById(R.id.tvStatus);
        tvLast = findViewById(R.id.tvLast);

        rgMode.setOnCheckedChangeListener((group, checkedId) -> fillQuality(checkedId == R.id.rbAudio));
        fillQuality(false);

        btnDownload.setOnClickListener(v -> startDownload());
        btnCancel.setOnClickListener(v -> cancelDownload());
        btnPaste.setOnClickListener(v -> pasteFromClipboard());
        btnOpenFolder.setOnClickListener(v -> openDownloads());
        btnUpdate.setOnClickListener(v -> updateYtdlp(true));

        handleIntent(getIntent());
        askLegacyPermission();
        initEngine();
    }

    @Override
    protected void onNewIntent(@NonNull Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    // ------------------------------------------------------------------ //
    //  Motor
    // ------------------------------------------------------------------ //
    private void initEngine() {
        setBusy(true);
        tvStatus.setTextColor(ContextCompat.getColor(this, R.color.text_dim));
        tvStatus.setText(R.string.preparing);

        new Thread(() -> {
            String error = null;
            try {
                YoutubeDL.getInstance().init(getApplicationContext());
                FFmpeg.getInstance().init(getApplicationContext());
            } catch (Throwable t) {
                Log.e(TAG, "motor başlatılamadı", t);
                error = t.getMessage();
            }
            final String err = error;
            runOnUiThread(() -> {
                if (err == null) {
                    ready = true;
                    setBusy(false);
                    tvStatus.setTextColor(ContextCompat.getColor(this, R.color.text_dim));
                    tvStatus.setText(R.string.ready);
                    autoUpdateOnce();
                } else {
                    setBusy(false);
                    tvStatus.setTextColor(ContextCompat.getColor(this, R.color.danger));
                    tvStatus.setText("İndirme motoru başlatılamadı: " + err);
                }
            });
        }, "indirici-init").start();
    }

    /** İlk açılışta yt-dlp'yi bir kez otomatik günceller (Instagram/TikTok için önemli). */
    private void autoUpdateOnce() {
        final SharedPreferences prefs = getSharedPreferences("indirici", MODE_PRIVATE);
        if (prefs.getBoolean("ytdlp_updated", false)) {
            return;
        }
        tvStatus.setText("yt-dlp güncelleniyor (ilk kurulum)…");
        new Thread(() -> {
            try {
                YoutubeDL.getInstance().updateYoutubeDL(
                        getApplicationContext(), YoutubeDL.UpdateChannel._STABLE);
                prefs.edit().putBoolean("ytdlp_updated", true).apply();
                runOnUiThread(() -> tvStatus.setText("Hazır · yt-dlp güncel"));
            } catch (Throwable t) {
                Log.w(TAG, "otomatik yt-dlp güncellemesi başarısız", t);
                runOnUiThread(() -> tvStatus.setText(
                        "Hazır (yt-dlp güncellenemedi, alttaki düğmeyle deneyebilirsin)"));
            }
        }, "indirici-update").start();
    }

    private void updateYtdlp(boolean userTriggered) {
        if (downloading) {
            toast("Önce devam eden indirmeyi bitir.");
            return;
        }
        btnUpdate.setEnabled(false);
        tvStatus.setTextColor(ContextCompat.getColor(this, R.color.text_dim));
        tvStatus.setText("yt-dlp güncelleniyor…");
        new Thread(() -> {
            String message;
            try {
                YoutubeDL.getInstance().updateYoutubeDL(
                        getApplicationContext(), YoutubeDL.UpdateChannel._STABLE);
                String version = YoutubeDL.getInstance().version(getApplicationContext());
                message = "yt-dlp güncellendi" + (version == null ? "" : ": " + version);
            } catch (Throwable t) {
                Log.e(TAG, "yt-dlp güncellenemedi", t);
                message = "Güncelleme başarısız: " + friendly(t);
            }
            final String text = message;
            runOnUiThread(() -> {
                btnUpdate.setEnabled(true);
                tvStatus.setText(text);
                toast(text);
            });
        }, "indirici-update").start();
    }

    // ------------------------------------------------------------------ //
    //  Arayüz yardımcıları
    // ------------------------------------------------------------------ //
    private void fillQuality(boolean audio) {
        String[] options = audio ? AUDIO_OPTIONS : VIDEO_OPTIONS;
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, options);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spQuality.setAdapter(adapter);
        spQuality.setSelection(0);
    }

    private void setBusy(boolean busy) {
        btnDownload.setEnabled(ready && !busy);
        btnCancel.setVisibility(busy && downloading ? View.VISIBLE : View.GONE);
        etUrl.setEnabled(!busy);
        spQuality.setEnabled(!busy);
        for (int i = 0; i < rgMode.getChildCount(); i++) {
            rgMode.getChildAt(i).setEnabled(!busy);
        }
        progress.setVisibility(busy ? View.VISIBLE : View.INVISIBLE);
        if (!busy) {
            progress.setProgress(0);
        }
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    private static String shorten(String value, int max) {
        if (value.length() <= max) {
            return value;
        }
        return value.substring(0, max - 1) + "…";
    }

    // ------------------------------------------------------------------ //
    //  Link yakalama
    // ------------------------------------------------------------------ //
    private void handleIntent(Intent intent) {
        if (intent == null) {
            return;
        }
        String text = null;
        if (Intent.ACTION_SEND.equals(intent.getAction())) {
            text = intent.getStringExtra(Intent.EXTRA_TEXT);
        } else if (Intent.ACTION_VIEW.equals(intent.getAction()) && intent.getData() != null) {
            text = intent.getData().toString();
        }
        if (TextUtils.isEmpty(text)) {
            return;
        }
        Matcher matcher = URL_PATTERN.matcher(text);
        if (matcher.find()) {
            text = matcher.group();
        }
        etUrl.setText(text.trim());
        etUrl.setSelection(etUrl.getText() == null ? 0 : etUrl.getText().length());
    }

    private void pasteFromClipboard() {
        ClipboardManager manager = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        if (manager == null || !manager.hasPrimaryClip()) {
            toast(getString(R.string.paste_empty));
            return;
        }
        ClipData clip = manager.getPrimaryClip();
        if (clip == null || clip.getItemCount() == 0) {
            toast(getString(R.string.paste_empty));
            return;
        }
        CharSequence text = clip.getItemAt(0).coerceToText(this);
        if (TextUtils.isEmpty(text)) {
            toast(getString(R.string.paste_empty));
            return;
        }
        String value = text.toString();
        Matcher matcher = URL_PATTERN.matcher(value);
        if (matcher.find()) {
            value = matcher.group();
        }
        etUrl.setText(value.trim());
    }

    private void openDownloads() {
        try {
            startActivity(new Intent(DownloadManager.ACTION_VIEW_DOWNLOADS));
        } catch (Exception e) {
            toast("İndirilenler klasörü: Download/Indirici");
        }
    }

    private void askLegacyPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            return;
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                    this, new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, 100);
        }
    }

    // ------------------------------------------------------------------ //
    //  İndirme
    // ------------------------------------------------------------------ //
    private void startDownload() {
        if (downloading) {
            return;
        }
        if (!ready) {
            toast(getString(R.string.preparing));
            return;
        }

        CharSequence raw = etUrl.getText();
        final String url = raw == null ? "" : raw.toString().trim();
        if (!url.startsWith("http")) {
            etUrl.setError(getString(R.string.url_required));
            return;
        }

        final boolean audio = rgMode.getCheckedRadioButtonId() == R.id.rbAudio;
        final String quality = String.valueOf(spQuality.getSelectedItem());

        final File work = new File(getExternalFilesDir(null), "is");
        if (!work.exists() && !work.mkdirs()) {
            toast("Geçici klasör oluşturulamadı");
            return;
        }

        final Set<String> before = new HashSet<>(Arrays.asList(names(work)));
        final long startedAt = System.currentTimeMillis();

        downloading = true;
        setBusy(true);
        tvLast.setText("");
        tvStatus.setTextColor(ContextCompat.getColor(this, R.color.text_dim));
        tvStatus.setText("Başlatılıyor…");

        new Thread(() -> {
            String error = null;
            List<String> saved = new ArrayList<>();
            try {
                YoutubeDLRequest request = buildRequest(url, audio, quality, work);
                YoutubeDLResponse response = YoutubeDL.getInstance().execute(request, PROCESS_ID, progressCallback);
                Log.i(TAG, "exit=" + response.getExitCode() + " out=" + response.getOut());
                saved = publishNew(work, before, startedAt);
            } catch (Throwable t) {
                Log.e(TAG, "indirme hatası", t);
                error = friendly(t);
            }

            final String err = error;
            final List<String> savedFiles = saved;
            runOnUiThread(() -> {
                downloading = false;
                setBusy(false);
                if (err != null) {
                    tvStatus.setTextColor(ContextCompat.getColor(this, R.color.danger));
                    tvStatus.setText(err);
                } else if (savedFiles.isEmpty()) {
                    tvStatus.setTextColor(ContextCompat.getColor(this, R.color.danger));
                    tvStatus.setText("İndirme bitti ama dosya bulunamadı. Linki kontrol et.");
                } else {
                    progress.setProgress(100);
                    tvStatus.setTextColor(ContextCompat.getColor(this, R.color.success));
                    tvStatus.setText("Tamamlandı ✓");
                    tvLast.setText("Kaydedildi:\n" + TextUtils.join("\n", savedFiles));
                }
            });
        }, "indirici-download").start();
    }

    private void cancelDownload() {
        try {
            YoutubeDL.getInstance().destroyProcessById(PROCESS_ID);
            tvStatus.setText("İptal ediliyor…");
        } catch (Exception e) {
            Log.w(TAG, "iptal edilemedi", e);
        }
    }

    private YoutubeDLRequest buildRequest(String url, boolean audio, String quality, File work) {
        YoutubeDLRequest request = new YoutubeDLRequest(url);
        request.addOption("--no-mtime");
        request.addOption("--concurrent-fragments", 4);
        request.addOption("--retries", 5);
        request.addOption("-o", new File(work, "%(title).80B [%(id)s].%(ext)s").getAbsolutePath());

        if (audio) {
            int kbps = digits(quality);
            if (kbps <= 0) {
                kbps = 192;
            }
            request.addOption("-x");
            request.addOption("--audio-format", "mp3");
            request.addOption("--audio-quality", kbps + "K");
            request.addOption("--embed-metadata");
        } else {
            String selector;
            int height = digits(quality);
            if (height <= 0) {
                selector = "bv*+ba/b";
            } else {
                selector = "bv*[height<=" + height + "]+ba/b[height<=" + height + "]/b";
            }
            request.addOption("-f", selector);
            request.addOption("--merge-output-format", "mp4");
        }
        return request;
    }

    private static int digits(String value) {
        if (value == null) {
            return 0;
        }
        String only = value.replaceAll("[^0-9]", "");
        if (only.isEmpty()) {
            return 0;
        }
        try {
            return Integer.parseInt(only);
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private static String[] names(File dir) {
        String[] result = dir.list();
        return result == null ? new String[0] : result;
    }

    private List<String> publishNew(File work, Set<String> before, long startedAt) {
        List<String> published = new ArrayList<>();
        File[] files = work.listFiles();
        if (files == null) {
            return published;
        }
        Arrays.sort(files, Comparator.comparingLong(File::lastModified));
        for (File file : files) {
            if (!file.isFile()) {
                continue;
            }
            String name = file.getName();
            if (name.endsWith(".part") || name.endsWith(".ytdl") || name.endsWith(".temp")) {
                continue;
            }
            boolean isNew = !before.contains(name) || file.lastModified() >= startedAt - 3000;
            if (!isNew) {
                continue;
            }
            try {
                published.add(publish(file));
                if (!file.delete()) {
                    Log.w(TAG, "geçici dosya silinemedi: " + name);
                }
            } catch (Exception e) {
                Log.e(TAG, "kaydetme hatası", e);
                published.add(file.getAbsolutePath());
            }
        }
        return published;
    }

    /** Geçici dosyayı İndirilenler/Indirici klasörüne taşır. */
    private String publish(File file) throws IOException {
        String name = file.getName();
        int dot = name.lastIndexOf('.');
        String ext = dot >= 0 ? name.substring(dot + 1).toLowerCase(Locale.ROOT) : "";
        String mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
        if (mime == null) {
            mime = "audio".equals(ext) || "mp3".equals(ext) ? "audio/mpeg" : "application/octet-stream";
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ContentValues values = new ContentValues();
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
            values.put(MediaStore.MediaColumns.MIME_TYPE, mime);
            values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Indirici");
            values.put(MediaStore.MediaColumns.IS_PENDING, 1);

            Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (uri == null) {
                throw new IOException("MediaStore kaydı açılamadı");
            }
            try (InputStream in = new FileInputStream(file);
                 OutputStream out = getContentResolver().openOutputStream(uri)) {
                if (out == null) {
                    throw new IOException("Çıkış akışı açılamadı");
                }
                copy(in, out);
            }
            ContentValues done = new ContentValues();
            done.put(MediaStore.MediaColumns.IS_PENDING, 0);
            getContentResolver().update(uri, done, null, null);
            return "Download/Indirici/" + name;
        }

        File dir = new File(
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "Indirici");
        if (!dir.exists() && !dir.mkdirs()) {
            throw new IOException("İndirilenler klasörü oluşturulamadı");
        }
        File target = new File(dir, name);
        try (InputStream in = new FileInputStream(file);
             OutputStream out = new FileOutputStream(target)) {
            copy(in, out);
        }
        return target.getAbsolutePath();
    }

    private static void copy(InputStream in, OutputStream out) throws IOException {
        byte[] buffer = new byte[16384];
        int read;
        while ((read = in.read(buffer)) > 0) {
            out.write(buffer, 0, read);
        }
        out.flush();
    }

    // ------------------------------------------------------------------ //
    //  Hata mesajları
    // ------------------------------------------------------------------ //
    private static String friendly(Throwable throwable) {
        String message = throwable.getMessage();
        if (TextUtils.isEmpty(message)) {
            message = throwable.toString();
        }
        String clean = message.replaceAll("\u001B\\[[0-9;]*m", "").trim();
        String low = clean.toLowerCase(Locale.ROOT);

        if (low.contains("unsupported url")) {
            return "Bu site veya link desteklenmiyor.";
        }
        if (low.contains("canceled") || low.contains("cancelled")) {
            return "İndirme iptal edildi.";
        }
        if (low.contains("login") || low.contains("cookies") || low.contains("sign in")) {
            return "Bu içerik giriş gerektiriyor (özel ya da yaş kısıtlı). Herkese açık bir link dene.";
        }
        if (low.contains("private")) {
            return "İçerik gizli olduğu için indirilemiyor.";
        }
        if (low.contains("unavailable") || low.contains("not available") || low.contains("removed")) {
            return "İçerik kullanılamıyor (kaldırılmış veya bölgene kapalı olabilir).";
        }
        if (low.contains("timed out") || low.contains("timeout")) {
            return "Bağlantı zaman aşımına uğradı. Tekrar dene.";
        }
        if (low.contains("unable to resolve host") || low.contains("network")
                || low.contains("connection")) {
            return "İnternet bağlantısı kurulamadı. Bağlantını kontrol et.";
        }
        if (low.contains("no space")) {
            return "Cihazda yeterli alan yok.";
        }

        for (String line : clean.split("\n")) {
            if (line.startsWith("ERROR:")) {
                clean = line.substring(6).trim();
                break;
            }
        }
        return shorten(clean, 300);
    }
}

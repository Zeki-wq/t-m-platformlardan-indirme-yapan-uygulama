package com.zeki.indirici;

import android.app.Application;
import android.util.Log;

/**
 * Uygulama girişi. İndirme motoru (yt-dlp + python + ffmpeg) ağır olduğu için
 * MainActivity içinde arka planda başlatılır; burada sadece temel kurulum var.
 */
public class App extends Application {

    public static final String TAG = "Indirici";

    @Override
    public void onCreate() {
        super.onCreate();
        Log.i(TAG, "İndirici başlatıldı");
    }
}

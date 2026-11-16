package com.example.quickanswer

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import android.util.DisplayMetrics
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.TextView
import kotlin.math.abs

class OverlayService : Service() {

    private lateinit var wm: WindowManager
    private var projection: MediaProjection? = null
    private var projectionCallback: MediaProjection.Callback? = null
    private var reader: ImageReader? = null
    private var display: VirtualDisplay? = null
    private var pill: TextView? = null
    private var highlight: HighlightView? = null
    private var rebase = false

    private val ui = Handler(Looper.getMainLooper())
    private var workThread: HandlerThread? = null
    private var work: Handler? = null

    // Latest frame, kept ready so a tap can send it immediately.
    @Volatile
    private var latest: Bitmap? = null
    private var lastConvert = 0L

    private var busy = false
    private var auto = false
    private var prevHash: IntArray? = null
    private var sentHash: IntArray? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (projection != null) return START_NOT_STICKY

        val code = intent?.getIntExtra("code", 0) ?: 0
        val data = readData(intent)
        if (data == null) {
            stopSelf()
            return START_NOT_STICKY
        }

        startAsForeground()
        wm = getSystemService(WINDOW_SERVICE) as WindowManager

        workThread = HandlerThread("qa-work").also { it.start() }
        work = Handler(workThread!!.looper)

        val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val p = mpm.getMediaProjection(code, data)
        projection = p

        // Android 14+ requires a callback to be registered before creating the display.
        projectionCallback = object : MediaProjection.Callback() {
            override fun onStop() {
                stopSelf()
            }
        }
        p.registerCallback(projectionCallback!!, ui)

        setupCapture(p)
        addHighlight()
        addPill()
        return START_NOT_STICKY
    }

    @Suppress("DEPRECATION")
    private fun readData(intent: Intent?): Intent? =
        if (Build.VERSION.SDK_INT >= 33) {
            intent?.getParcelableExtra("data", Intent::class.java)
        } else {
            intent?.getParcelableExtra("data")
        }

    private fun startAsForeground() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel("qa", "QuickAnswer", NotificationManager.IMPORTANCE_LOW)
        )
        val n = Notification.Builder(this, "qa")
            .setContentTitle("QuickAnswer")
            .setContentText("در حال اجرا")
            .setSmallIcon(android.R.drawable.ic_menu_search)
            .build()
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        } else {
            startForeground(1, n)
        }
    }

    @Suppress("DEPRECATION")
    private fun setupCapture(p: MediaProjection) {
        val real = DisplayMetrics()
        wm.defaultDisplay.getRealMetrics(real)

        // Capture at reduced resolution: cheaper to convert and to upload.
        val capW = 720
        val capH = (real.heightPixels.toFloat() * capW / real.widthPixels).toInt()

        val r = ImageReader.newInstance(capW, capH, PixelFormat.RGBA_8888, 2)
        reader = r
        r.setOnImageAvailableListener({ onFrame(it) }, work)

        display = p.createVirtualDisplay(
            "qa", capW, capH, real.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            r.surface, null, null
        )
    }

    private fun onFrame(r: ImageReader) {
        val img = r.acquireLatestImage() ?: return
        try {
            val now = SystemClock.uptimeMillis()
            if (now - lastConvert < 120) return // throttle conversion
            lastConvert = now

            val plane = img.planes[0]
            val rowPad = plane.rowStride - plane.pixelStride * img.width
            val full = Bitmap.createBitmap(
                img.width + rowPad / plane.pixelStride, img.height, Bitmap.Config.ARGB_8888
            )
            full.copyPixelsFromBuffer(plane.buffer)
            latest = if (rowPad == 0) full else Bitmap.createBitmap(full, 0, 0, img.width, img.height)
        } finally {
            img.close()
        }
    }

    // ---------- solving ----------

    private fun solveNow() {
        if (busy) return
        busy = true
        show("⏳")

        // Remove the old highlight first and give the capture a moment to catch up,
        // so the model never sees our own overlay.
        val delay = if (highlight?.hasBox == true) 200L else 0L
        highlight?.clear()

        ui.postDelayed({
            val bmp = latest
            if (bmp == null) {
                busy = false
                show("…")
                return@postDelayed
            }
            val key = getSharedPreferences("qa", MODE_PRIVATE).getString("apikey", "").orEmpty()
            work?.post {
                Solver.solve(bmp, key) { text, box ->
                    ui.post {
                        busy = false
                        show(text)
                        if (box != null) {
                            highlight?.set(box)
                            rebase = true // next stable frame (with highlight) becomes the baseline
                        }
                    }
                }
            }
        }, delay)
    }

    private fun toggleAuto() {
        auto = !auto
        prevHash = null
        sentHash = null
        rebase = false
        highlight?.clear()
        show(if (auto) "AUTO" else "OFF")
        ui.removeCallbacks(autoTick)
        if (auto) ui.postDelayed(autoTick, 350)
    }

    // Auto mode: call the model only when the screen has settled on something new.
    private val autoTick = object : Runnable {
        override fun run() {
            if (!auto) return
            val b = latest
            if (b != null && !busy) {
                val h = hashOf(b)
                val p = prevHash
                prevHash = h
                val s0 = sentHash
                // Screen moved on: drop the stale highlight right away.
                if (!rebase && s0 != null && highlight?.hasBox == true && diff(s0, h) >= 8) {
                    highlight?.clear()
                }
                if (p != null && diff(p, h) < 4) {
                    if (rebase) {
                        sentHash = h
                        rebase = false
                    } else {
                        val s = sentHash
                        if (s == null || diff(s, h) >= 8) {
                            sentHash = h
                            solveNow()
                        }
                    }
                }
            }
            ui.postDelayed(this, 350)
        }
    }

    private fun hashOf(b: Bitmap): IntArray {
        val s = Bitmap.createScaledBitmap(b, 16, 16, true)
        val px = IntArray(256)
        s.getPixels(px, 0, 16, 0, 0, 16, 16)
        return IntArray(256) {
            val c = px[it]
            (Color.red(c) + Color.green(c) + Color.blue(c)) / 3
        }
    }

    private fun diff(a: IntArray, b: IntArray): Int {
        var sum = 0
        for (i in a.indices) sum += abs(a[i] - b[i])
        return sum / a.size
    }

    // ---------- overlay ----------

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun show(text: String) {
        pill?.text = text
    }

    @Suppress("DEPRECATION")
    private fun addHighlight() {
        val real = DisplayMetrics()
        wm.defaultDisplay.getRealMetrics(real)

        val v = HighlightView(this)
        val lp = WindowManager.LayoutParams(
            real.widthPixels,
            real.heightPixels,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply { gravity = Gravity.TOP or Gravity.START }

        wm.addView(v, lp)
        highlight = v
    }

    private fun addPill() {
        val tv = TextView(this).apply {
            text = "؟"
            textSize = 20f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            textDirection = View.TEXT_DIRECTION_FIRST_STRONG
            setPadding(dp(18), dp(10), dp(18), dp(10))
            maxWidth = (resources.displayMetrics.widthPixels * 0.8).toInt()
            background = GradientDrawable().apply {
                cornerRadius = dp(28).toFloat()
                setColor(0xE61565C0.toInt())
            }
        }

        val lp = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = dp(8)
            y = dp(200)
        }

        var sx = 0f
        var sy = 0f
        var ox = 0
        var oy = 0
        var moved = false
        var downAt = 0L

        tv.setOnTouchListener { _, e ->
            when (e.action) {
                MotionEvent.ACTION_DOWN -> {
                    sx = e.rawX; sy = e.rawY
                    ox = lp.x; oy = lp.y
                    moved = false
                    downAt = SystemClock.uptimeMillis()
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (e.rawX - sx).toInt()
                    val dy = (e.rawY - sy).toInt()
                    if (abs(dx) > 10 || abs(dy) > 10) moved = true
                    if (moved) {
                        lp.x = ox + dx
                        lp.y = oy + dy
                        wm.updateViewLayout(tv, lp)
                    }
                }
                MotionEvent.ACTION_UP -> {
                    if (!moved) {
                        if (SystemClock.uptimeMillis() - downAt > 600) toggleAuto() else solveNow()
                    }
                }
            }
            true
        }

        wm.addView(tv, lp)
        pill = tv
    }

    override fun onDestroy() {
        auto = false
        ui.removeCallbacksAndMessages(null)
        pill?.let { runCatching { wm.removeView(it) } }
        pill = null
        highlight?.let { runCatching { wm.removeView(it) } }
        highlight = null
        display?.release()
        reader?.close()
        projection?.let { p ->
            projectionCallback?.let { runCatching { p.unregisterCallback(it) } }
            runCatching { p.stop() }
        }
        projection = null
        workThread?.quitSafely()
        super.onDestroy()
    }
}

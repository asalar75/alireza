package com.example.quickanswer

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {

    private lateinit var keyInput: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val pad = (20 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad * 2, pad, pad)
            layoutDirection = LinearLayout.LAYOUT_DIRECTION_RTL
        }

        root.addView(TextView(this).apply {
            text = "QuickAnswer"
            textSize = 24f
            gravity = Gravity.CENTER
        })

        keyInput = EditText(this).apply {
            hint = "کلید API (sk-ant-...)"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setText(prefs().getString("apikey", ""))
        }
        root.addView(keyInput)

        root.addView(Button(this).apply {
            text = "شروع"
            setOnClickListener { start() }
        })
        root.addView(Button(this).apply {
            text = "توقف"
            setOnClickListener { stopService(Intent(this@MainActivity, OverlayService::class.java)) }
        })
        root.addView(TextView(this).apply {
            text = "پس از شروع، یک دکمهٔ شناور روی صفحه می‌آید.\n" +
                "• لمس کوتاه: تشخیص همین لحظه\n" +
                "• لمس طولانی: روشن/خاموش کردن حالت خودکار\n" +
                "• کشیدن: جابه‌جایی دکمه"
            setPadding(0, pad, 0, 0)
        })

        setContentView(root)

        if (Build.VERSION.SDK_INT >= 33) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }
    }

    private fun prefs() = getSharedPreferences("qa", Context.MODE_PRIVATE)

    private fun start() {
        prefs().edit().putString("apikey", keyInput.text.toString().trim()).apply()

        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "مجوز نمایش روی برنامه‌های دیگر را فعال کنید", Toast.LENGTH_LONG).show()
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
            return
        }

        val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        startActivityForResult(mpm.createScreenCaptureIntent(), 100)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 100 && resultCode == RESULT_OK && data != null) {
            val svc = Intent(this, OverlayService::class.java)
                .putExtra("code", resultCode)
                .putExtra("data", data)
            startForegroundService(svc)
            moveTaskToBack(true)
        }
    }
}

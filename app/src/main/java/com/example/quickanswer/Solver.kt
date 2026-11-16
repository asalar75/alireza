package com.example.quickanswer

import android.graphics.Bitmap
import android.graphics.RectF
import android.util.Base64
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Sends a screenshot straight to a vision model and returns the correct option
 * plus where it sits on screen (as fractions 0..1), so it can be highlighted.
 * No OCR step: lower latency, and it works for Persian text.
 */
object Solver {

    // Fastest model tier; swap for a stronger model if accuracy matters more than speed.
    private const val MODEL = "claude-haiku-5-5"
    private const val URL = "https://api.anthropic.com/v1/messages"

    private const val PROMPT =
        "The screenshot may show a multiple-choice quiz question with exactly 4 options. " +
        "If it does, answer the question and reply ONLY in this exact format: " +
        "<number>|<cx>|<cy>|<w>|<h>|<text of the correct option> " +
        "where cx, cy, w, h are integers from 0 to 100: the center x, center y, width and height " +
        "of the correct option's button or box, as a percentage of the screenshot width/height. " +
        "Number options by visual position: top to bottom, and left to right within a row " +
        "(right to left if the text is Persian or Arabic). " +
        "If there is no 4-option question on screen, reply with a single dash: -"

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    /** onResult(text, box) — box is null when the position could not be determined. */
    fun solve(bitmap: Bitmap, apiKey: String, onResult: (String, RectF?) -> Unit) {
        if (apiKey.isBlank()) {
            onResult("کلید API وارد نشده", null)
            return
        }

        val jpeg = ByteArrayOutputStream().also { bitmap.compress(Bitmap.CompressFormat.JPEG, 55, it) }
        val b64 = Base64.encodeToString(jpeg.toByteArray(), Base64.NO_WRAP)

        val content = JSONArray()
            .put(
                JSONObject()
                    .put("type", "image")
                    .put(
                        "source", JSONObject()
                            .put("type", "base64")
                            .put("media_type", "image/jpeg")
                            .put("data", b64)
                    )
            )
            .put(JSONObject().put("type", "text").put("text", PROMPT))

        val body = JSONObject()
            .put("model", MODEL)
            .put("max_tokens", 60)
            .put("temperature", 0)
            .put("messages", JSONArray().put(JSONObject().put("role", "user").put("content", content)))

        val request = Request.Builder()
            .url(URL)
            .header("x-api-key", apiKey)
            .header("anthropic-version", "2023-06-01")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()

        client.newCall(request).enqueue(object : okhttp3.Callback {
            override fun onFailure(call: okhttp3.Call, e: IOException) {
                onResult("خطای شبکه", null)
            }

            override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) {
                response.use { r ->
                    val raw = r.body?.string().orEmpty()
                    if (!r.isSuccessful) {
                        onResult("خطا ${r.code}", null)
                        return
                    }
                    val text = try {
                        JSONObject(raw).getJSONArray("content").getJSONObject(0).getString("text").trim()
                    } catch (e: Exception) {
                        onResult("پاسخ نامعتبر", null)
                        return
                    }
                    if (text == "-") {
                        onResult("سؤالی پیدا نشد", null)
                        return
                    }
                    parse(text, onResult)
                }
            }
        })
    }

    private fun parse(text: String, onResult: (String, RectF?) -> Unit) {
        val p = text.split("|", limit = 6).map { it.trim() }
        if (p.size == 6) {
            val n = p[1].toFloatOrNull()
            val cy = p[2].toFloatOrNull()
            val w = p[3].toFloatOrNull()
            val h = p[4].toFloatOrNull()
            if (n != null && cy != null && w != null && h != null) {
                val cx = n / 100f
                val cyf = cy / 100f
                // Pad the box slightly so the highlight fully surrounds the option.
                val hw = (w / 100f) / 2f + 0.01f
                val hh = (h / 100f) / 2f + 0.005f
                val box = RectF(
                    (cx - hw).coerceIn(0f, 1f), (cyf - hh).coerceIn(0f, 1f),
                    (cx + hw).coerceIn(0f, 1f), (cyf + hh).coerceIn(0f, 1f)
                )
                onResult("${p[0]}) ${p[5]}", box)
                return
            }
        }
        onResult(text, null)
    }
}

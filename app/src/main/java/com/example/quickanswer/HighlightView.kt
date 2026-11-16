package com.example.quickanswer

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.view.View

/** Full-screen, touch-transparent layer that outlines the correct option. */
class HighlightView(ctx: Context) : View(ctx) {

    private var box: RectF? = null
    private val density = ctx.resources.displayMetrics.density

    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f * density
        color = 0xFF00E676.toInt()
    }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0x3300E676
    }

    val hasBox: Boolean get() = box != null

    fun set(fractions: RectF) {
        box = fractions
        invalidate()
    }

    fun clear() {
        if (box != null) {
            box = null
            invalidate()
        }
    }

    override fun onDraw(canvas: Canvas) {
        val b = box ?: return
        val r = RectF(b.left * width, b.top * height, b.right * width, b.bottom * height)
        val radius = 14f * density
        canvas.drawRoundRect(r, radius, radius, fill)
        canvas.drawRoundRect(r, radius, radius, stroke)
    }
}

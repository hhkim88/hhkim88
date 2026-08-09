package com.hhkim88.typofix.ime

import android.content.Context
import android.graphics.Typeface
import android.os.Handler
import android.os.Looper
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import com.hhkim88.typofix.R

/**
 * A fully custom, view-hierarchy-based keyboard: no system keyboard involved.
 * Each key is a plain TextView built programmatically from [KeyboardLayout], since a
 * real drawn/touch-hit-tested canvas keyboard isn't needed for this app to work correctly.
 */
class KeyboardView(context: Context) : LinearLayout(context) {

    var listener: KeyboardActionListener? = null

    private var mode: KeyboardMode = KeyboardMode.HANGUL
    private var shifted: Boolean = false
    private val repeatHandler = Handler(Looper.getMainLooper())

    init {
        orientation = VERTICAL
        setBackgroundColor(getColor(R.color.keyboard_background))
        setPadding(dp(4), dp(6), dp(4), dp(6))
        rebuild()
    }

    fun setMode(newMode: KeyboardMode) {
        mode = newMode
        shifted = false
        rebuild()
    }

    private fun toggleShift() {
        shifted = !shifted
        rebuild()
    }

    private fun rebuild() {
        removeAllViews()
        val rows = if (mode == KeyboardMode.HANGUL) KeyboardLayout.hangulRows else KeyboardLayout.symbolRows
        rows.forEach { row -> addView(buildRow(row)) }
    }

    private fun buildRow(keys: List<Key>): LinearLayout {
        val row = LinearLayout(context).apply {
            orientation = HORIZONTAL
            layoutParams = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(4)
            }
        }
        keys.forEach { key -> row.addView(buildKeyView(key)) }
        return row
    }

    private fun buildKeyView(key: Key): View {
        val label = labelFor(key)
        val isSpecial = key !is Key.Letter && key !is Key.Symbol

        val textView = TextView(context).apply {
            text = label
            gravity = Gravity.CENTER
            setTextColor(getColor(R.color.key_text))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, if (isSpecial) 13f else 18f)
            if (key is Key.Shift && shifted) setTypeface(typeface, Typeface.BOLD)
            setBackgroundResource(
                if (isSpecial) R.drawable.key_background_special else R.drawable.key_background_normal
            )
            layoutParams = LayoutParams(0, dp(46), key.flexWeight).apply {
                marginStart = dp(2)
                marginEnd = dp(2)
            }
        }

        if (key is Key.Backspace) {
            attachRepeatOnLongPress(textView) { listener?.onBackspace() }
        } else {
            textView.setOnClickListener { handleKey(key) }
        }

        return textView
    }

    private fun handleKey(key: Key) {
        when (key) {
            is Key.Letter -> {
                listener?.onHangulJamo(if (shifted) key.shifted else key.normal)
                if (shifted) {
                    shifted = false
                    rebuild()
                }
            }
            is Key.Symbol -> listener?.onSymbol(key.char)
            Key.Shift -> toggleShift()
            Key.Backspace -> listener?.onBackspace()
            Key.Space -> listener?.onSpace()
            Key.Enter -> listener?.onEnter()
            Key.ToSymbols -> setMode(KeyboardMode.SYMBOLS)
            Key.ToHangul -> setMode(KeyboardMode.HANGUL)
        }
    }

    private fun labelFor(key: Key): String = when (key) {
        is Key.Letter -> (if (shifted) key.shifted else key.normal).toString()
        is Key.Symbol -> key.char.toString()
        Key.Shift -> context.getString(R.string.key_shift)
        Key.Backspace -> "⌫"
        Key.Space -> context.getString(R.string.key_space)
        Key.Enter -> context.getString(R.string.key_enter)
        Key.ToSymbols -> context.getString(R.string.key_symbols)
        Key.ToHangul -> context.getString(R.string.key_hangul)
    }

    private fun attachRepeatOnLongPress(view: View, action: () -> Unit) {
        val repeatIntervalMs = 60L
        val initialDelayMs = 350L
        val repeatRunnable = object : Runnable {
            override fun run() {
                action()
                repeatHandler.postDelayed(this, repeatIntervalMs)
            }
        }
        view.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    action()
                    repeatHandler.postDelayed(repeatRunnable, initialDelayMs)
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    repeatHandler.removeCallbacks(repeatRunnable)
                }
            }
            true
        }
    }

    private fun dp(value: Int): Int =
        TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value.toFloat(), resources.displayMetrics).toInt()

    private fun getColor(resId: Int): Int = androidx.core.content.ContextCompat.getColor(context, resId)
}

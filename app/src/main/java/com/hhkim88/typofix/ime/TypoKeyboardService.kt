package com.hhkim88.typofix.ime

import android.inputmethodservice.InputMethodService
import android.view.Gravity
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import com.hhkim88.typofix.R
import com.hhkim88.typofix.core.CorrectionEngine
import com.hhkim88.typofix.core.HangulComposer
import com.hhkim88.typofix.core.WordAttemptTracker
import com.hhkim88.typofix.data.AppDatabase
import com.hhkim88.typofix.data.RoomCorrectionStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel

/**
 * The whole app in one place: a custom Hangul keyboard that (a) types, and (b) watches how the
 * user edits each word before finishing it, learning personal typo -> correction pairs and
 * auto-applying them once confident. See com.hhkim88.typofix.core for the reusable, unit-tested
 * logic (Hangul composition, word-attempt tracking, correction confidence).
 */
class TypoKeyboardService : InputMethodService(), KeyboardActionListener {

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private val composer = HangulComposer()
    private val tracker = WordAttemptTracker()
    private lateinit var correctionEngine: CorrectionEngine

    private lateinit var keyboardView: KeyboardView
    private lateinit var statusStrip: TextView
    private lateinit var autoCorrectToggle: TextView

    private data class AutoCorrectRecord(val original: String, val applied: String, val trailing: String)
    private var lastAutoCorrect: AutoCorrectRecord? = null

    // Not persisted on purpose: a quick, thumb-reachable pause for auto-correct, not a permanent
    // setting. Learning keeps happening while paused; only the auto-apply step is skipped.
    private var autoCorrectEnabled = true

    override fun onCreate() {
        super.onCreate()
        val dao = AppDatabase.get(applicationContext).typoCorrectionDao()
        val store = RoomCorrectionStore(dao, serviceScope)
        correctionEngine = CorrectionEngine(store)
    }

    override fun onCreateInputView(): View {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        statusStrip = TextView(this).apply {
            setBackgroundColor(ContextCompat.getColor(context, R.color.strip_background))
            setTextColor(ContextCompat.getColor(context, R.color.strip_text))
            textSize = 14f
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(8), dp(12), dp(8))
            visibility = View.GONE
            setOnClickListener { revertLastAutoCorrect() }
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }

        // Always-visible, thumb-reachable pause button: sits directly above the keys (right
        // where thumbs already rest while typing), not tucked into a settings screen.
        autoCorrectToggle = TextView(this).apply {
            textSize = 13f
            gravity = Gravity.CENTER
            setPadding(dp(14), dp(10), dp(14), dp(10))
            contentDescription = getString(R.string.autocorrect_toggle_description)
            setOnClickListener {
                autoCorrectEnabled = !autoCorrectEnabled
                updateToggleAppearance()
            }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                marginStart = dp(8)
                marginEnd = dp(8)
                topMargin = dp(4)
                bottomMargin = dp(4)
                gravity = Gravity.CENTER_VERTICAL
            }
        }
        updateToggleAppearance()

        val topBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(ContextCompat.getColor(context, R.color.strip_background))
            addView(statusStrip)
            addView(autoCorrectToggle)
        }

        keyboardView = KeyboardView(this).apply {
            listener = this@TypoKeyboardService
        }

        container.addView(topBar)
        container.addView(keyboardView)
        return container
    }

    private fun updateToggleAppearance() {
        autoCorrectToggle.text = getString(
            if (autoCorrectEnabled) R.string.autocorrect_toggle_on else R.string.autocorrect_toggle_off
        )
        autoCorrectToggle.setBackgroundResource(
            if (autoCorrectEnabled) R.drawable.toggle_on_background else R.drawable.toggle_off_background
        )
        autoCorrectToggle.setTextColor(
            ContextCompat.getColor(
                this,
                if (autoCorrectEnabled) R.color.toggle_on_text else R.color.toggle_off_text
            )
        )
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        composer.reset()
        tracker.reset()
        lastAutoCorrect = null
        hideAutoCorrectHint()
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        super.onFinishInputView(finishingInput)
        // Best-effort: still learn from whatever the user did to this word, but never try to
        // mutate the host app's text at a moment when focus may already be gone.
        correctionEngine.observeSelfCorrection(tracker.finalizeWord())
        composer.reset()
        hideAutoCorrectHint()
    }

    override fun onDestroy() {
        super.onDestroy()
        serviceScope.cancel()
    }

    // --- KeyboardActionListener ---

    override fun onHangulJamo(jamo: Char) {
        if (HangulComposer.isConsonant(jamo)) composer.inputConsonant(jamo) else composer.inputVowel(jamo)
        tracker.update(composer.text)
        updateComposingDisplay()
    }

    override fun onSymbol(char: Char) {
        finalizeAndCommitWord(char.toString())
    }

    override fun onBackspace() {
        val ic = currentInputConnection ?: return
        if (composer.backspace()) {
            tracker.update(composer.text)
            updateComposingDisplay()
        } else {
            ic.finishComposingText()
            ic.deleteSurroundingText(1, 0)
            tracker.reset()
        }
        hideAutoCorrectHint()
    }

    override fun onSpace() {
        finalizeAndCommitWord(" ")
    }

    override fun onEnter() {
        val ic = currentInputConnection ?: return
        val action = (currentInputEditorInfo?.imeOptions ?: 0) and EditorInfo.IME_MASK_ACTION
        val performable = action in PERFORMABLE_ACTIONS
        if (performable) {
            finalizeAndCommitWord("")
            ic.performEditorAction(action)
        } else {
            finalizeAndCommitWord("\n")
        }
    }

    // --- Core logic glue ---

    private fun finalizeAndCommitWord(trailing: String) {
        val ic = currentInputConnection ?: return
        val typedWord = composer.text
        correctionEngine.observeSelfCorrection(tracker.finalizeWord())

        if (typedWord.isEmpty()) {
            composer.reset()
            if (trailing.isNotEmpty()) ic.commitText(trailing, 1)
            lastAutoCorrect = null
            hideAutoCorrectHint()
            return
        }

        // Learning always happens (above); only the auto-apply step respects the pause toggle.
        val suggestion = if (autoCorrectEnabled) correctionEngine.suggestCorrection(typedWord) else null
        val finalWord = suggestion ?: typedWord
        ic.setComposingText(finalWord, 1)
        ic.finishComposingText()
        if (trailing.isNotEmpty()) ic.commitText(trailing, 1)

        if (suggestion != null) {
            lastAutoCorrect = AutoCorrectRecord(typedWord, suggestion, trailing)
            showAutoCorrectHint(typedWord, suggestion)
        } else {
            lastAutoCorrect = null
            hideAutoCorrectHint()
        }
        composer.reset()
    }

    private fun revertLastAutoCorrect() {
        val record = lastAutoCorrect ?: return
        val ic = currentInputConnection ?: return
        ic.deleteSurroundingText(record.applied.length + record.trailing.length, 0)
        ic.commitText(record.original + record.trailing, 1)
        correctionEngine.forget(record.original)
        lastAutoCorrect = null
        hideAutoCorrectHint()
    }

    private fun updateComposingDisplay() {
        currentInputConnection?.setComposingText(composer.text, 1)
    }

    private fun showAutoCorrectHint(typo: String, correction: String) {
        statusStrip.text = getString(R.string.autocorrect_hint_format, typo, correction)
        statusStrip.visibility = View.VISIBLE
    }

    private fun hideAutoCorrectHint() {
        statusStrip.visibility = View.GONE
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()

    companion object {
        private val PERFORMABLE_ACTIONS = setOf(
            EditorInfo.IME_ACTION_SEND,
            EditorInfo.IME_ACTION_GO,
            EditorInfo.IME_ACTION_SEARCH,
            EditorInfo.IME_ACTION_DONE,
            EditorInfo.IME_ACTION_NEXT
        )
    }
}

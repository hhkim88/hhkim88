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
import com.hhkim88.typofix.core.DictionarySuggester
import com.hhkim88.typofix.core.HangulComposer
import com.hhkim88.typofix.core.WordAttemptTracker
import com.hhkim88.typofix.core.WordListDictionary
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
 * logic (Hangul composition, word-attempt tracking, correction confidence, dictionary matching).
 *
 * Two independent correction signals feed into the same word-boundary decision:
 *  - Personal memory ([CorrectionEngine.suggestCorrection]): a typo this exact user has
 *    self-corrected before, confident enough to auto-apply silently.
 *  - Dictionary plausibility ([DictionarySuggester]): a word that was never self-corrected
 *    (no personal history at all) but doesn't look like a real word, and is unambiguously close
 *    to exactly one real one. This is only ever shown as a tappable suggestion, never applied
 *    silently, since "not in a small seed dictionary" is much weaker evidence than "this exact
 *    user fixed this exact typo before".
 */
class TypoKeyboardService : InputMethodService(), KeyboardActionListener {

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private val composer = HangulComposer()
    private val tracker = WordAttemptTracker()
    private lateinit var correctionEngine: CorrectionEngine
    private lateinit var dictionarySuggester: DictionarySuggester

    private lateinit var keyboardView: KeyboardView
    private lateinit var statusStrip: TextView
    private lateinit var autoCorrectToggle: TextView

    private enum class WordActionMode { REVERT_AUTOCORRECT, APPLY_SUGGESTION }

    /**
     * What's currently sitting right before the cursor, and what tapping the status strip would
     * do about it. [committedText] is what's actually in the text field right now; [alternativeText]
     * is what tapping would swap it for.
     */
    private data class WordAction(
        val committedText: String,
        val trailing: String,
        val alternativeText: String,
        val mode: WordActionMode
    )

    private var pendingWordAction: WordAction? = null

    // Not persisted on purpose: a quick, thumb-reachable pause for auto-correct, not a permanent
    // setting. Learning keeps happening while paused; only the auto-apply step is skipped.
    private var autoCorrectEnabled = true

    override fun onCreate() {
        super.onCreate()
        val dao = AppDatabase.get(applicationContext).typoCorrectionDao()
        val store = RoomCorrectionStore(dao, serviceScope)
        correctionEngine = CorrectionEngine(store)
        dictionarySuggester = DictionarySuggester(WordListDictionary(loadBundledDictionary()))
    }

    private fun loadBundledDictionary(): List<String> =
        assets.open(DICTIONARY_ASSET).bufferedReader().useLines { lines ->
            lines.map { it.trim() }.filter { it.isNotEmpty() && !it.startsWith("#") }.toList()
        }

    override fun onCreateInputView(): View {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        statusStrip = TextView(this).apply {
            textSize = 14f
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(8), dp(12), dp(8))
            visibility = View.GONE
            setOnClickListener { handleStripTap() }
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
        pendingWordAction = null
        hideWordActionStrip()
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        super.onFinishInputView(finishingInput)
        // Best-effort: still learn from whatever the user did to this word, but never try to
        // mutate the host app's text at a moment when focus may already be gone.
        correctionEngine.observeSelfCorrection(tracker.finalizeWord())
        composer.reset()
        pendingWordAction = null
        hideWordActionStrip()
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
        pendingWordAction = null
        hideWordActionStrip()
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
            pendingWordAction = null
            hideWordActionStrip()
            return
        }

        // Learning always happens (above); only auto-apply / suggesting respects the pause toggle.
        val autoCorrection = if (autoCorrectEnabled) correctionEngine.suggestCorrection(typedWord) else null
        val committedWord = autoCorrection ?: typedWord
        ic.setComposingText(committedWord, 1)
        ic.finishComposingText()
        if (trailing.isNotEmpty()) ic.commitText(trailing, 1)

        when {
            autoCorrection != null -> {
                pendingWordAction = WordAction(committedWord, trailing, typedWord, WordActionMode.REVERT_AUTOCORRECT)
                showAutoCorrectedStrip(typedWord, autoCorrection)
            }
            autoCorrectEnabled -> {
                val suggestion = dictionarySuggester.suggest(typedWord)
                if (suggestion != null) {
                    pendingWordAction = WordAction(committedWord, trailing, suggestion, WordActionMode.APPLY_SUGGESTION)
                    showSuggestionStrip(typedWord, suggestion)
                } else {
                    pendingWordAction = null
                    hideWordActionStrip()
                }
            }
            else -> {
                pendingWordAction = null
                hideWordActionStrip()
            }
        }
        composer.reset()
    }

    private fun handleStripTap() {
        when (pendingWordAction?.mode) {
            WordActionMode.REVERT_AUTOCORRECT -> revertAutoCorrect()
            WordActionMode.APPLY_SUGGESTION -> applySuggestion()
            null -> Unit
        }
    }

    private fun revertAutoCorrect() {
        val action = pendingWordAction?.takeIf { it.mode == WordActionMode.REVERT_AUTOCORRECT } ?: return
        val ic = currentInputConnection ?: return
        ic.deleteSurroundingText(action.committedText.length + action.trailing.length, 0)
        ic.commitText(action.alternativeText + action.trailing, 1)
        correctionEngine.forget(action.alternativeText)
        pendingWordAction = null
        hideWordActionStrip()
    }

    private fun applySuggestion() {
        val action = pendingWordAction?.takeIf { it.mode == WordActionMode.APPLY_SUGGESTION } ?: return
        val ic = currentInputConnection ?: return
        ic.deleteSurroundingText(action.committedText.length + action.trailing.length, 0)
        ic.commitText(action.alternativeText + action.trailing, 1)
        correctionEngine.confirmSuggestion(action.committedText, action.alternativeText)
        pendingWordAction = null
        hideWordActionStrip()
    }

    private fun updateComposingDisplay() {
        currentInputConnection?.setComposingText(composer.text, 1)
    }

    private fun showAutoCorrectedStrip(typo: String, correction: String) {
        statusStrip.text = getString(R.string.autocorrect_hint_format, typo, correction)
        statusStrip.setBackgroundColor(ContextCompat.getColor(this, R.color.strip_background))
        statusStrip.setTextColor(ContextCompat.getColor(this, R.color.strip_text))
        statusStrip.visibility = View.VISIBLE
    }

    private fun showSuggestionStrip(typo: String, suggestion: String) {
        statusStrip.text = getString(R.string.suggestion_hint_format, typo, suggestion)
        statusStrip.setBackgroundColor(ContextCompat.getColor(this, R.color.suggestion_background))
        statusStrip.setTextColor(ContextCompat.getColor(this, R.color.suggestion_text))
        statusStrip.visibility = View.VISIBLE
    }

    private fun hideWordActionStrip() {
        statusStrip.visibility = View.GONE
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()

    companion object {
        private const val DICTIONARY_ASSET = "common_words_ko.txt"

        private val PERFORMABLE_ACTIONS = setOf(
            EditorInfo.IME_ACTION_SEND,
            EditorInfo.IME_ACTION_GO,
            EditorInfo.IME_ACTION_SEARCH,
            EditorInfo.IME_ACTION_DONE,
            EditorInfo.IME_ACTION_NEXT
        )
    }
}

package com.hhkim88.typofix.core

/**
 * Watches the string content of the word currently being typed and detects
 * the "typed something, backspaced it out, retyped something else" pattern
 * that is the whole premise of this app: people type a typo, notice it,
 * delete it, and type the correct word before sending. Capturing that
 * (typo -> correction) pair is what lets the keyboard learn a user's
 * personal typo habits.
 *
 * This class only ever sees plain strings (the composed word so far), so it
 * has no dependency on Android or on [HangulComposer] and can be unit
 * tested directly.
 */
class WordAttemptTracker {

    private var buffer: String = ""
    private var direction: Direction = Direction.NONE
    private val peaks = mutableListOf<String>()

    private enum class Direction { NONE, GROWING, SHRINKING }

    /** Call after every keystroke (letter or backspace) with the new word-so-far string. */
    fun update(newValue: String) {
        val grew = newValue.length > buffer.length
        val shrank = newValue.length < buffer.length

        if (shrank && direction != Direction.SHRINKING) {
            // `buffer` (the value right before this shrink) was a local peak.
            if (buffer.isNotBlank()) peaks.add(buffer)
        }

        direction = when {
            grew -> Direction.GROWING
            shrank -> Direction.SHRINKING
            else -> direction
        }
        buffer = newValue
    }

    /**
     * Call when the word boundary is reached (space, newline, punctuation, send).
     * Returns the (typo, correction) candidate if the user backspaced away from
     * an earlier, different attempt before settling on the final word.
     * Resets internal state either way.
     */
    fun finalizeWord(): TypoCandidate? {
        val final = buffer
        val candidate = peaks.lastOrNull { it != final && it.isNotBlank() }
        reset()
        return if (candidate != null && final.isNotBlank()) TypoCandidate(candidate, final) else null
    }

    fun reset() {
        buffer = ""
        direction = Direction.NONE
        peaks.clear()
    }
}

data class TypoCandidate(val typo: String, val correction: String)

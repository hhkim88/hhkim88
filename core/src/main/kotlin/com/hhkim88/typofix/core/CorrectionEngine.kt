package com.hhkim88.typofix.core

/**
 * Ties the store and the per-word learning signal together.
 *
 * - [observeSelfCorrection] should be called with whatever [WordAttemptTracker.finalizeWord]
 *   returned for the word the user just finished typing: it feeds the learning store.
 * - [suggestCorrection] should be called with a freshly (first-try) typed word to see whether
 *   it matches a typo the user has corrected themselves often enough in the past, in which case
 *   the keyboard can auto-correct it going forward.
 */
class CorrectionEngine(
    private val store: CorrectionStore,
    private val minConfidenceCount: Int = 2
) {

    fun observeSelfCorrection(candidate: TypoCandidate?) {
        if (candidate == null) return
        if (candidate.typo == candidate.correction) return
        store.recordAttempt(candidate.typo, candidate.correction)
    }

    fun suggestCorrection(word: String): String? {
        val match = store.lookup(word) ?: return null
        if (!match.enabled) return null
        if (match.count < minConfidenceCount) return null
        if (match.correction == word) return null
        return match.correction
    }

    fun learnedCorrections(): List<Correction> = store.allCorrections()

    fun forget(typo: String) = store.remove(typo)

    fun setEnabled(typo: String, enabled: Boolean) = store.setEnabled(typo, enabled)
}

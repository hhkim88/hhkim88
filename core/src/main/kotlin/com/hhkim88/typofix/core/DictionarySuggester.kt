package com.hhkim88.typofix.core

import kotlin.math.abs

/**
 * Catches the typo class personal-memory learning can't: a word the user has never
 * self-corrected before (so there's no learned pair for it yet), but which doesn't look like
 * a real word at all.
 *
 * The idea: if a freshly typed word isn't in the dictionary, look for the nearest dictionary
 * word using a keyboard-aware edit distance. Only surface it as a suggestion when that nearest
 * word is a clearly better match than the *next*-nearest one -- i.e. when the typing "could
 * plausibly be" almost nothing else. If several dictionary words are roughly equally close,
 * it's too ambiguous to guess, so no suggestion is made.
 */
class DictionarySuggester(
    private val dictionary: WordListDictionary,
    private val maxWeightedDistance: Double = 1.4,
    private val minConfidenceGap: Double = 0.3
) {

    fun suggest(word: String): String? {
        if (word.isBlank() || dictionary.contains(word)) return null

        val target = HangulComposer.decomposeToJamoSequence(word)

        var best: String? = null
        var bestDistance = Double.MAX_VALUE
        var runnerUpDistance = Double.MAX_VALUE

        for (candidate in dictionary.all) {
            if (abs(candidate.length - word.length) > 2) continue // cheap pre-filter
            val distance = WeightedEditDistance.compute(target, HangulComposer.decomposeToJamoSequence(candidate))
            when {
                distance < bestDistance -> {
                    runnerUpDistance = bestDistance
                    bestDistance = distance
                    best = candidate
                }
                distance < runnerUpDistance -> runnerUpDistance = distance
            }
        }

        if (best == null || bestDistance > maxWeightedDistance) return null
        if (runnerUpDistance - bestDistance < minConfidenceGap) return null // too ambiguous to guess
        return best
    }
}
